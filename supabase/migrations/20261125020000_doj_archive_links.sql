BEGIN;

CREATE OR REPLACE FUNCTION app_private.valid_json_links(value jsonb, fields text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE item jsonb; allowed text[]:=fields; doj_pattern text;
BEGIN
    IF fields @> ARRAY['cf','qoj','atcoder'] THEN
        IF value ? 'ojuz' THEN allowed:=array_append(allowed,'ojuz'); END IF;
        IF value ? 'doj' THEN
            allowed:=array_append(allowed,'doj');
            doj_pattern:=CASE WHEN 'official'=ANY(fields)
                THEN '^https://doj\.kr/en/(contests/[A-Za-z0-9][A-Za-z0-9_-]{0,99}|categories(/[A-Za-z0-9][A-Za-z0-9_-]{0,99}){2,12})$'
                ELSE '^https://doj\.kr/en/problems/[1-9][0-9]{0,14}$' END;
            IF value->>'doj' IS NOT NULL AND value->>'doj' !~ doj_pattern THEN RETURN false; END IF;
        END IF;
    END IF;
    IF NOT app_private.has_json_fields(value,allowed) THEN RETURN false; END IF;
    FOR item IN SELECT entry.value FROM jsonb_each(value) entry LOOP
        IF item <> 'null'::jsonb AND NOT app_private.https_json_url(item) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;

CREATE FUNCTION catalog.publish_doj_archives(p_editions jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE edition jsonb; task jsonb; source_url text; task_url text; group_key text;
    contest catalog.contests; problem catalog.problems; standalone catalog.problems;
    existing_url text; groups jsonb; editions integer:=0; links integer:=0;
BEGIN
    IF jsonb_typeof(p_editions) IS DISTINCT FROM 'array' OR jsonb_array_length(p_editions) NOT BETWEEN 1 AND 150 THEN
        RAISE EXCEPTION 'Provide one to 150 reviewed DOJ archive editions' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('doj-archive-publication',0));
    FOR edition IN SELECT value FROM jsonb_array_elements(p_editions) ORDER BY value->>'url' LOOP
        source_url:=edition->>'url';
        group_key:=edition->>'groupId';
        IF COALESCE(source_url,'') !~ '^https://doj\.kr/en/categories(/[A-Za-z0-9][A-Za-z0-9_-]{0,99}){2,12}$'
            OR jsonb_typeof(edition->'problems') IS DISTINCT FROM 'array'
            OR jsonb_array_length(edition->'problems') NOT BETWEEN 1 AND 100 THEN
            RAISE EXCEPTION 'Invalid DOJ archive or problem list' USING ERRCODE='22023';
        END IF;
        SELECT * INTO contest FROM catalog.contests c WHERE c.id=(edition->>'contestId')::uuid AND c.is_public
            AND c.payload->'category'->>0 IN ('ICPC','Olympiad') FOR UPDATE;
        IF NOT FOUND OR contest.payload->>'title' IS DISTINCT FROM edition->>'title' THEN
            RAISE EXCEPTION 'The curated contest changed for %',source_url USING ERRCODE='40001';
        END IF;
        IF group_key IS NULL THEN
            existing_url:=contest.payload->'link'->>'doj';
            IF existing_url IS NULL THEN
                UPDATE catalog.contests SET payload=jsonb_set(payload,'{link,doj}',to_jsonb(source_url))
                    WHERE id=contest.id;
            END IF;
        ELSE
            SELECT g->'link'->>'doj' INTO existing_url FROM jsonb_array_elements(contest.payload->'groups') g
                WHERE g->>'id'=group_key;
            IF NOT FOUND THEN RAISE EXCEPTION 'The curated contest group changed' USING ERRCODE='40001'; END IF;
            IF existing_url IS NULL THEN
                SELECT jsonb_agg(CASE WHEN g->>'id'=group_key THEN jsonb_set(g,'{link,doj}',to_jsonb(source_url))
                    ELSE g END ORDER BY position) INTO groups
                FROM jsonb_array_elements(contest.payload->'groups') WITH ORDINALITY items(g,position);
                UPDATE catalog.contests SET payload=jsonb_set(payload,'{groups}',groups) WHERE id=contest.id;
            END IF;
        END IF;
        IF existing_url IS NOT NULL AND existing_url<>source_url THEN
            RAISE EXCEPTION 'The curated contest already has a different DOJ link for %',source_url USING ERRCODE='23505';
        END IF;
        FOR task IN SELECT value FROM jsonb_array_elements(edition->'problems') ORDER BY value->>'dojId' LOOP
            task_url:='https://doj.kr/en/problems/'||(task->>'dojId');
            IF COALESCE(task->>'dojId','') !~ '^[1-9][0-9]{0,14}$' THEN
                RAISE EXCEPTION 'Invalid native DOJ problem ID' USING ERRCODE='22023';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(task_url,0));
            SELECT p.* INTO problem FROM catalog.problems p JOIN catalog.contest_problems m ON m.problem_id=p.id
                WHERE p.id=(task->>'problemId')::uuid AND p.is_public AND m.is_public AND m.contest_id=contest.id
                    AND (group_key IS NULL OR m.group_id=group_key) FOR UPDATE OF p;
            IF NOT FOUND OR problem.payload->>'title' IS DISTINCT FROM task->>'title' THEN
                RAISE EXCEPTION 'The curated problem changed for %',task_url USING ERRCODE='40001';
            END IF;
            IF problem.payload->'link'->>'doj'=task_url THEN CONTINUE; END IF;
            IF problem.payload->'link'->>'doj' IS NOT NULL THEN
                RAISE EXCEPTION 'The curated problem already has a different DOJ link for %',task_url USING ERRCODE='23505';
            END IF;
            SELECT * INTO standalone FROM catalog.problems p WHERE p.payload->'link'->>'doj'=task_url FOR UPDATE;
            IF FOUND THEN
                IF EXISTS(SELECT 1 FROM jsonb_each_text(standalone.payload->'link') x WHERE key<>'doj' AND value IS NOT NULL)
                    OR EXISTS(SELECT 1 FROM catalog.contest_problems WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM catalog.materials WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM catalog.statement_variants WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM archive.snapshots WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM app_private.catalog_boj_problems WHERE catalog_problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM user_data.problem_progress WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM user_data.problem_notes WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM user_data.practice_attempts WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM user_data.difficulty_votes WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM user_data.difficulty_tier_votes WHERE problem_id=standalone.id)
                    OR EXISTS(SELECT 1 FROM app_private.doj_solvedac_links WHERE problem_id=standalone.id) THEN
                    RAISE EXCEPTION 'DOJ problem already has references that require a reviewed merge: %',task_url USING ERRCODE='23505';
                END IF;
                UPDATE catalog.problems SET is_public=false,payload=payload #- '{link,doj}' WHERE id=standalone.id;
            END IF;
            UPDATE catalog.problems SET payload=jsonb_set(payload,'{link,doj}',to_jsonb(task_url)),
                doj_metadata=COALESCE(doj_metadata,standalone.doj_metadata) WHERE id=problem.id;
            links:=links+1;
        END LOOP;
        editions:=editions+1;
    END LOOP;
    RETURN jsonb_build_object('editions',editions,'problemLinksAdded',links);
END;
$$;

REVOKE ALL ON FUNCTION catalog.publish_doj_archives(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.publish_doj_archives(jsonb) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
