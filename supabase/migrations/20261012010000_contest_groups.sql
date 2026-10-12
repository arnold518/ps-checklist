-- Optional ordered groups within one contest edition. Shared problem identities,
-- RLS, practice records, and explicit publication remain unchanged.
BEGIN;
ALTER TABLE catalog.contest_problems ADD COLUMN group_id text;
COMMENT ON COLUMN catalog.contest_problems.group_id IS 'Optional ID of a group in the owning contest payload. Labels remain complete display strings.';
CREATE FUNCTION app_private.valid_contest_groups(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $$
DECLARE g jsonb; m jsonb; ids text[] := ARRAY[]::text[];
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) > 20 THEN RETURN false; END IF;
    FOR g IN SELECT jsonb_array_elements(value) LOOP
        IF NOT app_private.has_json_fields(g, ARRAY['id','title','prefix','link','materials'])
            OR NOT app_private.nonempty_json_string(g->'id') OR g->>'id' = ANY(ids)
            OR NOT app_private.nonempty_json_string(g->'title')
            OR jsonb_typeof(g->'prefix') IS DISTINCT FROM 'string' OR length(g->>'prefix') > 32
            OR NOT app_private.valid_json_links(g->'link', ARRAY['cf','qoj','atcoder','official','standings'])
            OR jsonb_typeof(g->'materials') IS DISTINCT FROM 'array' THEN RETURN false; END IF;
        ids := array_append(ids, g->>'id');
        FOR m IN SELECT jsonb_array_elements(g->'materials') LOOP
            IF NOT app_private.valid_material_metadata(m) THEN RETURN false; END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END;
