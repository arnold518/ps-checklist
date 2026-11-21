BEGIN;

ALTER TABLE app_private.catalog_boj_contests DROP CONSTRAINT catalog_boj_contests_pkey;
CREATE INDEX catalog_boj_contests_by_source ON app_private.catalog_boj_contests(source_id);

CREATE OR REPLACE FUNCTION catalog.admin_publish_boj(p_contest_id uuid,p_version text,p_group_id text,p_source jsonb,
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
    -- The source row lock above serializes reviewers of the same BOJ edition.
    -- Some BOJ editions have one table for several separately catalogued days.
    IF EXISTS (
        SELECT 1 FROM app_private.catalog_boj_contests b
        JOIN catalog.contests other ON other.id=b.contest_id
        WHERE b.source_id=native_id AND (b.contest_id,b.group_id) IS DISTINCT FROM (p_contest_id,p_group_id)
          AND NOT COALESCE(
              b.group_id IS NULL AND p_group_id IS NULL
              AND selected.payload->'category'=other.payload->'category'
              AND selected.payload->>'year'=other.payload->>'year'
              AND selected.payload->>'contestLabel' ~ '^Day [1-9][0-9]*$'
              AND other.payload->>'contestLabel' ~ '^Day [1-9][0-9]*$'
              AND selected.payload->>'contestLabel'<>other.payload->>'contestLabel',false)
    ) THEN
        RAISE EXCEPTION 'BOJ source already belongs to another catalog scope' USING ERRCODE='23505';
    END IF;
    INSERT INTO app_private.catalog_boj_contests(source_id,contest_id,group_id,reviewed_by)
        VALUES(native_id,p_contest_id,p_group_id,p_reviewer) ON CONFLICT(contest_id,group_id) DO NOTHING;
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

COMMIT;
