BEGIN;

CREATE TABLE app_private.judge_sync_jobs (
    account_id uuid NOT NULL REFERENCES app_private.judge_sync_accounts(id) ON DELETE CASCADE,
    feed text NOT NULL CHECK (feed IN ('submissions','progress','contests')),
    due_at timestamptz NOT NULL DEFAULT now(),
    lease uuid,
    lease_until timestamptz,
    cursor jsonb NOT NULL DEFAULT '{}',
    last_success timestamptz,
    error_code text,
    PRIMARY KEY (account_id,feed)
);
CREATE INDEX judge_sync_jobs_due ON app_private.judge_sync_jobs(due_at);

-- Keep the completed receipt across disconnects and deletions from either view.
CREATE TABLE app_private.judge_contest_imports (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    judge text NOT NULL CHECK (judge IN ('cf','atcoder','doj')),
    contest_url text NOT NULL,
    account_id uuid REFERENCES app_private.judge_sync_accounts(id) ON DELETE SET NULL,
    started_at timestamptz,
    needs_confirmation boolean NOT NULL DEFAULT false,
    retry_at timestamptz NOT NULL DEFAULT now(),
    imported_at timestamptz,
    PRIMARY KEY (user_id,judge,contest_url)
);
CREATE INDEX judge_contest_imports_pending ON app_private.judge_contest_imports(account_id,retry_at)
    WHERE imported_at IS NULL;
ALTER TABLE app_private.judge_sync_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.judge_contest_imports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_private.judge_sync_jobs,app_private.judge_contest_imports FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION app_private.judge_job_feeds(p_source text)
RETURNS SETOF text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
    SELECT feed FROM (VALUES ('submissions'),('progress'),('contests')) f(feed)
    WHERE CASE feed
        WHEN 'submissions' THEN p_source IN ('cf','atcoder','boj','doj')
        WHEN 'progress' THEN p_source='solvedac'
        WHEN 'contests' THEN p_source IN ('cf','atcoder','doj')
    END;
$$;

CREATE FUNCTION app_private.seed_judge_jobs()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    INSERT INTO app_private.judge_sync_jobs(account_id,feed)
    SELECT NEW.id,f FROM app_private.judge_job_feeds(NEW.source) f;
    RETURN NEW;
END;
$$;
CREATE TRIGGER seed_judge_jobs AFTER INSERT ON app_private.judge_sync_accounts
    FOR EACH ROW EXECUTE FUNCTION app_private.seed_judge_jobs();
INSERT INTO app_private.judge_sync_jobs(account_id,feed)
SELECT a.id,f FROM app_private.judge_sync_accounts a CROSS JOIN LATERAL app_private.judge_job_feeds(a.source) f;

CREATE FUNCTION public.judge_sync_overview()
RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('source',a.source,'handle',a.handle,'feeds',(
        SELECT jsonb_object_agg(j.feed,jsonb_build_object('lastSyncedAt',j.last_success,
            'error',j.error_code,'pending',j.due_at<=now() OR j.lease_until>now()))
        FROM app_private.judge_sync_jobs j WHERE j.account_id=a.id
    )) FROM app_private.judge_sync_accounts a
    WHERE a.user_id=auth.uid() AND a.source IN ('cf','atcoder','doj','boj','solvedac')
    ORDER BY a.source;
$$;

