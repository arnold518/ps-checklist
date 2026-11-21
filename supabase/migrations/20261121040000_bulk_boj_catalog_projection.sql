BEGIN;

-- Resolve approved BOJ links in one indexed scan for the full catalog.
CREATE FUNCTION catalog.visible_boj_problem_links()
RETURNS TABLE(problem_id uuid,preferred_url text,parts jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT b.catalog_problem_id,
        max('https://acmicpc.net/problem/'||b.boj_problem_id) FILTER (WHERE b.preferred),
        jsonb_agg(jsonb_build_object('url','https://acmicpc.net/problem/'||b.boj_problem_id,
            'order',b.part_order) ORDER BY b.part_order) FILTER (WHERE b.part_order IS NOT NULL)
    FROM app_private.catalog_boj_problems b JOIN catalog.problems p ON p.id=b.catalog_problem_id
    WHERE p.is_public
    GROUP BY b.catalog_problem_id;
$$;
REVOKE ALL ON FUNCTION catalog.visible_boj_problem_links() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION catalog.visible_boj_problem_links() TO anon,authenticated,service_role;

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
    SELECT COALESCE(jsonb_agg((jsonb_build_object('id',p.id)||p.payload
            || CASE WHEN b.preferred_url IS NULL THEN '{}' ELSE
                jsonb_build_object('link',(p.payload->'link')||jsonb_build_object('boj',b.preferred_url)) END
            || CASE WHEN b.parts IS NULL THEN '{}' ELSE jsonb_build_object('bojParts',b.parts) END)
        ORDER BY p.created_at,p.id),'[]')
        INTO problem_list FROM catalog.problems p
        LEFT JOIN referenced r ON r.id=p.id
        LEFT JOIN catalog.visible_boj_problem_links() b ON b.problem_id=p.id
        WHERE p.payload IS NOT NULL AND (curated_only IS FALSE OR r.id IS NOT NULL);

    RETURN jsonb_build_object('contests',contest_list,'problems',problem_list);
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
