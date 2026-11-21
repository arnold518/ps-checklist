BEGIN;

CREATE FUNCTION public.problem_difficulty_batch(p_problem_ids uuid[]) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE ratings jsonb;
BEGIN
    IF p_problem_ids IS NULL OR cardinality(p_problem_ids) NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION 'Provide one to one hundred problem IDs' USING ERRCODE='22023';
    END IF;
    SELECT COALESCE(jsonb_object_agg(p.id,jsonb_build_object(
        'level',d.level,'fetchedAt',d.fetched_at)),'{}') INTO ratings
    FROM catalog.problems p
    JOIN app_private.catalog_boj_problems b ON b.catalog_problem_id=p.id AND b.preferred
    JOIN app_private.boj_solvedac_links l ON l.boj_problem_id=b.boj_problem_id AND l.outcome='mapped'
    JOIN app_private.solvedac_difficulty d ON (d.provider_problem_id,d.sub_id)=(l.provider_problem_id,l.sub_id)
    WHERE p.id=ANY(p_problem_ids) AND p.is_public;
    RETURN ratings;
END;
$$;

CREATE FUNCTION public.problem_boj_difficulty(p_problem_id uuid,p_contest_id uuid,p_group_id text DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT public.problem_difficulty(p_problem_id) || jsonb_build_object('bojLabels',COALESCE((
        SELECT jsonb_object_agg(b.part_order,s.label)
        FROM catalog.contest_problems m
        JOIN catalog.contests c ON c.id=m.contest_id AND c.is_public
        JOIN catalog.problems p ON p.id=m.problem_id AND p.is_public
        JOIN app_private.catalog_boj_contests cb
            ON cb.contest_id=m.contest_id AND cb.group_id IS NOT DISTINCT FROM m.group_id
        JOIN app_private.catalog_boj_problems b ON b.catalog_problem_id=p.id AND b.part_order IS NOT NULL
        JOIN app_private.boj_contest_slots s ON s.source_id=cb.source_id AND s.boj_problem_id=b.boj_problem_id
        WHERE m.contest_id=p_contest_id AND m.problem_id=p_problem_id AND m.is_public
            AND m.group_id IS NOT DISTINCT FROM p_group_id AND s.label IS NOT NULL
    ),'{}'));
$$;

-- Compare only the linked native slots from the completed operator job.
CREATE FUNCTION catalog.boj_review_matches(p_contest_id uuid,p_group_id text,p_boj_ids bigint[])
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_object_agg(m.boj_id,m.matches),'{}')
    FROM (
        SELECT b.boj_problem_id AS boj_id,jsonb_agg(jsonb_build_object(
            'problemId',p.id,'title',p.payload->>'title','partOrder',b.part_order,'evidence',b.evidence,
            'inScope',EXISTS(SELECT 1 FROM catalog.contest_problems cp
                WHERE cp.contest_id=p_contest_id AND cp.problem_id=p.id AND cp.is_public
                AND cp.group_id IS NOT DISTINCT FROM p_group_id))
            ORDER BY p.id) AS matches
        FROM app_private.catalog_boj_problems b JOIN catalog.problems p ON p.id=b.catalog_problem_id
        WHERE b.boj_problem_id=ANY(p_boj_ids)
        GROUP BY b.boj_problem_id
    ) m;
$$;

REVOKE ALL ON FUNCTION public.problem_difficulty_batch(uuid[]),
    public.problem_boj_difficulty(uuid,uuid,text),catalog.boj_review_matches(uuid,text,bigint[])
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.problem_difficulty_batch(uuid[]),
    public.problem_boj_difficulty(uuid,uuid,text) TO anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION catalog.boj_review_matches(uuid,text,bigint[]) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