CREATE FUNCTION public.request_judge_sync(p_source text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    UPDATE app_private.judge_sync_jobs j SET due_at=LEAST(j.due_at,clock_timestamp())
    FROM app_private.judge_sync_accounts a
    WHERE a.user_id=auth.uid() AND a.source=p_source AND a.id=j.account_id
      AND j.error_code IS NULL AND j.lease IS NULL
      AND (j.last_success IS NULL OR j.last_success<now()-interval '1 minute');
$$;

CREATE FUNCTION public.claim_judge_sync_job()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE job app_private.judge_sync_jobs; claimed_at timestamptz := clock_timestamp();
BEGIN
    SELECT j.* INTO job FROM app_private.judge_sync_jobs j
    WHERE j.due_at<=claimed_at AND (j.lease_until IS NULL OR j.lease_until<=claimed_at)
    ORDER BY j.due_at,j.account_id,j.feed FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    UPDATE app_private.judge_sync_jobs SET lease=gen_random_uuid(),lease_until=claimed_at+interval '5 minutes'
    WHERE account_id=job.account_id AND feed=job.feed RETURNING * INTO job;
    RETURN (SELECT jsonb_build_object('id',a.id,'source',a.source,'handle',a.handle,'feed',job.feed,
        'lease',job.lease,'cursor',COALESCE(c.cursor,job.cursor),'revision',COALESCE(c.revision,0))
        FROM app_private.judge_sync_accounts a
        LEFT JOIN app_private.judge_sync_checkpoints c ON c.account_id=a.id AND c.feed=job.feed
        WHERE a.id=job.account_id);
END;
$$;

CREATE FUNCTION app_private.lock_judge_job(p_account_id uuid,p_feed text,p_lease uuid)
RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    -- Use the same account then job lock order as the batch writer and disconnect.
    PERFORM 1 FROM app_private.judge_sync_accounts WHERE id=p_account_id FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    PERFORM 1 FROM app_private.judge_sync_jobs
    WHERE account_id=p_account_id AND feed=p_feed AND lease=p_lease AND lease_until>clock_timestamp() FOR UPDATE;
    RETURN FOUND;
END;
$$;

CREATE FUNCTION app_private.record_judge_participations(p_account_id uuid,p_contests jsonb)
RETURNS void LANGUAGE sql SET search_path=pg_catalog AS $$
    INSERT INTO app_private.judge_contest_imports(user_id,judge,account_id,contest_url,started_at,needs_confirmation)
    SELECT a.user_id,a.judge,a.id,r.url,min(r.started_at),bool_and(COALESCE(r.needs_confirmation,false))
    FROM app_private.judge_sync_accounts a
    CROSS JOIN jsonb_to_recordset(p_contests) r(url text,started_at timestamptz,needs_confirmation boolean)
    WHERE a.id=p_account_id AND (r.started_at IS NULL OR isfinite(r.started_at))
        AND r.url ~ CASE a.judge
            WHEN 'cf' THEN '^https://codeforces[.]com/(contest|gym)/[1-9][0-9]{0,14}$'
            WHEN 'atcoder' THEN '^https://atcoder[.]jp/contests/[A-Za-z0-9_-]{1,100}$'
            WHEN 'doj' THEN '^https://doj[.]kr/en/contests/[A-Za-z0-9][A-Za-z0-9_-]{0,99}$'
        END
    GROUP BY a.user_id,a.judge,a.id,r.url
    ON CONFLICT (user_id,judge,contest_url) DO UPDATE SET
        account_id=EXCLUDED.account_id,started_at=COALESCE(EXCLUDED.started_at,judge_contest_imports.started_at),
        retry_at=CASE WHEN judge_contest_imports.needs_confirmation AND NOT EXCLUDED.needs_confirmation
            THEN clock_timestamp() ELSE judge_contest_imports.retry_at END,
        needs_confirmation=EXCLUDED.needs_confirmation
    WHERE judge_contest_imports.imported_at IS NULL
      AND (judge_contest_imports.needs_confirmation OR NOT EXCLUDED.needs_confirmation)
      AND (judge_contest_imports.account_id,judge_contest_imports.started_at,judge_contest_imports.needs_confirmation)
          IS DISTINCT FROM (EXCLUDED.account_id,COALESCE(EXCLUDED.started_at,judge_contest_imports.started_at),EXCLUDED.needs_confirmation);
$$;

-- Accounts using the earlier on-demand importer may already have contest evidence.
INSERT INTO app_private.judge_contest_imports(user_id,judge,account_id,contest_url)
SELECT DISTINCT a.user_id,a.judge,a.id,s.native_contest_url
FROM app_private.judge_sync_accounts a JOIN app_private.judge_submissions s ON s.account_id=a.id
WHERE a.source='cf' AND s.participation='contest'
    AND s.native_contest_url ~ '^https://codeforces[.]com/(contest|gym)/[1-9][0-9]{0,14}$';

CREATE FUNCTION public.finish_judge_sync_job(
    p_account_id uuid,p_feed text,p_lease uuid,p_revision bigint,p_cursor jsonb,
    p_records jsonb,p_contests jsonb,p_delay integer,p_error text DEFAULT NULL
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF NOT app_private.lock_judge_job(p_account_id,p_feed,p_lease) THEN RETURN false; END IF;
    IF p_error IS NULL THEN
        IF p_feed IN ('submissions','progress') AND
            public.commit_judge_sync_batch(p_account_id,p_feed,p_revision,p_cursor,p_records) IS NULL
        THEN
            -- A deliberate on-demand import may have advanced this feed during the fetch.
            UPDATE app_private.judge_sync_jobs SET lease=NULL,lease_until=NULL,due_at=clock_timestamp()
            WHERE account_id=p_account_id AND feed=p_feed;
            RETURN false;
        END IF;
        IF jsonb_typeof(p_contests)='array' AND jsonb_array_length(p_contests)>0 THEN
            PERFORM app_private.record_judge_participations(p_account_id,p_contests);
        END IF;
    END IF;
    UPDATE app_private.judge_sync_jobs SET lease=NULL,lease_until=NULL,
        due_at=clock_timestamp()+make_interval(secs=>GREATEST(5,LEAST(86400,COALESCE(p_delay,3600)))),
        cursor=CASE WHEN p_error IS NULL AND p_feed='contests' THEN COALESCE(p_cursor,'{}') ELSE cursor END,
        last_success=CASE WHEN p_error IS NULL THEN clock_timestamp() ELSE last_success END,
        error_code=left(p_error,80)
    WHERE account_id=p_account_id AND feed=p_feed;
    RETURN true;
END;
$$;

CREATE FUNCTION public.judge_pending_contests(p_account_id uuid,p_lease uuid)
RETURNS TABLE(url text,known boolean,needs_confirmation boolean,needs_start boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT i.contest_url, EXISTS (
        SELECT 1 FROM catalog.contests c
        WHERE c.is_public AND c.payload->'link'->>i.judge=i.contest_url AND c.problem_count>0
    ),i.needs_confirmation,i.started_at IS NULL FROM app_private.judge_contest_imports i
    JOIN app_private.judge_sync_jobs j ON j.account_id=i.account_id AND j.feed='contests'
    WHERE i.account_id=p_account_id AND j.lease=p_lease AND j.lease_until>now()
      AND i.imported_at IS NULL AND i.retry_at<=now()
      AND (NOT i.needs_confirmation OR i.started_at>=now()-interval '14 days')
    ORDER BY i.started_at DESC NULLS LAST,i.contest_url LIMIT 4;
$$;

CREATE FUNCTION public.import_judge_participation(
    p_account_id uuid,p_lease uuid,p_url text,p_native jsonb DEFAULT NULL,p_retry boolean DEFAULT false,
    p_verified_start timestamptz DEFAULT NULL
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE participation app_private.judge_contest_imports; contest uuid;
BEGIN
    IF NOT app_private.lock_judge_job(p_account_id,'contests',p_lease) THEN RETURN false; END IF;
    SELECT * INTO participation FROM app_private.judge_contest_imports
    WHERE account_id=p_account_id AND contest_url=p_url AND imported_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF p_retry THEN
        UPDATE app_private.judge_contest_imports SET retry_at=clock_timestamp()
            +CASE WHEN participation.needs_confirmation THEN interval '1 day' ELSE interval '1 hour' END
        WHERE user_id=participation.user_id AND judge=participation.judge AND contest_url=p_url;
        RETURN false;
    END IF;
    IF (participation.needs_confirmation OR participation.started_at IS NULL)
        AND NOT COALESCE(isfinite(p_verified_start),false) THEN RETURN false; END IF;
    SELECT c.id INTO contest FROM catalog.contests c
    WHERE c.is_public AND c.payload->'link'->>participation.judge=p_url AND c.problem_count>0;
    IF contest IS NULL THEN
        IF p_native->>'url' IS DISTINCT FROM p_url
            OR p_native->>'source' IS DISTINCT FROM participation.judge
        THEN RAISE EXCEPTION 'Invalid participation contest' USING ERRCODE='22023'; END IF;
        contest := (catalog.import_round(participation.judge,p_native,participation.user_id)->'contest'->>'id')::uuid;
    ELSE
        INSERT INTO user_data.saved_contests AS saved(user_id,contest_id,payload)
        VALUES(participation.user_id,contest,jsonb_build_object('platforms',jsonb_build_array(participation.judge)))
        ON CONFLICT (user_id,contest_id) DO UPDATE SET payload=jsonb_build_object(
            'platforms',(saved.payload->'platforms')||jsonb_build_array(participation.judge))
        WHERE NOT (saved.payload->'platforms' ? participation.judge);
    END IF;
    INSERT INTO user_data.practice_sessions(user_id,contest_id,payload)
    VALUES(participation.user_id,contest,jsonb_build_object('date',
        to_char(COALESCE(p_verified_start,participation.started_at) AT TIME ZONE 'UTC','YYYY-MM-DD')))
    ON CONFLICT (user_id,contest_id) DO NOTHING;
    UPDATE app_private.judge_contest_imports SET imported_at=clock_timestamp()
    WHERE user_id=participation.user_id AND judge=participation.judge AND contest_url=p_url;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.deployment_state()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_set(user_data.read_state(),'{catalog,rawOrder}',public.deployment_order(),true)
        || jsonb_build_object('tierVotes',COALESCE((
            SELECT jsonb_object_agg(problem_id,tier) FROM user_data.difficulty_tier_votes WHERE user_id=auth.uid()
        ),'{}'::jsonb),'progress',COALESCE((
            SELECT jsonb_agg(jsonb_build_object('problemId',p.problem_id,'status',p.status,'manualStatus',p.manual_status))
            FROM public.judge_problem_status() p
        ),'[]'::jsonb));
$$;

CREATE FUNCTION public.set_judge_aware_progress(p_problem_id uuid,p_status integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    PERFORM user_data.set_progress(p_problem_id,p_status);
    RETURN (SELECT jsonb_build_object('problemId',p_problem_id,'status',s.status)
        FROM public.judge_problem_status(p_problem_id) s);
END;
$$;

REVOKE ALL ON FUNCTION app_private.judge_job_feeds(text),app_private.seed_judge_jobs(),
    app_private.lock_judge_job(uuid,text,uuid),app_private.record_judge_participations(uuid,jsonb)
    FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.judge_sync_overview(),public.request_judge_sync(text),
    public.claim_judge_sync_job(),public.finish_judge_sync_job(uuid,text,uuid,bigint,jsonb,jsonb,jsonb,integer,text),
    public.judge_pending_contests(uuid,uuid),public.import_judge_participation(uuid,uuid,text,jsonb,boolean,timestamptz),
    public.set_judge_aware_progress(uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.judge_sync_overview(),public.request_judge_sync(text),
    public.set_judge_aware_progress(uuid,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.claim_judge_sync_job(),
    public.finish_judge_sync_job(uuid,text,uuid,bigint,jsonb,jsonb,jsonb,integer,text),
    public.judge_pending_contests(uuid,uuid),public.import_judge_participation(uuid,uuid,text,jsonb,boolean,timestamptz) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
