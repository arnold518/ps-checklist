BEGIN;

CREATE FUNCTION catalog.boj_difficulty_targets(p_problem_ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'problemId',b.catalog_problem_id,'bojId',b.boj_problem_id,'preferred',b.preferred)
        ORDER BY b.boj_problem_id,b.catalog_problem_id),'[]')
    FROM app_private.catalog_boj_problems b
    JOIN catalog.problems p ON p.id=b.catalog_problem_id AND p.is_public
    WHERE cardinality(p_problem_ids) BETWEEN 1 AND 100 AND p.id=ANY(p_problem_ids)
        AND (b.preferred OR b.part_order IS NOT NULL);
$$;

REVOKE ALL ON FUNCTION catalog.boj_difficulty_targets(uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.boj_difficulty_targets(uuid[]) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