$$;
REVOKE ALL ON FUNCTION app_private.valid_contest_groups(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app_private.valid_contest_groups(jsonb) TO service_role;

CREATE OR REPLACE FUNCTION app_private.valid_contest_metadata(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $$
DECLARE part jsonb;
BEGIN
    IF NOT app_private.has_json_fields(value - 'groups', ARRAY['title', 'year', 'category', 'link'])
        OR NOT app_private.nonempty_json_string(value -> 'title')
        OR jsonb_typeof(value -> 'year') NOT IN ('string', 'null')
        OR NOT app_private.valid_json_links(value -> 'link', ARRAY['cf', 'qoj', 'atcoder', 'official', 'standings'])
        THEN RETURN false;
    END IF;
    IF value ? 'groups' AND NOT app_private.valid_contest_groups(value->'groups') THEN RETURN false; END IF;
    IF value -> 'category' = 'null'::jsonb THEN RETURN true; END IF;
    IF jsonb_typeof(value -> 'category') <> 'array' THEN RETURN false; END IF;
    FOR part IN SELECT jsonb_array_elements(value -> 'category') LOOP
        IF NOT app_private.nonempty_json_string(part) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;
CREATE OR REPLACE FUNCTION catalog.contest_json(contest_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $$
DECLARE
    entity catalog.contests%ROWTYPE;
    problem_list jsonb;
    material_list jsonb;
BEGIN
    SELECT * INTO entity FROM catalog.contests AS c WHERE c.id = contest_id;
    IF NOT FOUND OR entity.payload IS NULL THEN RETURN NULL; END IF;
    SELECT COALESCE(jsonb_agg((jsonb_build_object('problemId', cp.problem_id, 'index', cp.problem_index)
        || CASE WHEN cp.group_id IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('groupId', cp.group_id) END)
        ORDER BY cp.position), '[]'::jsonb) INTO problem_list
        FROM catalog.contest_problems AS cp JOIN catalog.problems AS p ON p.id = cp.problem_id
        WHERE cp.contest_id = entity.id AND cp.position IS NOT NULL AND p.payload IS NOT NULL;
    SELECT COALESCE(jsonb_agg(m.payload ORDER BY m.position), '[]'::jsonb) INTO material_list
        FROM catalog.materials AS m WHERE m.contest_id = entity.id AND m.problem_id IS NULL
        AND m.position IS NOT NULL AND m.payload IS NOT NULL;
    -- Return no assembled entity if hidden or incomplete children would make a
    -- known collection appear shorter. RLS is respected by every query above.
    IF (entity.problem_count IS NOT NULL AND jsonb_array_length(problem_list) <> entity.problem_count)
        OR (entity.material_count IS NOT NULL AND jsonb_array_length(material_list) <> entity.material_count)
        THEN RETURN NULL;
    END IF;
    RETURN jsonb_build_object('id', entity.id) || entity.payload || jsonb_build_object(
        'problems', CASE WHEN entity.problem_count IS NULL THEN 'null'::jsonb ELSE problem_list END,
        'materials', CASE WHEN entity.material_count IS NULL THEN 'null'::jsonb ELSE material_list END
    );
END;
$$;
CREATE OR REPLACE FUNCTION catalog.write_catalog(contests jsonb, problems jsonb, publish boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path = pg_catalog
AS $$
DECLARE
    item jsonb;
    entry jsonb;
    entity_id uuid;
    referenced_id uuid;
    row_id uuid;
    ordinal integer;
    metadata jsonb;
    old_metadata jsonb;
    was_public boolean;
    seen_problems uuid[] := ARRAY[]::uuid[];
    seen_contests uuid[] := ARRAY[]::uuid[];
    kept uuid[];
BEGIN
    IF jsonb_typeof(contests) IS DISTINCT FROM 'array' OR jsonb_typeof(problems) IS DISTINCT FROM 'array'
        OR publish IS NULL THEN
        RAISE EXCEPTION 'Provide contest/problem arrays and a publication boolean.' USING ERRCODE = '22023';
    END IF;
    SET CONSTRAINTS catalog.contest_problem_position_unique, catalog.contest_material_position_unique DEFERRED;

    FOR item IN SELECT value FROM jsonb_array_elements(problems) WITH ORDINALITY AS input(value, n) ORDER BY n LOOP
        IF NOT app_private.has_json_fields(item, ARRAY['id', 'title', 'link'])
            OR jsonb_typeof(item -> 'id') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'Invalid basic problem object.' USING ERRCODE = '22023';
        END IF;
        entity_id := (item ->> 'id')::uuid;
        IF entity_id = ANY(seen_problems) THEN
            RAISE EXCEPTION 'Duplicate problem id in input.' USING ERRCODE = '22023';
        END IF;
        seen_problems := array_append(seen_problems, entity_id);
        metadata := item - 'id';
        SELECT p.payload, p.is_public INTO old_metadata, was_public
            FROM catalog.problems AS p WHERE p.id = entity_id FOR UPDATE;
        IF FOUND AND was_public AND NOT publish AND old_metadata IS DISTINCT FROM metadata THEN
            RAISE EXCEPTION 'Published problem changes require explicit publication.' USING ERRCODE = '22023';
        END IF;
        INSERT INTO catalog.problems AS target (id, payload, is_public) VALUES (entity_id, metadata, publish)
            ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, is_public = target.is_public OR publish;
    END LOOP;

    FOR item IN SELECT value FROM jsonb_array_elements(contests) WITH ORDINALITY AS input(value, n) ORDER BY n LOOP
        IF NOT app_private.has_json_fields(item - 'groups', ARRAY['id', 'title', 'year', 'category', 'link', 'problems', 'materials'])
            OR jsonb_typeof(item -> 'id') IS DISTINCT FROM 'string'
            OR jsonb_typeof(item -> 'problems') NOT IN ('array', 'null')
            OR jsonb_typeof(item -> 'materials') NOT IN ('array', 'null') THEN
            RAISE EXCEPTION 'Invalid basic contest object.' USING ERRCODE = '22023';
        END IF;
        entity_id := (item ->> 'id')::uuid;
        IF entity_id = ANY(seen_contests) THEN
            RAISE EXCEPTION 'Duplicate contest id in input.' USING ERRCODE = '22023';
        END IF;
        seen_contests := array_append(seen_contests, entity_id);
        metadata := item - ARRAY['id', 'problems', 'materials'];
        SELECT c.payload, c.is_public INTO old_metadata, was_public
            FROM catalog.contests AS c WHERE c.id = entity_id FOR UPDATE;
        IF FOUND AND was_public AND NOT publish AND catalog.contest_json(entity_id) IS DISTINCT FROM item THEN
            RAISE EXCEPTION 'Published contest changes require explicit publication.' USING ERRCODE = '22023';
        END IF;
        INSERT INTO catalog.contests AS target (id, payload, is_public, problem_count, material_count)
            VALUES (entity_id, metadata, publish,
                CASE WHEN item -> 'problems' = 'null'::jsonb THEN NULL ELSE jsonb_array_length(item -> 'problems') END,
                CASE WHEN item -> 'materials' = 'null'::jsonb THEN NULL ELSE jsonb_array_length(item -> 'materials') END)
            ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, is_public = target.is_public OR publish,
                problem_count = EXCLUDED.problem_count, material_count = EXCLUDED.material_count;

        kept := ARRAY[]::uuid[];
        ordinal := 0;
        FOR entry IN SELECT value FROM jsonb_array_elements(
            CASE WHEN item -> 'problems' = 'null'::jsonb THEN '[]'::jsonb ELSE item -> 'problems' END
        ) WITH ORDINALITY AS input(value, n) ORDER BY n LOOP
            IF NOT app_private.has_json_fields(entry - 'groupId', ARRAY['problemId', 'index'])
                OR jsonb_typeof(entry -> 'problemId') IS DISTINCT FROM 'string'
                OR jsonb_typeof(entry -> 'index') NOT IN ('string', 'null') THEN
                RAISE EXCEPTION 'Invalid contest problem membership.' USING ERRCODE = '22023';
            END IF;
            IF entry ? 'groupId' AND (jsonb_typeof(entry->'groupId') IS DISTINCT FROM 'string'
                OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(item->'groups','[]'::jsonb)) AS g(value)
                    WHERE g.value->>'id' = entry->>'groupId')) THEN
                RAISE EXCEPTION 'Membership group does not belong to this contest.' USING ERRCODE = '22023';
            END IF;
            referenced_id := (entry ->> 'problemId')::uuid;
            IF publish AND NOT EXISTS (SELECT 1 FROM catalog.problems AS p
                WHERE p.id = referenced_id AND p.is_public AND p.payload IS NOT NULL) THEN
                RAISE EXCEPTION 'Publishing a contest requires published referenced problems.' USING ERRCODE = '23503';
            END IF;
            SELECT cp.id INTO row_id FROM catalog.contest_problems AS cp
                WHERE cp.contest_id = entity_id AND cp.problem_id = referenced_id AND cp.id <> ALL(kept)
                ORDER BY (cp.group_id IS NOT DISTINCT FROM entry ->> 'groupId') DESC,
                    (cp.problem_index IS NOT DISTINCT FROM entry ->> 'index') DESC,
                    cp.position NULLS LAST, cp.id LIMIT 1 FOR UPDATE;
            IF FOUND THEN
                UPDATE catalog.contest_problems SET position = ordinal, problem_index = entry ->> 'index', group_id = entry ->> 'groupId',
                    is_public = is_public OR publish WHERE id = row_id;
            ELSE
                INSERT INTO catalog.contest_problems (contest_id, problem_id, position, problem_index, group_id, is_public)
                    VALUES (entity_id, referenced_id, ordinal, entry ->> 'index', entry ->> 'groupId', publish) RETURNING id INTO row_id;
            END IF;
            kept := array_append(kept, row_id);
            ordinal := ordinal + 1;
        END LOOP;
        DELETE FROM catalog.contest_problems WHERE contest_id = entity_id AND id <> ALL(kept);

        kept := ARRAY[]::uuid[];
        ordinal := 0;
        FOR entry IN SELECT value FROM jsonb_array_elements(
            CASE WHEN item -> 'materials' = 'null'::jsonb THEN '[]'::jsonb ELSE item -> 'materials' END
        ) WITH ORDINALITY AS input(value, n) ORDER BY n LOOP
            SELECT m.id INTO row_id FROM catalog.materials AS m
                WHERE m.contest_id = entity_id AND m.problem_id IS NULL AND m.id <> ALL(kept)
                    AND m.payload ->> 'url' = entry ->> 'url'
                ORDER BY (m.payload = entry) DESC, m.position NULLS LAST, m.id LIMIT 1 FOR UPDATE;
            IF FOUND THEN
                UPDATE catalog.materials SET position = ordinal, payload = entry, is_public = is_public OR publish WHERE id = row_id;
            ELSE
                INSERT INTO catalog.materials (contest_id, position, payload, is_public)
                    VALUES (entity_id, ordinal, entry, publish) RETURNING id INTO row_id;
            END IF;
            kept := array_append(kept, row_id);
            ordinal := ordinal + 1;
        END LOOP;
        DELETE FROM catalog.materials WHERE contest_id = entity_id AND problem_id IS NULL AND id <> ALL(kept);
    END LOOP;
    SET CONSTRAINTS catalog.contest_problem_position_unique, catalog.contest_material_position_unique IMMEDIATE;
    RETURN jsonb_build_object('contests', jsonb_array_length(contests), 'problems', jsonb_array_length(problems));
END;
$$;
COMMIT;
