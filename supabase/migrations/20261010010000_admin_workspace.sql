-- Private, durable admin drafts. Existing canonical data is changed only by publication.
BEGIN;
CREATE TABLE IF NOT EXISTS app_private.admin_workspaces (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    revision uuid NOT NULL DEFAULT gen_random_uuid(),
    payload jsonb NOT NULL DEFAULT '{"rows":{}}',
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(payload->'rows')='object')
);
ALTER TABLE app_private.admin_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.admin_workspaces FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app_private.admin_workspaces FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON app_private.admin_workspaces TO service_role;

CREATE OR REPLACE FUNCTION catalog.admin_workspace_read(p_user_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE((SELECT jsonb_build_object('revision',revision,'rows',payload->'rows')
        FROM app_private.admin_workspaces WHERE user_id=p_user_id),' {"revision":null,"rows":{}}'::jsonb);
$$;

CREATE OR REPLACE FUNCTION catalog.admin_workspace_pending(p_queue text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_agg(user_id),'[]') FROM app_private.admin_workspaces
        WHERE EXISTS(SELECT 1 FROM jsonb_each(payload->'rows') rows
            WHERE rows.value->>'queue'=p_queue AND rows.value->>'status' IN ('queued','running'));
$$;

CREATE OR REPLACE FUNCTION catalog.admin_workspace_save(p_user_id uuid,p_revision uuid,p_changes jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE current_revision uuid; rows jsonb; entry record;
BEGIN
    IF jsonb_typeof(p_changes) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'Provide draft row changes' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('admin-workspace:'||p_user_id::text,0));
    SELECT revision,payload->'rows' INTO current_revision,rows
        FROM app_private.admin_workspaces WHERE user_id=p_user_id FOR UPDATE;
    IF current_revision IS DISTINCT FROM p_revision THEN
        RAISE EXCEPTION 'Workspace changed' USING ERRCODE='40001';
    END IF;
    rows:=COALESCE(rows,'{}');
    FOR entry IN SELECT * FROM jsonb_each(p_changes) LOOP
        IF entry.value='null'::jsonb THEN rows:=rows-entry.key;
        ELSE
            IF jsonb_typeof(entry.value) IS DISTINCT FROM 'object'
                OR entry.value->'draft'->'contest'->>'id' IS DISTINCT FROM entry.key
                OR NOT EXISTS(SELECT 1 FROM catalog.contests WHERE id=entry.key::uuid) THEN
                RAISE EXCEPTION 'Only existing catalog rows can be staged' USING ERRCODE='22023';
            END IF;
            rows:=jsonb_set(rows,ARRAY[entry.key],entry.value);
        END IF;
    END LOOP;
    INSERT INTO app_private.admin_workspaces(user_id,payload)
        VALUES(p_user_id,jsonb_build_object('rows',rows))
        ON CONFLICT(user_id) DO UPDATE SET payload=EXCLUDED.payload,revision=gen_random_uuid(),updated_at=clock_timestamp();
    RETURN catalog.admin_workspace_read(p_user_id);
END;
$$;

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
            PERFORM catalog.admin_publish(data->'contest',problems,data->'versions');
            item:=jsonb_set(item,'{status}','"published"');
            item:=item-'error'-'jobId';
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

REVOKE ALL ON FUNCTION catalog.admin_workspace_read(uuid),catalog.admin_workspace_save(uuid,uuid,jsonb),
    catalog.admin_workspace_publish(uuid,uuid,uuid[]),catalog.admin_workspace_pending(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_workspace_read(uuid),catalog.admin_workspace_save(uuid,uuid,jsonb),
    catalog.admin_workspace_publish(uuid,uuid,uuid[]),catalog.admin_workspace_pending(text) TO service_role;
COMMIT;
