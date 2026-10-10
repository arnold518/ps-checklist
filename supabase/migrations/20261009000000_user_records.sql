-- First user-data version: current problem status, platform selections,
-- one dated practice record per contest, and per-tab tree preferences.
BEGIN;

CREATE FUNCTION app_private.valid_platforms(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) NOT BETWEEN 1 AND 2 THEN RETURN false; END IF;
    RETURN NOT EXISTS (SELECT 1 FROM jsonb_array_elements(value) item WHERE item NOT IN ('"cf"'::jsonb, '"atcoder"'::jsonb))
        AND (SELECT count(*) = count(DISTINCT item) FROM jsonb_array_elements(value) item);
END;
$$;

CREATE FUNCTION app_private.valid_view(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE path_item jsonb;
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'object' OR value - ARRAY['expandedPaths','visibleContestIds'] <> '{}'::jsonb
        OR jsonb_typeof(value->'expandedPaths') IS DISTINCT FROM 'array'
        OR jsonb_typeof(value->'visibleContestIds') IS DISTINCT FROM 'array' THEN RETURN false; END IF;
    IF jsonb_array_length(value->'expandedPaths') > 2000 OR jsonb_array_length(value->'visibleContestIds') > 5000 THEN RETURN false; END IF;
    FOR path_item IN SELECT jsonb_array_elements(value->'expandedPaths') LOOP
        IF jsonb_typeof(path_item) IS DISTINCT FROM 'array' OR jsonb_array_length(path_item) NOT BETWEEN 1 AND 32 THEN RETURN false; END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(path_item) part WHERE jsonb_typeof(part) <> 'string' OR length(part#>>'{}') > 300) THEN RETURN false; END IF;
    END LOOP;
    RETURN NOT EXISTS (SELECT 1 FROM jsonb_array_elements(value->'visibleContestIds') item
        WHERE jsonb_typeof(item) <> 'string' OR (item#>>'{}') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$');
END;
$$;

CREATE FUNCTION app_private.valid_preferences(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE item record;
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'object' OR value - 'views' <> '{}'::jsonb OR jsonb_typeof(value->'views') IS DISTINCT FROM 'object' THEN RETURN false; END IF;
    FOR item IN SELECT * FROM jsonb_each(value->'views') LOOP
        IF item.key NOT IN ('icpc','olympiad','platforms') OR NOT app_private.valid_view(item.value) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;

CREATE FUNCTION app_private.valid_practice_date(value text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF value IS NULL OR value !~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN false; END IF;
    RETURN to_char(value::date, 'YYYY-MM-DD') = value;
EXCEPTION WHEN datetime_field_overflow OR invalid_datetime_format THEN RETURN false;
END;
$$;

ALTER TABLE user_data.problem_progress ALTER COLUMN payload SET NOT NULL;
ALTER TABLE user_data.problem_progress ADD CONSTRAINT progress_shape CHECK (
    jsonb_typeof(payload) = 'object' AND payload - 'status' = '{}'::jsonb
    AND payload ? 'status' AND payload->'status' IN ('0'::jsonb, '1'::jsonb, '2'::jsonb, '3'::jsonb));
ALTER TABLE user_data.saved_contests ALTER COLUMN payload SET NOT NULL;
ALTER TABLE user_data.saved_contests ADD CONSTRAINT saved_shape CHECK (
    jsonb_typeof(payload) = 'object' AND payload - 'platforms' = '{}'::jsonb
    AND app_private.valid_platforms(payload->'platforms'));
ALTER TABLE user_data.preferences ALTER COLUMN payload SET NOT NULL;
ALTER TABLE user_data.preferences ADD CONSTRAINT preferences_shape CHECK (app_private.valid_preferences(payload));
ALTER TABLE user_data.practice_sessions ALTER COLUMN contest_id SET NOT NULL;
ALTER TABLE user_data.practice_sessions ALTER COLUMN payload SET NOT NULL;
ALTER TABLE user_data.practice_sessions ADD CONSTRAINT practice_shape CHECK (
    jsonb_typeof(payload) = 'object' AND payload - 'date' = '{}'::jsonb
    AND jsonb_typeof(payload->'date') = 'string' AND app_private.valid_practice_date(payload->>'date'));
ALTER TABLE user_data.practice_sessions ADD CONSTRAINT one_practice_per_contest UNIQUE(user_id, contest_id);

-- New user references must point to records visible to that user.
DROP POLICY own_records ON user_data.problem_progress;
CREATE POLICY own_records ON user_data.problem_progress TO authenticated USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM catalog.problems p WHERE p.id = problem_id));
DROP POLICY own_records ON user_data.saved_contests;
CREATE POLICY own_records ON user_data.saved_contests TO authenticated USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id = contest_id));
DROP POLICY own_records ON user_data.practice_sessions;
CREATE POLICY own_records ON user_data.practice_sessions TO authenticated USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id = contest_id));

