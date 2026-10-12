-- Persist refresh choices alongside metadata without changing public JSON models.
BEGIN;
ALTER TABLE catalog.contests ADD COLUMN refresh_policy jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(refresh_policy)='object');
ALTER TABLE catalog.problems ADD COLUMN refresh_policy jsonb NOT NULL DEFAULT '{"source":null,"manual":["title"],"fields":{}}' CHECK (jsonb_typeof(refresh_policy)='object');
CREATE OR REPLACE FUNCTION catalog.admin_catalog()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT catalog.read_catalog() || jsonb_build_object(
        'refresh', jsonb_build_object(
            'contests', (SELECT COALESCE(jsonb_object_agg(id,refresh_policy),'{}') FROM catalog.contests),
            'problems', (SELECT COALESCE(jsonb_object_agg(id,refresh_policy),'{}') FROM catalog.problems)),
        'versions', jsonb_build_object(
            'contests', (SELECT COALESCE(jsonb_object_agg(id,updated_at::text),'{}') FROM catalog.contests),
            'problems', (SELECT COALESCE(jsonb_object_agg(id,updated_at::text),'{}') FROM catalog.problems)),
        'usages', (SELECT COALESCE(jsonb_object_agg(p.id,
            (SELECT COALESCE(jsonb_agg(item),'[]') FROM
                (SELECT DISTINCT jsonb_build_object('id',c.id,'title',c.payload->>'title') AS item
                 FROM catalog.contest_problems cp JOIN catalog.contests c ON c.id=cp.contest_id
                 WHERE cp.problem_id=p.id) uses)),'{}') FROM catalog.problems p));
$$;

CREATE OR REPLACE FUNCTION catalog.admin_publish_with_refresh(p_contest jsonb,p_problems jsonb,p_versions jsonb,p_refresh jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE item jsonb; entity_id uuid; rules jsonb; actual text;
BEGIN
    IF p_refresh IS NOT NULL AND p_refresh <> 'null'::jsonb
        AND (jsonb_typeof(p_refresh->'contest') IS DISTINCT FROM 'object'
            OR jsonb_typeof(p_refresh->'problems') IS DISTINCT FROM 'object') THEN
        RAISE EXCEPTION 'Invalid refresh settings' USING ERRCODE='22023';
    END IF;
    -- A preceding row in this batch may already have published the same shared
    -- value. Rebase only when metadata and refresh choices agree; observation
    -- timestamps do not establish a conflicting edit.
    FOR item IN SELECT value FROM jsonb_array_elements(p_problems) LOOP
        entity_id:=(item->>'id')::uuid;
        rules:=p_refresh->'problems'->entity_id::text;
        SELECT p.updated_at::text INTO actual FROM catalog.problems p WHERE p.id=entity_id
            AND p.payload=item-'id' AND (rules IS NULL OR p.refresh_policy-'fields'=rules-'fields');
        IF FOUND THEN
            p_versions:=jsonb_set(p_versions,ARRAY['problems',entity_id::text],to_jsonb(actual));
        END IF;
    END LOOP;
    PERFORM catalog.admin_publish(p_contest,p_problems,p_versions);
    IF p_refresh IS NOT NULL AND p_refresh <> 'null'::jsonb THEN
        rules:=p_refresh->'contest';
        UPDATE catalog.contests SET refresh_policy=rules WHERE id=(p_contest->>'id')::uuid AND refresh_policy IS DISTINCT FROM rules;
        FOR item IN SELECT value FROM jsonb_array_elements(p_problems) LOOP
            entity_id:=(item->>'id')::uuid;
            rules:=p_refresh->'problems'->entity_id::text;
            IF rules IS NOT NULL THEN
                UPDATE catalog.problems SET refresh_policy=rules WHERE catalog.problems.id=entity_id AND refresh_policy IS DISTINCT FROM rules;
            END IF;
        END LOOP;
    END IF;
    RETURN catalog.admin_catalog();
END;
$$;
REVOKE ALL ON FUNCTION catalog.admin_publish_with_refresh(jsonb,jsonb,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_publish_with_refresh(jsonb,jsonb,jsonb,jsonb) TO service_role;
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
            PERFORM catalog.admin_publish_with_refresh(data->'contest',problems,data->'versions',data->'refresh');
            item:=jsonb_set(item,'{status}','"published"');
            item:=item-'error'-'jobId';
            item:=jsonb_set(item,'{overrides}','[]');
            item:=item #- '{draft,refreshReport}';
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
                ELSE 'Publication failed. Check source identities, fields, and problem references.' END));
        END;
        rows:=jsonb_set(rows,ARRAY[id::text],item);
    END LOOP;
    UPDATE app_private.admin_workspaces SET payload=jsonb_build_object('rows',rows),
        revision=gen_random_uuid(),updated_at=clock_timestamp() WHERE user_id=p_user_id;
    RETURN catalog.admin_workspace_read(p_user_id);
END;
$$;

COMMIT;
