BEGIN;

-- Collect personal contests and their problems before merging them into the
-- curated catalog. Each catalog array is scanned and extended only once.
CREATE OR REPLACE FUNCTION user_data.read_state()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE
    owner_id uuid := auth.uid();
    base_catalog jsonb;
    extra_contests jsonb;
    extra_problems jsonb;
BEGIN
    IF owner_id IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    base_catalog := catalog.read_catalog(true);

    WITH selected AS (
        SELECT contest_id FROM user_data.saved_contests WHERE user_id=owner_id
        UNION
        SELECT contest_id FROM user_data.practice_sessions WHERE user_id=owner_id
    ), curated AS MATERIALIZED (
        SELECT (entry->>'id')::uuid AS id FROM jsonb_array_elements(base_catalog->'contests') AS entry
    ), extras AS MATERIALIZED (
        SELECT s.contest_id,catalog.contest_json(s.contest_id) AS data
        FROM selected s LEFT JOIN curated c ON c.id=s.contest_id
        WHERE c.id IS NULL
    )
    SELECT COALESCE(jsonb_agg(data ORDER BY contest_id),'[]'::jsonb)
    INTO extra_contests FROM extras WHERE data IS NOT NULL;

    WITH referenced AS (
        SELECT DISTINCT (entry->>'problemId')::uuid AS id
        FROM jsonb_array_elements(extra_contests) AS contest
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(NULLIF(contest->'problems','null'),'[]')) AS entry
    ), curated AS MATERIALIZED (
        SELECT (entry->>'id')::uuid AS id FROM jsonb_array_elements(base_catalog->'problems') AS entry
    ), extras AS MATERIALIZED (
        SELECT r.id,catalog.problem_json(r.id) AS data
        FROM referenced r LEFT JOIN curated c ON c.id=r.id
        WHERE c.id IS NULL
    )
    SELECT COALESCE(jsonb_agg(data ORDER BY id),'[]'::jsonb)
    INTO extra_problems FROM extras WHERE data IS NOT NULL;

    RETURN jsonb_build_object(
        'userId',owner_id,
        'catalog',jsonb_build_object(
            'contests',(base_catalog->'contests') || extra_contests,
            'problems',(base_catalog->'problems') || extra_problems),
        'preferences',COALESCE((
            SELECT payload FROM user_data.preferences WHERE user_id=owner_id),'{"views":{}}'::jsonb),
        'progress',COALESCE((
            SELECT jsonb_agg(jsonb_build_object('problemId',p.problem_id,'status',p.payload->'status'))
            FROM user_data.problem_progress p WHERE p.user_id=owner_id),'[]'::jsonb),
        'savedContests',COALESCE((
            SELECT jsonb_agg(jsonb_build_object('contestId',s.contest_id,'platforms',s.payload->'platforms') ORDER BY s.created_at,s.id)
            FROM user_data.saved_contests s WHERE s.user_id=owner_id),'[]'::jsonb),
        'practiceRecords',COALESCE((
            SELECT jsonb_agg(jsonb_build_object('id',s.id,'contestId',s.contest_id,'date',s.payload->>'date') ORDER BY s.created_at,s.id)
            FROM user_data.practice_sessions s WHERE s.user_id=owner_id),'[]'::jsonb));
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
