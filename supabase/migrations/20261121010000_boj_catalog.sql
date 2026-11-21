BEGIN;

CREATE TABLE app_private.boj_problems (
    problem_id bigint PRIMARY KEY CHECK (problem_id BETWEEN 1 AND 999999999999999),
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 1000),
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata)='object'),
    observed_at timestamptz NOT NULL,
    detail_fetched_at timestamptz
);
CREATE TABLE app_private.boj_contest_sources (
    source_id bigint PRIMARY KEY CHECK (source_id BETWEEN 1 AND 999999999999999),
    fetched_url text NOT NULL CHECK (fetched_url ~ '^https://(www\.)?acmicpc\.net/category(/(detail/)?[1-9][0-9]*)?/?$'),
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 1000),
    observed_at timestamptz NOT NULL,
    complete_at timestamptz,
    is_complete boolean NOT NULL
);
CREATE TABLE app_private.boj_contest_slots (
    source_id bigint NOT NULL REFERENCES app_private.boj_contest_sources ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    label text,
    displayed_number bigint NOT NULL CHECK (displayed_number BETWEEN 1 AND 999999999999999),
    boj_problem_id bigint REFERENCES app_private.boj_problems,
    PRIMARY KEY (source_id,position),
    UNIQUE (source_id,boj_problem_id),
    CHECK (boj_problem_id IS NULL OR boj_problem_id=displayed_number)
);
CREATE TABLE app_private.catalog_boj_contests (
    source_id bigint PRIMARY KEY REFERENCES app_private.boj_contest_sources,
    contest_id uuid NOT NULL REFERENCES catalog.contests(id),
    group_id text CHECK (group_id IS NULL OR length(btrim(group_id))>0),
    reviewed_by uuid REFERENCES auth.users ON DELETE SET NULL,
    reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE NULLS NOT DISTINCT (contest_id,group_id)
);
CREATE TABLE app_private.catalog_boj_problems (
    catalog_problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    boj_problem_id bigint NOT NULL REFERENCES app_private.boj_problems,
    part_order integer CHECK (part_order > 0),
    preferred boolean NOT NULL DEFAULT false,
    evidence text NOT NULL CHECK (length(btrim(evidence)) BETWEEN 1 AND 2000),
    reviewed_by uuid REFERENCES auth.users ON DELETE SET NULL,
    reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (catalog_problem_id,boj_problem_id),
    UNIQUE (catalog_problem_id,part_order),
    CHECK (part_order IS NULL OR NOT preferred)
);
CREATE UNIQUE INDEX boj_whole_task ON app_private.catalog_boj_problems(boj_problem_id) WHERE part_order IS NULL;
CREATE UNIQUE INDEX boj_preferred_task ON app_private.catalog_boj_problems(catalog_problem_id) WHERE preferred;
CREATE INDEX boj_relations_by_native_id ON app_private.catalog_boj_problems(boj_problem_id);
CREATE INDEX boj_slots_by_problem ON app_private.boj_contest_slots(boj_problem_id);
REVOKE ALL ON app_private.boj_problems,app_private.boj_contest_sources,app_private.boj_contest_slots,
    app_private.catalog_boj_contests,app_private.catalog_boj_problems FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON app_private.boj_problems,app_private.boj_contest_sources,app_private.boj_contest_slots,
    app_private.catalog_boj_contests,app_private.catalog_boj_problems TO service_role;

CREATE FUNCTION app_private.keep_boj_group_binding() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM app_private.catalog_boj_contests b WHERE b.contest_id=NEW.id AND b.group_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(NEW.payload->'groups','[]')) g WHERE g->>'id'=b.group_id))
    THEN RAISE EXCEPTION 'Remove the BOJ group binding before removing its group' USING ERRCODE='22023';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION app_private.keep_boj_group_binding() FROM PUBLIC;
CREATE TRIGGER keep_boj_group_binding BEFORE UPDATE OF payload ON catalog.contests
    FOR EACH ROW EXECUTE FUNCTION app_private.keep_boj_group_binding();

