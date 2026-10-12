-- Add oj.uz to personal Platforms using the existing shared catalog ingestion.
-- Existing selections, curated records, and practice references remain valid.
BEGIN;

CREATE OR REPLACE FUNCTION app_private.valid_platforms(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) NOT BETWEEN 1 AND 3 THEN RETURN false; END IF;
    RETURN NOT EXISTS (SELECT 1 FROM jsonb_array_elements(value) item WHERE item NOT IN ('"cf"'::jsonb, '"atcoder"'::jsonb, '"ojuz"'::jsonb))
        AND (SELECT count(*) = count(DISTINCT item) FROM jsonb_array_elements(value) item);
END;
$$;

CREATE OR REPLACE FUNCTION user_data.remove_saved(p_contest_id uuid, p_source text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder','ojuz') THEN RAISE EXCEPTION 'Invalid platform' USING ERRCODE='22023'; END IF;
    DELETE FROM user_data.saved_contests WHERE contest_id=p_contest_id AND payload->'platforms' = jsonb_build_array(p_source);
    UPDATE user_data.saved_contests SET payload=jsonb_build_object('platforms',(payload->'platforms') - p_source)
        WHERE contest_id=p_contest_id AND payload->'platforms' ? p_source;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION catalog.import_round(p_source text, p_native jsonb, p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE entity_id uuid; native_problem jsonb; problem_record jsonb; problem_id uuid;
    basic_contest jsonb; memberships jsonb := '[]'; problems jsonb := '[]'; materials jsonb;
    existing_payload jsonb; platforms jsonb;
BEGIN
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder','ojuz') OR p_native->>'source' IS DISTINCT FROM p_source
        OR jsonb_typeof(p_native->'problems') IS DISTINCT FROM 'array'
        OR jsonb_array_length(p_native->'problems')=0
        OR (p_native->>'problemCount')::integer IS DISTINCT FROM jsonb_array_length(p_native->'problems') THEN
        RAISE EXCEPTION 'Incomplete round' USING ERRCODE='22023';
    END IF;
    IF p_source='ojuz' AND (p_native->>'category' IS DISTINCT FROM 'source'
        OR COALESCE(p_native->>'url','') !~ '^https://oj\.uz/problems/source/[A-Za-z0-9][A-Za-z0-9_-]*$'
        OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_native->'problems') p
            WHERE COALESCE(p->>'url','') !~ '^https://oj\.uz/problem/view/[A-Za-z0-9][A-Za-z0-9_-]*$')) THEN
        RAISE EXCEPTION 'Invalid oj.uz contest or problem identity' USING ERRCODE='22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_native->>'url',0));
    SELECT id,payload INTO entity_id,existing_payload FROM catalog.contests WHERE payload->'link'->>p_source=p_native->>'url';
    IF entity_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM catalog.contests WHERE id=entity_id AND is_public) THEN
        RAISE EXCEPTION 'This contest is under catalog review' USING ERRCODE='42501';
    END IF;
    IF entity_id IS NULL OR existing_payload->'category'='null'::jsonb THEN
        entity_id := COALESCE(entity_id,gen_random_uuid());
        FOR native_problem IN SELECT value FROM jsonb_array_elements(p_native->'problems') LOOP
            PERFORM pg_advisory_xact_lock(hashtextextended(native_problem->>'url',0));
            SELECT id INTO problem_id FROM catalog.problems WHERE payload->'link'->>p_source=native_problem->>'url';
            IF problem_id IS NULL THEN
                problem_id := gen_random_uuid();
                problem_record := jsonb_build_object('id',problem_id,'title',native_problem->>'name','link',
                    jsonb_build_object('cf',NULL,'qoj',NULL,'atcoder',NULL) || jsonb_build_object(p_source,native_problem->>'url'));
            ELSE problem_record := catalog.problem_json(problem_id);
            END IF;
            problems := problems || jsonb_build_array(problem_record);
            memberships := memberships || jsonb_build_array(jsonb_build_object('problemId',problem_id,'index',native_problem->'index'));
        END LOOP;
        IF p_native->'materials'='null'::jsonb THEN materials := 'null'::jsonb;
        ELSE
            SELECT COALESCE(jsonb_agg(jsonb_build_object('role',m->>'role','title',m->>'title','language',m->'language','url',m->>'url') ORDER BY position),'[]'::jsonb)
                INTO materials FROM jsonb_array_elements(COALESCE(p_native->'materials','[]'::jsonb)) WITH ORDINALITY items(m,position) WHERE m->>'scope'='contest';
        END IF;
        basic_contest := jsonb_build_object('id',entity_id,'title',p_native->>'name',
            'year',CASE WHEN p_native->>'startTime' ~ '^\d{4}-' THEN left(p_native->>'startTime',4) END,'category',NULL,
            'link',COALESCE(existing_payload->'link',jsonb_build_object('cf',NULL,'qoj',NULL,'atcoder',NULL,'official',NULL,'standings',NULL))
                || jsonb_build_object(p_source,p_native->>'url','standings',
                    CASE WHEN p_source='ojuz' THEN existing_payload->'link'->>'standings'
                         ELSE (p_native->>'url')||'/standings' END),
            'problems',memberships,'materials',materials);
        PERFORM catalog.write_catalog(jsonb_build_array(basic_contest),problems,true);
    END IF;
    INSERT INTO user_data.saved_contests(user_id,contest_id,payload) VALUES(p_user_id,entity_id,jsonb_build_object('platforms',jsonb_build_array(p_source)))
        ON CONFLICT(user_id,contest_id) DO UPDATE SET payload=jsonb_build_object('platforms',
            CASE WHEN user_data.saved_contests.payload->'platforms' ? p_source THEN user_data.saved_contests.payload->'platforms'
            ELSE (user_data.saved_contests.payload->'platforms') || jsonb_build_array(p_source) END)
        RETURNING payload->'platforms' INTO platforms;
    basic_contest := catalog.contest_json(entity_id);
    SELECT COALESCE(jsonb_agg(catalog.problem_json((entry->>'problemId')::uuid)),'[]'::jsonb) INTO problems
        FROM jsonb_array_elements(COALESCE(NULLIF(basic_contest->'problems','null'::jsonb),'[]'::jsonb)) entry;
    RETURN jsonb_build_object('contest',basic_contest,'problems',problems,'saved',jsonb_build_object('contestId',entity_id,'platforms',platforms));
END;
$$;

REVOKE ALL ON FUNCTION catalog.import_round(text,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.import_round(text,jsonb,uuid) TO service_role;

COMMIT;
