BEGIN;

-- Build the set of visible problem IDs once for the curated catalog.
CREATE OR REPLACE FUNCTION catalog.read_catalog(curated_only boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE contest_list jsonb; problem_list jsonb;
BEGIN
    WITH entities AS MATERIALIZED (
        SELECT c.id,c.created_at,catalog.contest_json(c.id) AS data
        FROM catalog.contests c
        WHERE curated_only IS FALSE OR c.payload->'category'->>0 IN ('ICPC','Olympiad')
    )
    SELECT COALESCE(jsonb_agg(data ORDER BY created_at,id),'[]')
        INTO contest_list FROM entities WHERE data IS NOT NULL;

    WITH referenced AS MATERIALIZED (
        SELECT DISTINCT (entry->>'problemId')::uuid AS id
        FROM jsonb_array_elements(contest_list) c
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(NULLIF(c->'problems','null'),'[]')) entry
        WHERE curated_only IS NOT FALSE
    )
    SELECT COALESCE(jsonb_agg(catalog.problem_json(p.id) ORDER BY p.created_at,p.id),'[]')
        INTO problem_list FROM catalog.problems p
        LEFT JOIN referenced r ON r.id=p.id
        WHERE p.payload IS NOT NULL AND (curated_only IS FALSE OR r.id IS NOT NULL);

    RETURN jsonb_build_object('contests',contest_list,'problems',problem_list);
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