CREATE FUNCTION user_data.read_state()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER AS $$
DECLARE result jsonb; v_catalog jsonb; entity jsonb; item uuid; problem_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    v_catalog := catalog.read_catalog(true);
    FOR item IN SELECT contest_id FROM user_data.saved_contests UNION SELECT contest_id FROM user_data.practice_sessions LOOP
        IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_catalog->'contests') c WHERE c->>'id' = item::text) THEN
            entity := catalog.contest_json(item);
            IF entity IS NULL THEN CONTINUE; END IF;
            v_catalog := jsonb_set(v_catalog, '{contests}', (v_catalog->'contests') || jsonb_build_array(entity));
            FOR problem_id IN SELECT (p->>'problemId')::uuid FROM jsonb_array_elements(COALESCE(NULLIF(entity->'problems','null'::jsonb),'[]'::jsonb)) p LOOP
                IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_catalog->'problems') p WHERE p->>'id' = problem_id::text) THEN
                    v_catalog := jsonb_set(v_catalog, '{problems}', (v_catalog->'problems') || jsonb_build_array(catalog.problem_json(problem_id)));
                END IF;
            END LOOP;
        END IF;
    END LOOP;
    RETURN jsonb_build_object(
        'userId', auth.uid(), 'catalog', v_catalog,
        'preferences', COALESCE((SELECT payload FROM user_data.preferences), '{"views":{}}'::jsonb),
        'progress', COALESCE((SELECT jsonb_agg(jsonb_build_object('problemId', p.problem_id, 'status', payload->'status')) FROM user_data.problem_progress p), '[]'::jsonb),
        'savedContests', COALESCE((SELECT jsonb_agg(jsonb_build_object('contestId', contest_id, 'platforms', payload->'platforms') ORDER BY created_at,id) FROM user_data.saved_contests), '[]'::jsonb),
        'practiceRecords', COALESCE((SELECT jsonb_agg(jsonb_build_object('id',id,'contestId',contest_id,'date',payload->>'date') ORDER BY created_at,id) FROM user_data.practice_sessions), '[]'::jsonb));
END;
$$;