-- The server passes a normalized observation from a successful crawler job.
CREATE FUNCTION catalog.stage_boj_contest(p_source jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE native_id bigint:=(p_source->>'sourceId')::bigint;
    fetched timestamptz:=(p_source->>'observedAt')::timestamptz;
    complete boolean:=(p_source->>'complete')::boolean;
    changed boolean;
BEGIN
    IF jsonb_typeof(p_source->'slots') IS DISTINCT FROM 'array'
        OR jsonb_array_length(p_source->'slots') NOT BETWEEN 1 AND 500
        OR (complete AND EXISTS(SELECT 1 FROM jsonb_array_elements(p_source->'slots') s WHERE s->>'title' IS NULL))
    THEN RAISE EXCEPTION 'Invalid BOJ slot observation' USING ERRCODE='22023'; END IF;

    INSERT INTO app_private.boj_contest_sources AS current(source_id,fetched_url,title,observed_at,complete_at,is_complete)
        VALUES(native_id,p_source->>'fetchedUrl',p_source->>'title',fetched,CASE WHEN complete THEN fetched END,complete)
        ON CONFLICT (source_id) DO UPDATE SET fetched_url=EXCLUDED.fetched_url,title=EXCLUDED.title,
            observed_at=EXCLUDED.observed_at,is_complete=EXCLUDED.is_complete,
            complete_at=COALESCE(EXCLUDED.complete_at,current.complete_at)
        WHERE current.observed_at<EXCLUDED.observed_at RETURNING true INTO changed;
    IF changed IS DISTINCT FROM true THEN RETURN jsonb_build_object('sourceId',native_id,'updated',false); END IF;

    INSERT INTO app_private.boj_problems AS current(problem_id,title,observed_at)
        SELECT (s->>'number')::bigint,s->>'title',fetched FROM jsonb_array_elements(p_source->'slots') s
        WHERE s->>'title' IS NOT NULL ORDER BY (s->>'number')::bigint
        ON CONFLICT(problem_id) DO UPDATE SET title=EXCLUDED.title,observed_at=EXCLUDED.observed_at
        WHERE current.detail_fetched_at IS NULL AND current.observed_at<EXCLUDED.observed_at;
    DELETE FROM app_private.boj_contest_slots WHERE source_id=native_id;
    INSERT INTO app_private.boj_contest_slots(source_id,position,label,displayed_number,boj_problem_id)
        SELECT native_id,(position-1)::integer,s->>'label',(s->>'number')::bigint,
            CASE WHEN s->>'title' IS NOT NULL THEN (s->>'number')::bigint END
        FROM jsonb_array_elements(p_source->'slots') WITH ORDINALITY AS slots(s,position);
    RETURN jsonb_build_object('sourceId',native_id,'updated',true);
END;
$$;

CREATE FUNCTION catalog.stage_boj_problem(p_problem jsonb) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
    WITH upsert AS (
        INSERT INTO app_private.boj_problems AS current(problem_id,title,metadata,observed_at,detail_fetched_at)
        VALUES ((p_problem->>'problemId')::bigint,p_problem->>'title',p_problem->'metadata',
                (p_problem->>'observedAt')::timestamptz,(p_problem->>'observedAt')::timestamptz)
        ON CONFLICT(problem_id) DO UPDATE SET title=EXCLUDED.title,metadata=current.metadata||jsonb_strip_nulls(EXCLUDED.metadata),
            observed_at=greatest(current.observed_at,EXCLUDED.observed_at),detail_fetched_at=EXCLUDED.detail_fetched_at
        WHERE current.detail_fetched_at IS NULL OR current.detail_fetched_at<EXCLUDED.detail_fetched_at
        RETURNING problem_id)
    SELECT jsonb_build_object('problemId',p_problem->'problemId','updated',EXISTS(SELECT 1 FROM upsert));
$$;

CREATE FUNCTION catalog.admin_publish_boj(p_contest_id uuid,p_version text,p_group_id text,p_source jsonb,
    p_matches jsonb,p_reviewer uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE selected catalog.contests; native_id bigint:=(p_source->>'sourceId')::bigint; item jsonb;
    version text; target uuid; boj_id bigint; part integer; proposed_title text; membership_count integer;
BEGIN
    SELECT * INTO selected FROM catalog.contests WHERE id=p_contest_id AND is_public FOR UPDATE;
    IF NOT FOUND OR selected.updated_at::text IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION 'Contest changed while reviewing' USING ERRCODE='40001';
    END IF;
    IF p_group_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
        COALESCE(selected.payload->'groups','[]')) g WHERE g->>'id'=p_group_id) THEN
        RAISE EXCEPTION 'Choose a group belonging to this contest' USING ERRCODE='22023';
    END IF;
    IF jsonb_typeof(p_matches) IS DISTINCT FROM 'array' OR jsonb_array_length(p_matches)>500 THEN
        RAISE EXCEPTION 'Invalid BOJ match list' USING ERRCODE='22023';
    END IF;
    PERFORM catalog.stage_boj_contest(p_source);
    PERFORM 1 FROM app_private.boj_contest_sources WHERE source_id=native_id AND
        observed_at=(p_source->>'observedAt')::timestamptz FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'BOJ source changed while reviewing' USING ERRCODE='40001'; END IF;
    INSERT INTO app_private.catalog_boj_contests(source_id,contest_id,group_id,reviewed_by)
        VALUES(native_id,p_contest_id,p_group_id,p_reviewer) ON CONFLICT(source_id) DO NOTHING;
    IF NOT EXISTS (SELECT 1 FROM app_private.catalog_boj_contests WHERE source_id=native_id
        AND contest_id=p_contest_id AND group_id IS NOT DISTINCT FROM p_group_id) THEN
        RAISE EXCEPTION 'BOJ source already belongs to another catalog scope' USING ERRCODE='23505';
    END IF;

    -- Lock every shared task first and verify all expected versions before editing any task.
    FOR item IN SELECT value FROM jsonb_array_elements(p_matches) ORDER BY value->>'problemId' LOOP
        target:=(item->>'problemId')::uuid;
        SELECT p.updated_at::text INTO version FROM catalog.problems p WHERE p.id=target AND p.is_public FOR UPDATE;
        SELECT count(*) INTO membership_count FROM catalog.contest_problems m WHERE m.contest_id=p_contest_id
            AND m.problem_id=target AND m.is_public AND m.group_id IS NOT DISTINCT FROM p_group_id;
        IF membership_count=0 THEN RAISE EXCEPTION 'Match must target a contest member in scope' USING ERRCODE='22023'; END IF;
        IF version IS NULL OR version IS DISTINCT FROM item->>'version' THEN
            RAISE EXCEPTION 'Problem changed while reviewing' USING ERRCODE='40001';
        END IF;
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(p_matches) ORDER BY (value->>'bojId')::bigint LOOP
        target:=(item->>'problemId')::uuid;
        boj_id:=(item->>'bojId')::bigint;
        part:=(item->>'partOrder')::integer;
        SELECT b.title INTO proposed_title FROM app_private.boj_contest_slots s
            JOIN app_private.boj_problems b ON b.problem_id=s.boj_problem_id
            WHERE s.source_id=native_id AND s.boj_problem_id=boj_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Match must use a linked BOJ slot' USING ERRCODE='22023'; END IF;
        IF EXISTS (SELECT 1 FROM app_private.catalog_boj_problems b WHERE b.catalog_problem_id=target
            AND b.boj_problem_id=boj_id AND b.part_order IS DISTINCT FROM part) THEN
            RAISE EXCEPTION 'The BOJ relationship is already recorded differently' USING ERRCODE='23505';
        END IF;
        INSERT INTO app_private.catalog_boj_problems(catalog_problem_id,boj_problem_id,part_order,preferred,evidence,reviewed_by)
            VALUES(target,boj_id,part,part IS NULL AND NOT EXISTS (
                SELECT 1 FROM app_private.catalog_boj_problems b WHERE b.catalog_problem_id=target AND b.preferred),
                item->>'evidence',p_reviewer)
            ON CONFLICT(catalog_problem_id,boj_problem_id) DO NOTHING;
        IF part IS NULL AND EXISTS (SELECT 1 FROM app_private.catalog_boj_problems b
            WHERE b.catalog_problem_id=target AND b.boj_problem_id=boj_id AND b.preferred)
        THEN
            UPDATE catalog.problems SET
                payload=jsonb_set(payload,'{title}',to_jsonb(proposed_title)),
                refresh_policy=jsonb_set(refresh_policy,'{fields}',COALESCE(refresh_policy->'fields','{}')||
                    jsonb_build_object('title',jsonb_build_object('source','boj','url','https://acmicpc.net/problem/'||boj_id,
                        'value',proposed_title,'fetchedAt',(SELECT COALESCE(detail_fetched_at,observed_at)
                            FROM app_private.boj_problems WHERE problem_id=boj_id))))
                    || '{"source":"boj"}'::jsonb
            WHERE id=target AND NOT COALESCE(refresh_policy->'manual' ? 'title',false);
        END IF;
        UPDATE catalog.problems SET updated_at=clock_timestamp() WHERE id=target;
    END LOOP;
    UPDATE catalog.contests SET updated_at=clock_timestamp() WHERE id=p_contest_id;
    RETURN jsonb_build_object('contestId',p_contest_id,'sourceId',native_id,'matches',jsonb_array_length(p_matches));
