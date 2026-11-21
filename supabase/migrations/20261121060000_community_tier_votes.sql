BEGIN;

-- Earlier votes used a ten-point scale. Keep those scores in difficulty_votes.
CREATE TABLE user_data.difficulty_tier_votes (
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    tier smallint NOT NULL CHECK (tier BETWEEN 1 AND 30),
    PRIMARY KEY (user_id, problem_id)
);
CREATE INDEX difficulty_tier_votes_problem ON user_data.difficulty_tier_votes(problem_id);
ALTER TABLE user_data.difficulty_tier_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_data.difficulty_tier_votes FORCE ROW LEVEL SECURITY;
CREATE POLICY own_tier_vote ON user_data.difficulty_tier_votes TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()) AND EXISTS (
        SELECT 1 FROM catalog.problems WHERE id = problem_id AND is_public
    ));
GRANT SELECT, INSERT, DELETE ON user_data.difficulty_tier_votes TO authenticated;
GRANT UPDATE(tier) ON user_data.difficulty_tier_votes TO authenticated;
GRANT ALL ON user_data.difficulty_tier_votes TO service_role;

CREATE OR REPLACE FUNCTION public.problem_difficulty(p_problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    WITH problem AS (
        SELECT id FROM catalog.problems WHERE id=p_problem_id AND is_public
    ), legacy AS (
        SELECT count(*) AS count, round(avg(value),2) AS average,
            max(value) FILTER (WHERE user_id=auth.uid()) AS vote
        FROM user_data.difficulty_votes WHERE problem_id IN (SELECT id FROM problem)
    ), community AS (
        SELECT count(*) AS count, round(avg(tier))::integer AS level,
            max(tier) FILTER (WHERE user_id=auth.uid()) AS vote
        FROM user_data.difficulty_tier_votes WHERE problem_id IN (SELECT id FROM problem)
    )
    SELECT to_jsonb(legacy) || jsonb_build_object('communityTier',to_jsonb(community))
        || COALESCE((SELECT jsonb_build_object('solvedAc',rating) FROM
            (SELECT catalog.solvedac_problem_difficulty(p_problem_id) AS rating) r
            WHERE rating IS NOT NULL),'{}')
    FROM legacy, community;
$$;

CREATE FUNCTION public.set_problem_tier_vote(p_problem_id uuid, p_tier integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_tier IS NULL THEN
        DELETE FROM user_data.difficulty_tier_votes WHERE problem_id=p_problem_id AND user_id=auth.uid();
    ELSE
        INSERT INTO user_data.difficulty_tier_votes(problem_id,tier) VALUES(p_problem_id,p_tier)
            ON CONFLICT(user_id,problem_id) DO UPDATE SET tier=EXCLUDED.tier;
    END IF;
    RETURN public.problem_difficulty(p_problem_id);
END;
$$;
REVOKE ALL ON FUNCTION public.set_problem_tier_vote(uuid,integer) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.set_problem_tier_vote(uuid,integer) TO authenticated,service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