CREATE FUNCTION user_data.set_progress(p_problem_id uuid, p_status integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_status IS NULL OR p_status NOT BETWEEN 0 AND 3 THEN RAISE EXCEPTION 'Invalid status' USING ERRCODE='22023'; END IF;
    INSERT INTO user_data.problem_progress(user_id,problem_id,payload) VALUES(auth.uid(),p_problem_id,jsonb_build_object('status',p_status))
        ON CONFLICT(user_id,problem_id) DO UPDATE SET payload=EXCLUDED.payload;
    RETURN jsonb_build_object('problemId',p_problem_id,'status',p_status);
END;
$$;

CREATE FUNCTION user_data.save_view(p_tab text, p_view jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_tab IS NULL OR p_tab NOT IN ('icpc','olympiad','platforms') OR NOT app_private.valid_view(p_view) THEN RAISE EXCEPTION 'Invalid view' USING ERRCODE='22023'; END IF;
    INSERT INTO user_data.preferences(user_id,payload) VALUES(auth.uid(),jsonb_build_object('views',jsonb_build_object(p_tab,p_view)))
        ON CONFLICT(user_id) DO UPDATE SET payload=jsonb_set(user_data.preferences.payload,ARRAY['views',p_tab],p_view,true);
    RETURN p_view;
END;
$$;

CREATE FUNCTION user_data.create_practice(p_contest_id uuid, p_date text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE record_id uuid;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF NOT app_private.valid_practice_date(p_date) THEN RAISE EXCEPTION 'Invalid date' USING ERRCODE='22023'; END IF;
    IF NOT EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id=p_contest_id AND
        (c.payload->'category'->>0 IN ('ICPC','Olympiad') OR EXISTS(SELECT 1 FROM user_data.saved_contests s WHERE s.contest_id=c.id))) THEN
        RAISE EXCEPTION 'Select a contest from your lists' USING ERRCODE='42501';
    END IF;
    INSERT INTO user_data.practice_sessions(user_id,contest_id,payload) VALUES(auth.uid(),p_contest_id,jsonb_build_object('date',p_date)) RETURNING id INTO record_id;
    RETURN jsonb_build_object('id',record_id,'contestId',p_contest_id,'date',p_date);
END;
$$;

CREATE FUNCTION user_data.delete_practice(p_record_id uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE count_removed integer;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    DELETE FROM user_data.practice_sessions WHERE id=p_record_id;
    GET DIAGNOSTICS count_removed = ROW_COUNT;
    RETURN count_removed > 0;
END;
$$;

CREATE FUNCTION user_data.remove_saved(p_contest_id uuid, p_source text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder') THEN RAISE EXCEPTION 'Invalid platform' USING ERRCODE='22023'; END IF;
    DELETE FROM user_data.saved_contests WHERE contest_id=p_contest_id AND payload->'platforms' = jsonb_build_array(p_source);
    UPDATE user_data.saved_contests SET payload=jsonb_build_object('platforms',(payload->'platforms') - p_source)
        WHERE contest_id=p_contest_id AND payload->'platforms' ? p_source;
    RETURN true;
END;
$$;

-- A primary judge URL identifies an entity. Cross-judge equivalence remains
-- an explicit catalog decision; titles and contest positions are never keys.
CREATE UNIQUE INDEX contests_cf_identity ON catalog.contests((payload->'link'->>'cf')) WHERE payload->'link'->>'cf' IS NOT NULL;
CREATE UNIQUE INDEX contests_atcoder_identity ON catalog.contests((payload->'link'->>'atcoder')) WHERE payload->'link'->>'atcoder' IS NOT NULL;
CREATE UNIQUE INDEX problems_cf_identity ON catalog.problems((payload->'link'->>'cf')) WHERE payload->'link'->>'cf' IS NOT NULL;
CREATE UNIQUE INDEX problems_atcoder_identity ON catalog.problems((payload->'link'->>'atcoder')) WHERE payload->'link'->>'atcoder' IS NOT NULL;

CREATE FUNCTION catalog.import_round(p_source text, p_native jsonb, p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE entity_id uuid; native_problem jsonb; problem_record jsonb; problem_id uuid;
    basic_contest jsonb; memberships jsonb := '[]'; problems jsonb := '[]'; materials jsonb;
    existing_payload jsonb; platforms jsonb;
BEGIN
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder') OR p_native->>'source' IS DISTINCT FROM p_source
        OR jsonb_typeof(p_native->'problems') IS DISTINCT FROM 'array'
        OR jsonb_array_length(p_native->'problems')=0
        OR (p_native->>'problemCount')::integer IS DISTINCT FROM jsonb_array_length(p_native->'problems') THEN
        RAISE EXCEPTION 'Incomplete round' USING ERRCODE='22023';
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
                || jsonb_build_object(p_source,p_native->>'url','standings',(p_native->>'url')||'/standings'),
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA user_data FROM PUBLIC,anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA user_data TO authenticated,service_role;
GRANT USAGE ON SCHEMA app_private TO authenticated;
REVOKE ALL ON FUNCTION catalog.import_round(text,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.import_round(text,jsonb,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION app_private.valid_platforms(jsonb),app_private.valid_view(jsonb),app_private.valid_preferences(jsonb),app_private.valid_practice_date(text) TO authenticated,service_role;

COMMIT;
