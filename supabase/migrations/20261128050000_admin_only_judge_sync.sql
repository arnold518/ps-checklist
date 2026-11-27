BEGIN;

-- The HTTP application resolves the owner from the authenticated session
-- and checks its existing administrator allowlist before invoking these writes.
DROP FUNCTION public.set_judge_sync_account(text,text);
CREATE FUNCTION public.set_judge_sync_account(p_user_id uuid,p_source text,p_handle text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account_id uuid;
BEGIN
    IF p_user_id IS NULL THEN RAISE EXCEPTION 'Owner required' USING ERRCODE='42501'; END IF;
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder','boj','solvedac','doj')
        OR (p_handle IS NOT NULL AND p_handle !~ '^[A-Za-z0-9_.-]{1,64}$')
    THEN RAISE EXCEPTION 'Invalid judge source or handle' USING ERRCODE='22023'; END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('judge-account:'||p_user_id::text||':'||p_source,0));
    DELETE FROM app_private.judge_sync_accounts
    WHERE user_id=p_user_id AND source=p_source AND handle IS DISTINCT FROM p_handle;
    IF p_handle IS NULL THEN RETURN NULL; END IF;
    INSERT INTO app_private.judge_sync_accounts(user_id,source,handle)
    VALUES(p_user_id,p_source,p_handle) ON CONFLICT (user_id,source) DO NOTHING;
    SELECT a.id INTO account_id FROM app_private.judge_sync_accounts a WHERE a.user_id=p_user_id AND a.source=p_source;
    RETURN account_id;
END;
$$;

DROP FUNCTION public.request_judge_sync(text);
CREATE FUNCTION public.request_judge_sync(p_user_id uuid,p_source text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE app_private.judge_sync_jobs j SET due_at=LEAST(j.due_at,clock_timestamp())
    FROM app_private.judge_sync_accounts a
    WHERE a.user_id=p_user_id AND a.source=p_source AND a.id=j.account_id
      AND j.error_code IS NULL AND j.lease IS NULL
      AND (j.last_success IS NULL OR j.last_success<now()-interval '1 minute');
$$;

DROP FUNCTION public.claim_judge_sync_job();
CREATE FUNCTION public.claim_judge_sync_job(p_admin_user_ids uuid[])
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE job app_private.judge_sync_jobs; claimed_at timestamptz := clock_timestamp();
BEGIN
    SELECT j.* INTO job FROM app_private.judge_sync_jobs j
    JOIN app_private.judge_sync_accounts a ON a.id=j.account_id
    WHERE a.user_id=ANY(p_admin_user_ids)
      AND j.due_at<=claimed_at AND (j.lease_until IS NULL OR j.lease_until<=claimed_at)
    ORDER BY j.due_at,j.account_id,j.feed FOR UPDATE OF j SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    UPDATE app_private.judge_sync_jobs SET lease=gen_random_uuid(),lease_until=claimed_at+interval '5 minutes'
    WHERE account_id=job.account_id AND feed=job.feed RETURNING * INTO job;
    RETURN (SELECT jsonb_build_object('id',a.id,'userId',a.user_id,'source',a.source,'handle',a.handle,'feed',job.feed,
        'lease',job.lease,'cursor',COALESCE(c.cursor,job.cursor),'revision',COALESCE(c.revision,0))
        FROM app_private.judge_sync_accounts a
        LEFT JOIN app_private.judge_sync_checkpoints c ON c.account_id=a.id AND c.feed=job.feed
        WHERE a.id=job.account_id);
END;
$$;

DROP FUNCTION public.judge_sync_targets(uuid,integer,uuid);
CREATE FUNCTION public.judge_sync_targets(
    p_admin_user_ids uuid[],p_after uuid DEFAULT NULL,p_limit integer DEFAULT 50,p_account_id uuid DEFAULT NULL
) RETURNS TABLE(id uuid,source text,judge text,handle text,checkpoints jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT a.id,a.source,a.judge,a.handle,
        COALESCE((SELECT jsonb_object_agg(c.feed,jsonb_build_object(
            'cursor',c.cursor,'revision',c.revision,'committedAt',c.committed_at))
        FROM app_private.judge_sync_checkpoints c WHERE c.account_id=a.id),'{}'::jsonb)
    FROM app_private.judge_sync_accounts a
    WHERE a.user_id=ANY(p_admin_user_ids) AND (p_after IS NULL OR a.id>p_after)
      AND (p_account_id IS NULL OR a.id=p_account_id)
    ORDER BY a.id LIMIT GREATEST(1,LEAST(100,COALESCE(p_limit,50)));
$$;

-- Jobs issued under the previous authorization rule must be claimed again.
UPDATE app_private.judge_sync_jobs SET lease=NULL,lease_until=NULL WHERE lease IS NOT NULL;

REVOKE ALL ON FUNCTION public.set_judge_sync_account(uuid,text,text),public.request_judge_sync(uuid,text),
    public.claim_judge_sync_job(uuid[]),public.judge_sync_targets(uuid[],uuid,integer,uuid)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.set_judge_sync_account(uuid,text,text),public.request_judge_sync(uuid,text),
    public.claim_judge_sync_job(uuid[]),public.judge_sync_targets(uuid[],uuid,integer,uuid) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
