-- Map the agreed problem/contest JSON model onto the existing catalog.
-- Private user payloads, categories, statement variants, and archives remain
-- structural scaffolding. No hosted service or file bucket is provisioned.
BEGIN;

CREATE FUNCTION app_private.has_json_fields(value jsonb, fields text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $$
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
    RETURN value ?& fields AND NOT EXISTS (
        SELECT 1 FROM jsonb_object_keys(value) AS item(key) WHERE key <> ALL(fields)
    );
END;
$$;

CREATE FUNCTION app_private.nonempty_json_string(value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog
AS $$
    SELECT COALESCE(jsonb_typeof(value) = 'string' AND (value #>> '{}') ~ '[^[:space:]]', false);
$$;

CREATE FUNCTION app_private.https_json_url(value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog
AS $$
    SELECT COALESCE(jsonb_typeof(value) = 'string'
        AND (value #>> '{}') ~ '^https://[^/?#[:space:]]+([/?#][^[:space:]]*)?$'
        AND substring(value #>> '{}' FROM '^https://([^/?#]+)') !~ '@', false);
$$;

CREATE FUNCTION app_private.valid_json_links(value jsonb, fields text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $$
DECLARE item jsonb;
BEGIN
    IF NOT app_private.has_json_fields(value, fields) THEN RETURN false; END IF;
    FOR item IN SELECT entry.value FROM jsonb_each(value) AS entry LOOP
        IF item <> 'null'::jsonb AND NOT app_private.https_json_url(item) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;

CREATE FUNCTION app_private.valid_problem_metadata(value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog
AS $$
    SELECT app_private.has_json_fields(value, ARRAY['title', 'link'])
        AND app_private.nonempty_json_string(value -> 'title')
        AND app_private.valid_json_links(value -> 'link', ARRAY['cf', 'qoj', 'atcoder']);
$$;

CREATE FUNCTION app_private.valid_contest_metadata(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $$
DECLARE part jsonb;
BEGIN
    IF NOT app_private.has_json_fields(value, ARRAY['title', 'year', 'category', 'link'])
        OR NOT app_private.nonempty_json_string(value -> 'title')
        OR jsonb_typeof(value -> 'year') NOT IN ('string', 'null')
        OR NOT app_private.valid_json_links(value -> 'link', ARRAY['cf', 'qoj', 'atcoder', 'official', 'standings'])
        THEN RETURN false;
    END IF;
    IF value -> 'category' = 'null'::jsonb THEN RETURN true; END IF;
    IF jsonb_typeof(value -> 'category') <> 'array' THEN RETURN false; END IF;
    FOR part IN SELECT jsonb_array_elements(value -> 'category') LOOP
        IF NOT app_private.nonempty_json_string(part) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;

CREATE FUNCTION app_private.valid_material_metadata(value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog
AS $$
    SELECT app_private.has_json_fields(value, ARRAY['role', 'title', 'language', 'url'])
        AND app_private.nonempty_json_string(value -> 'role')
        AND app_private.nonempty_json_string(value -> 'title')
        AND jsonb_typeof(value -> 'language') IN ('string', 'null')
        AND app_private.https_json_url(value -> 'url');
$$;

-- Counts describe whether a collection is known: NULL = unknown, 0 = known
-- empty. They also let an RLS-filtered reader detect an incomplete graph.
ALTER TABLE catalog.contests
    ADD COLUMN problem_count integer CHECK (problem_count >= 0),
    ADD COLUMN material_count integer CHECK (material_count >= 0),
    ADD CONSTRAINT contest_metadata_shape CHECK (payload IS NULL OR app_private.valid_contest_metadata(payload)),
    ADD CONSTRAINT published_contest_has_metadata CHECK (NOT is_public OR payload IS NOT NULL);
ALTER TABLE catalog.problems
    ADD CONSTRAINT problem_metadata_shape CHECK (payload IS NULL OR app_private.valid_problem_metadata(payload)),
    ADD CONSTRAINT published_problem_has_metadata CHECK (NOT is_public OR payload IS NOT NULL);

ALTER TABLE catalog.contest_problems
    ADD COLUMN position integer CHECK (position >= 0),
    ADD COLUMN problem_index text,
    ADD CONSTRAINT published_membership_has_position CHECK (NOT is_public OR position IS NOT NULL),
    ADD CONSTRAINT contest_problem_position_unique UNIQUE (contest_id, position) DEFERRABLE INITIALLY IMMEDIATE;
ALTER TABLE catalog.materials
    ADD COLUMN position integer CHECK (position >= 0),
    ADD CONSTRAINT material_metadata_shape CHECK (payload IS NULL OR app_private.valid_material_metadata(payload)),
    ADD CONSTRAINT published_material_has_metadata CHECK (NOT is_public OR payload IS NOT NULL),
    ADD CONSTRAINT published_contest_material_has_position
        CHECK (NOT is_public OR contest_id IS NULL OR problem_id IS NOT NULL OR position IS NOT NULL),
    ADD CONSTRAINT contest_material_position_unique UNIQUE (contest_id, position) DEFERRABLE INITIALLY IMMEDIATE;

COMMENT ON COLUMN catalog.problems.payload IS 'Basic JSON metadata: title and link. Identity is the row id; no contest label is stored here.';
COMMENT ON COLUMN catalog.contests.payload IS 'Basic JSON metadata: title, year, category, link. Memberships and materials are authoritative in their related tables.';
COMMENT ON COLUMN catalog.contest_problems.problem_index IS 'Nullable native display label within this contest; separate from the zero-based position.';
COMMENT ON COLUMN catalog.contest_problems.position IS 'Zero-based array order of the contest problem membership.';
COMMENT ON COLUMN catalog.materials.payload IS 'Basic material JSON: role, title, language, url.';

CREATE FUNCTION catalog.problem_json(problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $$
    SELECT jsonb_build_object('id', p.id) || p.payload
    FROM catalog.problems AS p WHERE p.id = problem_id AND p.payload IS NOT NULL;
$$;

CREATE FUNCTION catalog.contest_json(contest_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $$
DECLARE
    entity catalog.contests%ROWTYPE;
    problem_list jsonb;
    material_list jsonb;
BEGIN
    SELECT * INTO entity FROM catalog.contests AS c WHERE c.id = contest_id;
    IF NOT FOUND OR entity.payload IS NULL THEN RETURN NULL; END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('problemId', cp.problem_id, 'index', cp.problem_index)
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

CREATE FUNCTION catalog.read_catalog(curated_only boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog
AS $$
DECLARE contest_list jsonb; problem_list jsonb;
BEGIN
    SELECT COALESCE(jsonb_agg(data ORDER BY created_at, id), '[]'::jsonb) INTO contest_list
    FROM (
        SELECT c.id, c.created_at, catalog.contest_json(c.id) AS data FROM catalog.contests AS c
        WHERE NOT curated_only OR c.payload -> 'category' ->> 0 IN ('ICPC', 'Olympiad')
    ) AS entities WHERE data IS NOT NULL;
    SELECT COALESCE(jsonb_agg(catalog.problem_json(p.id) ORDER BY p.created_at, p.id), '[]'::jsonb)
        INTO problem_list FROM catalog.problems AS p WHERE p.payload IS NOT NULL AND (
            NOT curated_only OR EXISTS (
                SELECT 1 FROM jsonb_array_elements(contest_list) AS c(value),
                    LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(c.value -> 'problems') = 'array'
                        THEN c.value -> 'problems' ELSE '[]'::jsonb END) AS entry(value)
                WHERE entry.value ->> 'problemId' = p.id::text
            )
        );
    RETURN jsonb_build_object('contests', contest_list, 'problems', problem_list);
END;
$$;

-- Administrative write adapter: canonical JSON in, atomic relational records
-- out. Caller supplies stable UUIDs; titles never establish entity identity.
CREATE FUNCTION catalog.write_catalog(contests jsonb, problems jsonb, publish boolean DEFAULT false)
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
        IF NOT app_private.has_json_fields(item, ARRAY['id', 'title', 'year', 'category', 'link', 'problems', 'materials'])
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
            IF NOT app_private.has_json_fields(entry, ARRAY['problemId', 'index'])
                OR jsonb_typeof(entry -> 'problemId') IS DISTINCT FROM 'string'
                OR jsonb_typeof(entry -> 'index') NOT IN ('string', 'null') THEN
                RAISE EXCEPTION 'Invalid contest problem membership.' USING ERRCODE = '22023';
            END IF;
            referenced_id := (entry ->> 'problemId')::uuid;
            IF publish AND NOT EXISTS (SELECT 1 FROM catalog.problems AS p
                WHERE p.id = referenced_id AND p.is_public AND p.payload IS NOT NULL) THEN
                RAISE EXCEPTION 'Publishing a contest requires published referenced problems.' USING ERRCODE = '23503';
            END IF;
            SELECT cp.id INTO row_id FROM catalog.contest_problems AS cp
                WHERE cp.contest_id = entity_id AND cp.problem_id = referenced_id AND cp.id <> ALL(kept)
                ORDER BY (cp.problem_index IS NOT DISTINCT FROM entry ->> 'index') DESC,
                    cp.position NULLS LAST, cp.id LIMIT 1 FOR UPDATE;
            IF FOUND THEN
                UPDATE catalog.contest_problems SET position = ordinal, problem_index = entry ->> 'index',
                    is_public = is_public OR publish WHERE id = row_id;
            ELSE
                INSERT INTO catalog.contest_problems (contest_id, problem_id, position, problem_index, is_public)
                    VALUES (entity_id, referenced_id, ordinal, entry ->> 'index', publish) RETURNING id INTO row_id;
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

GRANT USAGE ON SCHEMA app_private TO service_role;
REVOKE ALL ON FUNCTION app_private.has_json_fields(jsonb, text[]), app_private.nonempty_json_string(jsonb),
    app_private.https_json_url(jsonb), app_private.valid_json_links(jsonb, text[]),
    app_private.valid_problem_metadata(jsonb), app_private.valid_contest_metadata(jsonb),
    app_private.valid_material_metadata(jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app_private.has_json_fields(jsonb, text[]), app_private.nonempty_json_string(jsonb),
    app_private.https_json_url(jsonb), app_private.valid_json_links(jsonb, text[]),
    app_private.valid_problem_metadata(jsonb), app_private.valid_contest_metadata(jsonb),
    app_private.valid_material_metadata(jsonb) TO service_role;

REVOKE ALL ON FUNCTION catalog.problem_json(uuid), catalog.contest_json(uuid), catalog.read_catalog(boolean),
    catalog.write_catalog(jsonb, jsonb, boolean) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION catalog.problem_json(uuid), catalog.contest_json(uuid), catalog.read_catalog(boolean)
    TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION catalog.write_catalog(jsonb, jsonb, boolean) TO service_role;

COMMIT;
