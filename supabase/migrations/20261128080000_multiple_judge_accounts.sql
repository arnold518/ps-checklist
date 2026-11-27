BEGIN;

ALTER TABLE app_private.judge_sync_accounts
    DROP CONSTRAINT judge_sync_accounts_user_id_source_key,
    ADD CONSTRAINT judge_sync_accounts_user_id_source_handle_key UNIQUE (user_id,source,handle);

CREATE FUNCTION public.add_judge_sync_account(p_user_id uuid,p_source text,p_handle text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account_id uuid;
BEGIN
    IF p_user_id IS NULL THEN RAISE EXCEPTION 'Owner required' USING ERRCODE='42501'; END IF;
    IF NOT EXISTS (SELECT 1 FROM app_private.judge_job_feeds(p_source))
        OR p_handle IS NULL OR p_handle !~ '^[A-Za-z0-9_.-]{1,64}$'
    THEN RAISE EXCEPTION 'Invalid judge source or handle' USING ERRCODE='22023'; END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('judge-account:'||p_user_id::text||':'||p_source,0));
    INSERT INTO app_private.judge_sync_accounts(user_id,source,handle)
    VALUES(p_user_id,p_source,p_handle) ON CONFLICT (user_id,source,handle) DO NOTHING;
    SELECT a.id INTO account_id FROM app_private.judge_sync_accounts a
    WHERE a.user_id=p_user_id AND a.source=p_source AND a.handle=p_handle;
    RETURN account_id;
END;
$$;

-- An older client can still manage a single connection. It cannot remove or
-- replace a connection ambiguously once a second handle has been linked.
CREATE OR REPLACE FUNCTION public.set_judge_sync_account(p_user_id uuid,p_source text,p_handle text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF p_user_id IS NULL THEN RAISE EXCEPTION 'Owner required' USING ERRCODE='42501'; END IF;
    IF NOT EXISTS (SELECT 1 FROM app_private.judge_job_feeds(p_source))
        OR (p_handle IS NOT NULL AND p_handle !~ '^[A-Za-z0-9_.-]{1,64}$')
    THEN RAISE EXCEPTION 'Invalid judge source or handle' USING ERRCODE='22023'; END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('judge-account:'||p_user_id::text||':'||p_source,0));
    IF (SELECT count(*) FROM app_private.judge_sync_accounts
        WHERE user_id=p_user_id AND source=p_source)>1
    THEN RAISE EXCEPTION 'Select a judge account by ID' USING ERRCODE='22023'; END IF;

    DELETE FROM app_private.judge_sync_accounts
    WHERE user_id=p_user_id AND source=p_source AND handle IS DISTINCT FROM p_handle;
    IF p_handle IS NULL THEN RETURN NULL; END IF;
    RETURN public.add_judge_sync_account(p_user_id,p_source,p_handle);
END;
$$;

CREATE FUNCTION public.unlink_judge_sync_account(p_user_id uuid,p_account_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('judge-account:'||p_user_id::text||':'||source,0))
    FROM app_private.judge_sync_accounts WHERE user_id=p_user_id AND id=p_account_id;
    DELETE FROM app_private.judge_sync_accounts WHERE user_id=p_user_id AND id=p_account_id;
END;
$$;

CREATE FUNCTION public.request_judge_account_sync(p_user_id uuid,p_account_id uuid)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE app_private.judge_sync_jobs j SET due_at=LEAST(j.due_at,clock_timestamp())
    FROM app_private.judge_sync_accounts a
    WHERE a.user_id=p_user_id AND a.id=p_account_id AND a.id=j.account_id
      AND j.error_code IS NULL AND j.lease IS NULL
      AND (j.last_success IS NULL OR j.last_success<now()-interval '1 minute');
$$;

CREATE OR REPLACE FUNCTION public.judge_sync_overview()
RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',a.id,'source',a.source,'handle',a.handle,'feeds',(
        SELECT jsonb_object_agg(j.feed,jsonb_build_object(
            'lastSyncedAt',j.last_success,
            'error',j.error_code,
            'pending',j.due_at<=now() OR j.lease_until>now(),
            'activity',CASE
                WHEN j.error_code IS NOT NULL THEN 'retry'
                WHEN j.feed='submissions' AND (c.cursor-'watermark')<>'{}'::jsonb
                    AND COALESCE(c.cursor->>'watermark','') IN ('','0') THEN 'backfill'
                WHEN j.feed='progress' AND c.cursor<>'{}'::jsonb THEN 'importing'
                WHEN j.feed='contests' AND j.cursor->>'draining'='true' THEN 'importing'
                WHEN j.lease_until>now() THEN 'running'
                WHEN j.due_at<=now() THEN 'queued'
                ELSE 'idle'
            END,
            'count',CASE j.feed
                WHEN 'submissions' THEN (SELECT count(*) FROM app_private.judge_submissions s WHERE s.account_id=a.id)
                WHEN 'progress' THEN (SELECT count(*) FROM app_private.judge_progress_observations p WHERE p.account_id=a.id AND p.status>0)
                WHEN 'contests' THEN (SELECT count(*) FROM app_private.judge_contest_imports i WHERE i.account_id=a.id AND i.imported_at IS NOT NULL)
            END
        ))
        FROM app_private.judge_sync_jobs j LEFT JOIN app_private.judge_sync_checkpoints c
            ON c.account_id=j.account_id AND c.feed=j.feed
        WHERE j.account_id=a.id
    )) FROM app_private.judge_sync_accounts a
    WHERE a.user_id=auth.uid() AND EXISTS (
        SELECT 1 FROM app_private.judge_sync_jobs j WHERE j.account_id=a.id
    )
    ORDER BY a.source,a.linked_at,a.id;
