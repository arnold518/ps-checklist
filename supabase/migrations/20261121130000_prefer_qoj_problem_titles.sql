BEGIN;

-- Keep publication and its locks intact. BOJ can supply the title for tasks
-- without QOJ, and reviewed BOJ bindings remain available for solved.ac.
DO $migration$
DECLARE
    definition text := pg_get_functiondef(
        'catalog.admin_publish_boj(uuid,text,text,jsonb,jsonb,uuid)'::regprocedure);
    original_filter text := $filter$WHERE id=target AND NOT COALESCE(refresh_policy->'manual' ? 'title',false);$filter$;
    revised_definition text;
BEGIN
    revised_definition := replace(definition, original_filter, $filter$WHERE id=target
                AND payload->'link'->>'qoj' IS NULL
                AND NOT COALESCE(refresh_policy->'manual' ? 'title',false);$filter$);
    IF revised_definition = definition THEN
        RAISE EXCEPTION 'Expected the BOJ title adoption filter';
    END IF;
    EXECUTE revised_definition;
END;
$migration$;

COMMIT;
