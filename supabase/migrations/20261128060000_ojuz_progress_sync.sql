BEGIN;

CREATE OR REPLACE FUNCTION app_private.judge_job_feeds(p_source text)
RETURNS SETOF text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT feed FROM (VALUES ('submissions'),('progress'),('contests')) f(feed)
    WHERE CASE feed
        WHEN 'submissions' THEN p_source IN ('cf','atcoder','boj','doj')
        WHEN 'progress' THEN p_source IN ('solvedac','ojuz')
        WHEN 'contests' THEN p_source IN ('cf','atcoder','doj')
    END;
$$;

CREATE OR REPLACE FUNCTION public.set_judge_sync_account(p_user_id uuid,p_source text,p_handle text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account_id uuid;
BEGIN
    IF p_user_id IS NULL THEN RAISE EXCEPTION 'Owner required' USING ERRCODE='42501'; END IF;
    IF NOT EXISTS (SELECT 1 FROM app_private.judge_job_feeds(p_source))
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

CREATE OR REPLACE FUNCTION public.judge_sync_overview()
RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('source',a.source,'handle',a.handle,'feeds',(
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
    ORDER BY a.source;
$$;

CREATE OR REPLACE FUNCTION public.commit_judge_sync_batch(
    p_account_id uuid,p_feed text,p_expected_revision bigint,p_cursor jsonb,p_records jsonb
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account app_private.judge_sync_accounts; revision bigint; observed timestamptz;
BEGIN
    IF p_feed IS NULL OR p_feed NOT IN ('submissions','progress')
        OR p_expected_revision IS NULL OR p_expected_revision<0
        OR jsonb_typeof(p_cursor) IS DISTINCT FROM 'object' OR octet_length(p_cursor::text)>4096
        OR jsonb_typeof(p_records) IS DISTINCT FROM 'array'
    THEN RAISE EXCEPTION 'Invalid judge sync batch' USING ERRCODE='22023'; END IF;
    SELECT * INTO account FROM app_private.judge_sync_accounts WHERE id=p_account_id FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF (p_feed='submissions' AND account.source IN ('solvedac','ojuz'))
        OR (p_feed='progress' AND account.source NOT IN ('solvedac','ojuz','doj'))
    THEN RAISE EXCEPTION 'This source does not provide the requested feed' USING ERRCODE='22023'; END IF;
    IF jsonb_array_length(p_records)>(CASE WHEN account.source='ojuz' THEN 10000 ELSE 500 END) THEN
        RAISE EXCEPTION 'Judge sync batch exceeds its record limit' USING ERRCODE='22023';
    END IF;

    SELECT c.revision INTO revision FROM app_private.judge_sync_checkpoints c
    WHERE c.account_id=account.id AND c.feed=p_feed;
    IF COALESCE(revision,0)<>p_expected_revision THEN RETURN NULL; END IF;
    observed := clock_timestamp();

    IF p_feed='submissions' THEN
        INSERT INTO app_private.judge_submissions AS current (
            account_id,judge,native_submission_id,submission_url,problem_url,native_contest_url,
            participation,submitted_at,result,verdict,language,score,max_score,runtime_ms,memory_bytes,fetched_at,observed_at)
        SELECT account.id,account.judge,r.submission_id,r.submission_url,r.problem_url,r.native_contest_url,
            COALESCE(r.participation,'unknown'),r.submitted_at,r.result,r.verdict,r.language,r.score,r.max_score,
            r.runtime_ms,r.memory_bytes,r.fetched_at,observed
        FROM jsonb_to_recordset(p_records) AS r(submission_id text,submission_url text,problem_url text,
            native_contest_url text,participation text,submitted_at timestamptz,result text,verdict text,
            language text,score double precision,max_score double precision,runtime_ms bigint,memory_bytes bigint,
            fetched_at timestamptz)
        ON CONFLICT (account_id,native_submission_id) DO UPDATE SET
            submission_url=EXCLUDED.submission_url,
            problem_url=COALESCE(EXCLUDED.problem_url,current.problem_url),
            native_contest_url=COALESCE(EXCLUDED.native_contest_url,current.native_contest_url),
            participation=COALESCE(NULLIF(EXCLUDED.participation,'unknown'),current.participation),
            submitted_at=COALESCE(current.submitted_at,EXCLUDED.submitted_at),
            result=EXCLUDED.result, verdict=EXCLUDED.verdict, language=COALESCE(EXCLUDED.language,current.language),
            score=EXCLUDED.score, max_score=EXCLUDED.max_score, runtime_ms=EXCLUDED.runtime_ms,
            memory_bytes=EXCLUDED.memory_bytes, fetched_at=COALESCE(EXCLUDED.fetched_at,current.fetched_at),
            observed_at=EXCLUDED.observed_at
        WHERE EXCLUDED.fetched_at IS NULL OR current.fetched_at IS NULL OR EXCLUDED.fetched_at>=current.fetched_at;
    ELSE
        -- An oj.uz progress batch is an entire validated profile snapshot.
        -- A problem removed from that snapshot loses only this source's evidence.
        IF account.source='ojuz' THEN
            DELETE FROM app_private.judge_progress_observations WHERE account_id=account.id;
        END IF;
        INSERT INTO app_private.judge_progress_observations(account_id,judge,problem_url,status,observed_at)
        SELECT account.id,account.judge,r.problem_url,r.status,observed
        FROM jsonb_to_recordset(p_records) AS r(problem_url text,status integer)
        ON CONFLICT (account_id,native_problem_key) DO UPDATE SET
            status=EXCLUDED.status, observed_at=EXCLUDED.observed_at;
    END IF;

    INSERT INTO app_private.judge_sync_checkpoints(account_id,feed,cursor,revision,committed_at)
    VALUES(account.id,p_feed,p_cursor,p_expected_revision+1,observed)
    ON CONFLICT (account_id,feed) DO UPDATE SET
        cursor=EXCLUDED.cursor, revision=EXCLUDED.revision, committed_at=EXCLUDED.committed_at;
    RETURN p_expected_revision+1;
END;
$$;

INSERT INTO app_private.judge_sync_jobs(account_id,feed)
SELECT id,'progress' FROM app_private.judge_sync_accounts WHERE source='ojuz'
ON CONFLICT (account_id,feed) DO NOTHING;

NOTIFY pgrst,'reload schema';

COMMIT;