END;
$$;

CREATE FUNCTION catalog.boj_problem_links(p_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('preferred',max('https://acmicpc.net/problem/'||b.boj_problem_id) FILTER (WHERE b.preferred),
        'parts',COALESCE(jsonb_agg(jsonb_build_object('url','https://acmicpc.net/problem/'||b.boj_problem_id,
                'order',b.part_order) ORDER BY b.part_order) FILTER (WHERE b.part_order IS NOT NULL),'[]'))
    FROM app_private.catalog_boj_problems b JOIN catalog.problems p ON p.id=b.catalog_problem_id
    WHERE p.id=p_id AND p.is_public;
$$;
CREATE FUNCTION catalog.boj_contest_links(p_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_object_agg(coalesce(b.group_id,''),'https://acmicpc.net/category/detail/'||b.source_id),'{}')
    FROM app_private.catalog_boj_contests b JOIN catalog.contests c ON c.id=b.contest_id
    WHERE c.id=p_id AND c.is_public;
$$;
CREATE OR REPLACE FUNCTION catalog.problem_json(problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',p.id)||p.payload
        || CASE WHEN links->>'preferred' IS NULL THEN '{}' ELSE
                jsonb_build_object('link',(p.payload->'link')||jsonb_build_object('boj',links->>'preferred')) END
        || CASE WHEN links->'parts'='[]'::jsonb THEN '{}' ELSE jsonb_build_object('bojParts',links->'parts') END
    FROM catalog.problems p CROSS JOIN LATERAL (SELECT catalog.boj_problem_links(p.id) links) l
    WHERE p.id=problem_id AND p.payload IS NOT NULL;
$$;
CREATE OR REPLACE FUNCTION catalog.contest_json(contest_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE entity catalog.contests%ROWTYPE; problem_list jsonb; material_list jsonb; problem_materials jsonb; links jsonb; result jsonb;
BEGIN
    SELECT * INTO entity FROM catalog.contests c WHERE c.id=contest_id;
    IF NOT FOUND OR entity.payload IS NULL THEN RETURN NULL; END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('problemId',cp.problem_id,'index',cp.problem_index)
        || CASE WHEN cp.group_id IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('groupId',cp.group_id) END
        ORDER BY cp.position),'[]'::jsonb) INTO problem_list
        FROM catalog.contest_problems cp JOIN catalog.problems p ON p.id=cp.problem_id
        WHERE cp.contest_id=entity.id AND cp.position IS NOT NULL AND p.payload IS NOT NULL;
    SELECT COALESCE(jsonb_agg(m.payload ORDER BY m.position),'[]'::jsonb) INTO material_list
        FROM catalog.materials m WHERE m.contest_id=entity.id AND m.problem_id IS NULL
        AND m.position IS NOT NULL AND m.payload IS NOT NULL;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('problemId',m.problem_id)||m.payload ORDER BY m.position),'[]'::jsonb)
        INTO problem_materials FROM catalog.materials m JOIN catalog.problems p ON p.id=m.problem_id
        WHERE m.contest_id=entity.id AND m.problem_id IS NOT NULL AND m.position IS NOT NULL
        AND m.payload IS NOT NULL AND p.payload IS NOT NULL
        AND EXISTS (SELECT 1 FROM catalog.contest_problems cp WHERE cp.contest_id=entity.id AND cp.problem_id=m.problem_id);
    IF (entity.problem_count IS NOT NULL AND jsonb_array_length(problem_list)<>entity.problem_count)
        OR (entity.material_count IS NOT NULL AND jsonb_array_length(material_list)<>entity.material_count)
        OR (entity.problem_material_count IS NOT NULL AND jsonb_array_length(problem_materials)<>entity.problem_material_count)
        THEN RETURN NULL;
    END IF;
    links:=catalog.boj_contest_links(entity.id);
    result:=jsonb_build_object('id',entity.id)||entity.payload||jsonb_build_object(
        'problems',CASE WHEN entity.problem_count IS NULL THEN 'null'::jsonb ELSE problem_list END,
        'materials',CASE WHEN entity.material_count IS NULL THEN 'null'::jsonb ELSE material_list END)
        || CASE WHEN entity.problem_material_count IS NULL THEN '{}'::jsonb
                ELSE jsonb_build_object('problemMaterials',problem_materials) END;
    IF links ? '' THEN result:=jsonb_set(result,'{link,boj}',links->''); END IF;
    IF result ? 'groups' AND links<>'{}'::jsonb THEN
        result:=jsonb_set(result,'{groups}',(SELECT COALESCE(jsonb_agg(
            CASE WHEN links ? (value->>'id') THEN jsonb_set(value,'{link,boj}',links->(value->>'id'))
                 ELSE value END ORDER BY position),'[]')
            FROM jsonb_array_elements(result->'groups') WITH ORDINALITY items(value,position)));
    END IF;
    RETURN result;