$$;

CREATE OR REPLACE FUNCTION public.judge_submission_history(
    p_problem_id uuid DEFAULT NULL,p_contest_id uuid DEFAULT NULL,p_group_id text DEFAULT NULL,
    p_before uuid DEFAULT NULL,p_limit integer DEFAULT 50
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE before_time timestamptz := '-infinity'; owner_id uuid := auth.uid();
BEGIN
    IF owner_id IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100 OR (p_group_id IS NOT NULL AND p_contest_id IS NULL)
    THEN RAISE EXCEPTION 'Invalid submission history filter' USING ERRCODE='22023'; END IF;
    IF p_before IS NOT NULL THEN
        SELECT COALESCE(s.submitted_at,'-infinity'::timestamptz) INTO before_time
        FROM app_private.judge_submissions s JOIN app_private.judge_sync_accounts a ON a.id=s.account_id
        WHERE s.id=p_before AND a.user_id=owner_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Invalid submission history cursor' USING ERRCODE='22023'; END IF;
    END IF;
    RETURN (
        WITH memberships AS MATERIALIZED (
            SELECT cp.id,cp.problem_id,cp.group_id,cp.problem_index,cp.position,
                c.payload->'link' AS contest_links,g.value->'link' AS group_links
            FROM catalog.contest_problems cp JOIN catalog.contests c ON c.id=cp.contest_id AND c.is_public
            LEFT JOIN LATERAL jsonb_array_elements(COALESCE(c.payload->'groups','[]')) g
                ON g.value->>'id'=cp.group_id
            WHERE cp.contest_id=p_contest_id AND cp.is_public AND (p_group_id IS NULL OR cp.group_id=p_group_id)
        ), bindings AS MATERIALIZED (
            SELECT * FROM app_private.judge_problem_bindings WHERE p_problem_id IS NULL OR problem_id=p_problem_id
        ), candidates AS (
            SELECT s.*,a.source,a.handle AS account_handle,COALESCE(s.submitted_at,'-infinity'::timestamptz) AS sort_time
            FROM app_private.judge_sync_accounts a JOIN app_private.judge_submissions s ON s.account_id=a.id
            WHERE a.user_id=owner_id AND (p_before IS NULL OR
                (COALESCE(s.submitted_at,'-infinity'::timestamptz),s.id)<(before_time,p_before))
              AND ((p_problem_id IS NULL AND p_contest_id IS NULL) OR EXISTS (
                  SELECT 1 FROM bindings b WHERE b.judge=s.judge AND b.native_key=s.native_problem_key
                  AND (p_contest_id IS NULL OR EXISTS (SELECT 1 FROM memberships m WHERE m.problem_id=b.problem_id))
              ))
            ORDER BY sort_time DESC,s.id DESC LIMIT p_limit+1
        ), numbered AS (
            SELECT c.*,row_number() OVER (ORDER BY sort_time DESC,id DESC) AS ordinal FROM candidates c
        ), page AS (
            SELECT n.ordinal,n.id,jsonb_build_object(
                'id',n.id,'judge',n.judge,'source',n.source,'accountHandle',n.account_handle,'nativeSubmissionId',n.native_submission_id,
                'submissionUrl',n.submission_url,'problemUrl',n.problem_url,'nativeContestUrl',n.native_contest_url,
                'participation',n.participation,'submittedAt',n.submitted_at,'fetchedAt',n.fetched_at,'observedAt',n.observed_at,
                'result',n.result,'verdict',n.verdict,'language',n.language,'score',n.score,
                'maxScore',n.max_score,'runtimeMs',n.runtime_ms,'memoryBytes',n.memory_bytes,
                'problemMatches',COALESCE((SELECT jsonb_agg(jsonb_build_object(
                    'problemId',b.problem_id,'partOrder',b.part_order) ORDER BY b.problem_id)
                    FROM bindings b WHERE b.judge=n.judge AND b.native_key=n.native_problem_key),'[]'::jsonb),
                'contestMemberships',COALESCE((SELECT jsonb_agg(jsonb_build_object(
                    'membershipId',m.id,'problemId',m.problem_id,'groupId',m.group_id,'index',m.problem_index,
                    'matchesNativeContest',CASE WHEN n.native_contest_url IS NOT NULL THEN
                        n.native_contest_url=COALESCE(m.group_links->>n.judge,m.contest_links->>n.judge) END
                    ) ORDER BY m.position,m.id)
                    FROM memberships m JOIN bindings b ON b.problem_id=m.problem_id
                    WHERE b.judge=n.judge AND b.native_key=n.native_problem_key),'[]'::jsonb)
            ) AS record FROM numbered n WHERE n.ordinal<=p_limit
        )
        SELECT jsonb_build_object('submissions',COALESCE(jsonb_agg(record ORDER BY ordinal),'[]'::jsonb),
            'nextCursor',CASE WHEN EXISTS (SELECT 1 FROM numbered WHERE ordinal>p_limit) THEN
                (SELECT id FROM page WHERE ordinal=p_limit) END)
        FROM page
    );
END;
$$;

REVOKE ALL ON FUNCTION public.add_judge_sync_account(uuid,text,text),public.unlink_judge_sync_account(uuid,uuid),
    public.request_judge_account_sync(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.add_judge_sync_account(uuid,text,text),public.unlink_judge_sync_account(uuid,uuid),
    public.request_judge_account_sync(uuid,uuid) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
