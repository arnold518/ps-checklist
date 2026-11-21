BEGIN;
CREATE OR REPLACE FUNCTION public.deployment_state()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_set(user_data.read_state(),'{catalog,rawOrder}',public.deployment_order(),true)
        || jsonb_build_object('tierVotes', COALESCE((
            SELECT jsonb_object_agg(problem_id,tier)
            FROM user_data.difficulty_tier_votes WHERE user_id=auth.uid()
        ), '{}'::jsonb));
$$;
NOTIFY pgrst,'reload schema';
COMMIT;