END;
$$;

REVOKE ALL ON FUNCTION catalog.stage_boj_contest(jsonb),catalog.stage_boj_problem(jsonb),
    catalog.admin_publish_boj(uuid,text,text,jsonb,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.stage_boj_contest(jsonb),catalog.stage_boj_problem(jsonb),
    catalog.admin_publish_boj(uuid,text,text,jsonb,jsonb,uuid) TO service_role;
REVOKE ALL ON FUNCTION catalog.boj_problem_links(uuid),catalog.boj_contest_links(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION catalog.boj_problem_links(uuid),catalog.boj_contest_links(uuid)
    TO anon,authenticated,service_role;

-- Existing admin and personal import callers can round-trip catalog objects.
CREATE FUNCTION app_private.boj_writable_contest(data jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT (data #- '{link,boj}') ||
        CASE WHEN jsonb_typeof(data->'groups')='array' THEN jsonb_build_object('groups',
            (SELECT COALESCE(jsonb_agg(g #- '{link,boj}' ORDER BY n),'[]')
             FROM jsonb_array_elements(data->'groups') WITH ORDINALITY groups(g,n))) ELSE '{}' END;
$$;
CREATE FUNCTION app_private.boj_writable_problems(data jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT CASE WHEN jsonb_typeof(data)='array' THEN (SELECT
        COALESCE(jsonb_agg((entry-'bojParts') #- '{link,boj}' ORDER BY ordinality),'[]')
        FROM jsonb_array_elements(data) WITH ORDINALITY rows(entry,ordinality)) ELSE data END;
$$;
REVOKE ALL ON FUNCTION app_private.boj_writable_contest(jsonb),app_private.boj_writable_problems(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_private.boj_writable_contest(jsonb),app_private.boj_writable_problems(jsonb) TO service_role;

ALTER FUNCTION catalog.write_catalog(jsonb,jsonb,boolean) RENAME TO write_catalog_rows;
CREATE FUNCTION catalog.write_catalog(contests jsonb,problems jsonb,publish boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE cleaned_contests jsonb;
BEGIN
    IF jsonb_typeof(contests) IS DISTINCT FROM 'array' THEN
        RETURN catalog.write_catalog_rows(contests,problems,publish);
    END IF;
    SELECT COALESCE(jsonb_agg(app_private.boj_writable_contest(entry) ORDER BY ordinality),'[]')
        INTO cleaned_contests FROM jsonb_array_elements(contests) WITH ORDINALITY rows(entry,ordinality);
    RETURN catalog.write_catalog_rows(cleaned_contests,app_private.boj_writable_problems(problems),publish);
END;
$$;
REVOKE ALL ON FUNCTION catalog.write_catalog(jsonb,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.write_catalog(jsonb,jsonb,boolean) TO service_role;

ALTER FUNCTION catalog.admin_publish_with_refresh(jsonb,jsonb,jsonb,jsonb) RENAME TO admin_publish_refresh_rows;
CREATE FUNCTION catalog.admin_publish_with_refresh(p_contest jsonb,p_problems jsonb,p_versions jsonb,p_refresh jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT catalog.admin_publish_refresh_rows(app_private.boj_writable_contest(p_contest),
        app_private.boj_writable_problems(p_problems),p_versions,p_refresh);
$$;
REVOKE ALL ON FUNCTION catalog.admin_publish_with_refresh(jsonb,jsonb,jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_publish_with_refresh(jsonb,jsonb,jsonb,jsonb) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
