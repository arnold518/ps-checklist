-- Published materials keep their source URL and optionally reference a verified
-- archive object. File bytes are staged by the application before this transaction.
BEGIN;

CREATE OR REPLACE FUNCTION app_private.valid_material_metadata(value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT app_private.has_json_fields(value - 'archiveId', ARRAY['role','title','language','url'])
        AND app_private.nonempty_json_string(value->'role')
        AND app_private.nonempty_json_string(value->'title')
        AND jsonb_typeof(value->'language') IN ('string','null')
        AND app_private.https_json_url(value->'url')
        AND (NOT value ? 'archiveId' OR
            (jsonb_typeof(value->'archiveId')='string' AND
             value->>'archiveId' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'));
$$;

CREATE FUNCTION catalog.admin_publish_archived(p_contest jsonb,p_problems jsonb,p_versions jsonb,
    p_refresh jsonb,p_archives jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE item jsonb; material jsonb; archive_id uuid;
BEGIN
    IF jsonb_typeof(p_archives) IS DISTINCT FROM 'array' OR jsonb_array_length(p_archives)>200 THEN
        RAISE EXCEPTION 'Invalid selected archive manifest' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(p_archives) LOOP
        IF NOT app_private.has_json_fields(item,ARRAY['id','sourceUrl','finalUrl','key','sha256','contentType','size','backend'])
            OR NOT app_private.https_json_url(item->'sourceUrl')
            OR NOT app_private.https_json_url(item->'finalUrl')
            OR item->>'key' !~ '^[a-f0-9]{64}$' OR item->>'sha256' IS DISTINCT FROM item->>'key'
            OR item->>'backend' NOT IN ('local','r2')
            OR jsonb_typeof(item->'size') IS DISTINCT FROM 'number'
            OR (item->>'size')::bigint NOT BETWEEN 1 AND 67108864
            OR NOT app_private.nonempty_json_string(item->'contentType') THEN
            RAISE EXCEPTION 'Invalid selected archive object' USING ERRCODE='22023';
        END IF;
        archive_id:=(item->>'id')::uuid;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(COALESCE(NULLIF(p_contest->'materials','null'::jsonb),'[]'::jsonb)) m
                WHERE m->>'url'=item->>'sourceUrl' AND m->>'archiveId'=item->>'id'
            UNION ALL SELECT 1 FROM jsonb_array_elements(COALESCE(p_contest->'groups','[]'::jsonb)) g,
                LATERAL jsonb_array_elements(g->'materials') m
                WHERE m->>'url'=item->>'sourceUrl' AND m->>'archiveId'=item->>'id'
            UNION ALL SELECT 1 FROM jsonb_array_elements(COALESCE(p_contest->'problemMaterials','[]'::jsonb)) m
                WHERE m->>'url'=item->>'sourceUrl' AND m->>'archiveId'=item->>'id'
        ) THEN
            RAISE EXCEPTION 'Archive object is not linked to a selected material' USING ERRCODE='22023';
        END IF;
        INSERT INTO archive.objects(id,owner_id,is_public,payload)
            VALUES(archive_id,NULL,true,item-'id'-'finalUrl');
    END LOOP;
    FOR material IN
        SELECT value FROM jsonb_array_elements(COALESCE(NULLIF(p_contest->'materials','null'::jsonb),'[]'::jsonb))
        UNION ALL SELECT m.value FROM jsonb_array_elements(COALESCE(p_contest->'groups','[]'::jsonb)) g,
            LATERAL jsonb_array_elements(g->'materials') m
        UNION ALL SELECT value FROM jsonb_array_elements(COALESCE(p_contest->'problemMaterials','[]'::jsonb))
    LOOP
        IF material ? 'archiveId' AND NOT EXISTS (
            SELECT 1 FROM archive.objects o WHERE o.id=(material->>'archiveId')::uuid
                AND o.is_public AND o.payload->>'sourceUrl'=material->>'url') THEN
            RAISE EXCEPTION 'Archive reference does not match the selected material' USING ERRCODE='22023';
        END IF;
    END LOOP;
    PERFORM catalog.admin_publish_with_refresh(p_contest,p_problems,p_versions,p_refresh);
    RETURN catalog.admin_catalog();
END;
$$;
REVOKE ALL ON FUNCTION catalog.admin_publish_archived(jsonb,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_publish_archived(jsonb,jsonb,jsonb,jsonb,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION catalog.admin_workspace_publish(p_user_id uuid,p_revision uuid,p_ids uuid[])
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE current_revision uuid; rows jsonb; id uuid; item jsonb; data jsonb; state text; problems jsonb;
BEGIN
    IF cardinality(p_ids) NOT BETWEEN 1 AND 20 THEN
        RAISE EXCEPTION 'Publish between one and twenty rows per request' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('admin-workspace:'||p_user_id::text,0));
    SELECT revision,payload->'rows' INTO current_revision,rows
        FROM app_private.admin_workspaces WHERE user_id=p_user_id FOR UPDATE;
    IF NOT FOUND OR current_revision IS DISTINCT FROM p_revision THEN
        RAISE EXCEPTION 'Workspace changed' USING ERRCODE='40001';
    END IF;
    FOREACH id IN ARRAY p_ids LOOP
        item:=rows->id::text;
        IF item->>'status' IS DISTINCT FROM 'ready' THEN CONTINUE; END IF;
        BEGIN
            data:=item->'draft';
            SELECT COALESCE(jsonb_agg(records.item),'[]') INTO problems FROM jsonb_array_elements(data->'problems') records(item)
                WHERE records.item->>'id' IN (SELECT entries.item->>'problemId'
                    FROM jsonb_array_elements(CASE WHEN data->'contest'->'problems'='null'::jsonb THEN '[]'::jsonb
                        ELSE data->'contest'->'problems' END) entries(item));
            IF data->'archivePrepared' IS NULL THEN
                RAISE EXCEPTION 'Selected attachments have not been staged' USING ERRCODE='22023';
            END IF;
            PERFORM catalog.admin_publish_archived(data->'contest',problems,data->'versions',data->'refresh',data->'archivePrepared');
            item:=jsonb_set(item,'{status}','"published"');
            item:=item-'error'-'jobId';
            item:=jsonb_set(item,'{overrides}','[]');
            item:=item #- '{draft,refreshReport}';
            item:=item #- '{draft,archivePrepared}';
            item:=jsonb_set(item,'{draft,contest}',catalog.contest_json(id));
            item:=jsonb_set(item,'{draft,original,contest}',catalog.contest_json(id));
            item:=jsonb_set(item,'{draft,problems}',problems);
            item:=jsonb_set(item,'{draft,original,problems}',problems);
            item:=jsonb_set(item,'{draft,sources}','[]');
            item:=jsonb_set(item,'{draft,warnings}','[]');
            item:=jsonb_set(item,'{draft,versions}',catalog.admin_catalog()->'versions');
        EXCEPTION WHEN OTHERS THEN
            state:=CASE WHEN SQLSTATE='40001' THEN 'conflict' ELSE 'failed' END;
            item:=jsonb_set(item,'{status}',to_jsonb(state));
            item:=jsonb_set(item,'{error}',to_jsonb(CASE WHEN state='conflict'
                THEN 'Saved metadata changed. Reload this row and review again.'
                ELSE 'Publication failed. Check selected archive links and catalog fields.' END));
        END;
        rows:=jsonb_set(rows,ARRAY[id::text],item);
    END LOOP;
    UPDATE app_private.admin_workspaces SET payload=jsonb_build_object('rows',rows),
        revision=gen_random_uuid(),updated_at=clock_timestamp() WHERE user_id=p_user_id;
    RETURN catalog.admin_workspace_read(p_user_id);
END;
$$;
COMMIT;
