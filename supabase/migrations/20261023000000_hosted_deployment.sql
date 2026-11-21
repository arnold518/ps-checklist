-- Hosted API jobs, per-problem votes, and pointers to private note objects.
BEGIN;

CREATE TABLE app_private.remote_jobs (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    request_key text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('fetch','admin')),
    source text NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED')),
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    next_run timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease uuid,
    lease_until timestamptz,
    result_key text,
    http_status integer,
    CONSTRAINT remote_job_payload_limit CHECK (octet_length(payload::text) <= 2097152)
);
CREATE UNIQUE INDEX remote_jobs_active ON app_private.remote_jobs(owner_key,request_key)
    WHERE status IN ('QUEUED','RUNNING');
CREATE INDEX remote_jobs_schedule ON app_private.remote_jobs(source,status,next_run);
CREATE INDEX remote_jobs_retention ON app_private.remote_jobs(updated_at);
CREATE TABLE app_private.remote_agent (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    seen_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE app_private.remote_receipts (
    job_id text REFERENCES app_private.remote_jobs(id) ON DELETE CASCADE,
    step text NOT NULL,
    result jsonb,
    PRIMARY KEY(job_id,step)
);
CREATE TABLE app_private.remote_rate_limits (
    key text PRIMARY KEY,
    window_start timestamptz NOT NULL,
    amount integer NOT NULL
);
CREATE TABLE app_private.catalog_order (
    url text PRIMARY KEY,
    position numeric NOT NULL CHECK (position >= 0)
);
REVOKE ALL ON app_private.remote_jobs,app_private.remote_agent,app_private.remote_receipts,
    app_private.remote_rate_limits,app_private.catalog_order FROM PUBLIC,anon,authenticated;
GRANT ALL ON app_private.remote_jobs,app_private.remote_agent,app_private.remote_receipts,
    app_private.remote_rate_limits,app_private.catalog_order TO service_role;

CREATE FUNCTION app_private.remote_job_json(j app_private.remote_jobs)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('id',j.id,'owner',j.owner_key,'kind',j.kind,'source',j.source,
        'request',j.payload,'status',j.status,'attempts',j.attempts,
        'createdAt',extract(epoch FROM j.created_at),'updatedAt',extract(epoch FROM j.updated_at),
        'nextRunAt',extract(epoch FROM j.next_run),'lease',j.lease,'leaseUntil',j.lease_until,
        'resultKey',j.result_key,'httpStatus',j.http_status);
$$;

CREATE FUNCTION public.deployment_rate_limit(p_key text,p_limit integer,p_seconds integer)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE n integer;
BEGIN
    IF length(p_key)>200 OR p_limit NOT BETWEEN 1 AND 100000 OR p_seconds NOT BETWEEN 1 AND 86400 THEN
        RAISE EXCEPTION 'Invalid rate limit' USING ERRCODE='22023';
    END IF;
    INSERT INTO app_private.remote_rate_limits AS limits(key,window_start,amount)
    VALUES(p_key,clock_timestamp(),1)
    ON CONFLICT(key) DO UPDATE SET
        amount=CASE WHEN limits.window_start < clock_timestamp()-make_interval(secs=>p_seconds) THEN 1 ELSE limits.amount+1 END,
        window_start=CASE WHEN limits.window_start < clock_timestamp()-make_interval(secs=>p_seconds)
            THEN clock_timestamp() ELSE limits.window_start END RETURNING amount INTO n;
    DELETE FROM app_private.remote_rate_limits WHERE window_start<clock_timestamp()-interval '2 days';
    RETURN n<=p_limit;
END;
$$;

CREATE FUNCTION public.deployment_enqueue(p_owner text,p_key text,p_kind text,p_source text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs;
BEGIN
    IF p_owner !~ '^(user:[0-9a-f-]{36}|guest:[0-9a-f]{64}|agent)$'
        OR length(p_key)>200 OR p_kind NOT IN ('fetch','admin')
        OR p_source NOT IN ('cf','atcoder','qoj','ojuz','admin','admin-op')
        OR jsonb_typeof(p_payload)<>'object' THEN
        RAISE EXCEPTION 'Invalid job' USING ERRCODE='22023';
    END IF;
    -- Global admission lock keeps capacity/owner limits correct under concurrency.
    PERFORM pg_advisory_xact_lock(hashtextextended('remote-job-admission',0));
    DELETE FROM app_private.remote_jobs WHERE updated_at<clock_timestamp()-interval '7 days'
        AND (status IN ('DONE','FAILED') OR status='QUEUED');
    SELECT * INTO j FROM app_private.remote_jobs
        WHERE owner_key=p_owner AND request_key=p_key AND
            (status IN ('QUEUED','RUNNING') OR
                (p_kind='fetch' AND status='DONE' AND updated_at>clock_timestamp()-interval '5 minutes'))
        ORDER BY created_at DESC LIMIT 1;
    IF FOUND THEN RETURN app_private.remote_job_json(j); END IF;
    IF (SELECT count(*) FROM app_private.remote_jobs WHERE status IN ('QUEUED','RUNNING'))>=256
        OR (p_owner<>'agent' AND (SELECT count(*) FROM app_private.remote_jobs
            WHERE owner_key=p_owner AND status IN ('QUEUED','RUNNING'))>=20) THEN
        RAISE EXCEPTION 'The fetch queue is full. Try again later.' USING ERRCODE='53300';
    END IF;
    INSERT INTO app_private.remote_jobs(id,owner_key,request_key,kind,source,payload)
        VALUES(replace(gen_random_uuid()::text,'-',''),p_owner,p_key,p_kind,p_source,p_payload) RETURNING * INTO j;
    RETURN app_private.remote_job_json(j);
END;
$$;

CREATE FUNCTION public.deployment_job(p_id text,p_owner text DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT app_private.remote_job_json(j) FROM app_private.remote_jobs j
        WHERE id=p_id AND (p_owner IS NULL OR owner_key=p_owner);
$$;

CREATE FUNCTION public.deployment_claim()
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs;
BEGIN
    INSERT INTO app_private.remote_agent(id) VALUES(true)
        ON CONFLICT(id) DO UPDATE SET seen_at=clock_timestamp();
    PERFORM pg_advisory_xact_lock(hashtextextended('remote-job-claim',0));
    UPDATE app_private.remote_jobs SET status='FAILED',http_status=503,updated_at=clock_timestamp()
        WHERE status='RUNNING' AND lease_until<clock_timestamp() AND attempts>=3;
    SELECT * INTO j FROM app_private.remote_jobs candidate
        WHERE ((status='QUEUED' AND next_run<=clock_timestamp()) OR
            (status='RUNNING' AND lease_until<clock_timestamp() AND attempts<3))
        AND NOT EXISTS(SELECT 1 FROM app_private.remote_jobs active
            WHERE active.source=candidate.source AND active.status='RUNNING'
                AND active.lease_until>clock_timestamp())
        ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    UPDATE app_private.remote_jobs SET status='RUNNING',attempts=attempts+1,
        lease=gen_random_uuid(),lease_until=clock_timestamp()+interval '2 minutes',updated_at=clock_timestamp()
        WHERE id=j.id RETURNING * INTO j;
    RETURN app_private.remote_job_json(j);
END;
$$;

CREATE FUNCTION public.deployment_heartbeat(p_id text,p_lease uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    INSERT INTO app_private.remote_agent(id) VALUES(true)
        ON CONFLICT(id) DO UPDATE SET seen_at=clock_timestamp();
    UPDATE app_private.remote_jobs SET lease_until=clock_timestamp()+interval '2 minutes'
        WHERE id=p_id AND lease=p_lease AND status='RUNNING' AND lease_until>clock_timestamp();
    RETURN FOUND;
END;
$$;

CREATE FUNCTION public.deployment_finish(p_id text,p_lease uuid,p_result_key text,p_status integer,
    p_retry boolean DEFAULT false,p_delay integer DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs;
BEGIN
    SELECT * INTO j FROM app_private.remote_jobs WHERE id=p_id FOR UPDATE;
    IF NOT FOUND OR j.lease IS DISTINCT FROM p_lease THEN
        RAISE EXCEPTION 'Job ownership expired' USING ERRCODE='40001';
    END IF;
    IF j.status IN ('DONE','FAILED') AND j.result_key=p_result_key THEN RETURN app_private.remote_job_json(j); END IF;
    IF j.status<>'RUNNING' OR j.lease_until<=clock_timestamp()
        OR p_result_key IS DISTINCT FROM 'jobs/'||p_id||'/'||p_lease::text||'.json'
        OR p_status NOT BETWEEN 200 AND 599 THEN
        RAISE EXCEPTION 'Invalid completion or expired claim' USING ERRCODE='40001';
    END IF;
    UPDATE app_private.remote_jobs SET status=CASE
            WHEN p_retry AND attempts<3 THEN 'QUEUED'
            WHEN p_status BETWEEN 200 AND 299 THEN 'DONE' ELSE 'FAILED' END,
        result_key=p_result_key,http_status=p_status,updated_at=clock_timestamp(),
        next_run=clock_timestamp()+make_interval(secs=>greatest(least(p_delay,86400),power(2,attempts)::integer)),
        lease_until=NULL WHERE id=p_id RETURNING * INTO j;
    RETURN app_private.remote_job_json(j);
END;
$$;

CREATE FUNCTION public.deployment_status()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('online',COALESCE((SELECT seen_at>clock_timestamp()-interval '90 seconds'
        FROM app_private.remote_agent WHERE id),false),
        'lastSeen',(SELECT seen_at FROM app_private.remote_agent WHERE id));
$$;

CREATE FUNCTION public.deployment_set_order(p_rows jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    DELETE FROM app_private.catalog_order;
    INSERT INTO app_private.catalog_order(url,position)
        SELECT key,value::text::numeric FROM jsonb_each(p_rows);
END;
$$;
CREATE FUNCTION public.deployment_order()
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_object_agg(id,position),'{}') FROM (
        SELECT c.id,COALESCE(explicit.position,min(o.position)) position FROM catalog.contests c
        LEFT JOIN app_private.catalog_order explicit ON explicit.url='id:'||c.id::text
        CROSS JOIN LATERAL jsonb_each_text(c.payload->'link') link
        LEFT JOIN app_private.catalog_order o ON o.url=link.value WHERE c.is_public
        GROUP BY c.id,explicit.position HAVING COALESCE(explicit.position,min(o.position)) IS NOT NULL
    ) rows;
$$;
CREATE FUNCTION public.deployment_catalog()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT catalog.read_catalog(true)||jsonb_build_object('rawOrder',public.deployment_order());
$$;
CREATE FUNCTION public.deployment_state()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_set(user_data.read_state(),'{catalog,rawOrder}',public.deployment_order(),true);
$$;

-- Fenced, transactional receipts make administrative retries return the first
-- successful write instead of repeating a publication after a lost response.
CREATE FUNCTION public.deployment_admin_step(p_id text,p_lease uuid,p_step text,p_function text,p_body jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs; answer jsonb;
BEGIN
    SELECT * INTO j FROM app_private.remote_jobs WHERE id=p_id FOR UPDATE;
    IF NOT FOUND OR j.kind<>'admin' OR j.lease IS DISTINCT FROM p_lease OR j.status<>'RUNNING'
        OR j.lease_until<=clock_timestamp() THEN
        RAISE EXCEPTION 'Job ownership expired' USING ERRCODE='40001';
    END IF;
    SELECT result INTO answer FROM app_private.remote_receipts WHERE job_id=p_id AND step=p_step;
    IF FOUND THEN RETURN answer; END IF;
    CASE p_function
    WHEN 'admin_publish_archived' THEN answer:=catalog.admin_publish_archived(p_body->'p_contest',p_body->'p_problems',
        p_body->'p_versions',p_body->'p_refresh',p_body->'p_archives');
    WHEN 'admin_remove' THEN answer:=catalog.admin_remove((p_body->>'p_id')::uuid,p_body->>'p_version');
    WHEN 'admin_workspace_save' THEN answer:=catalog.admin_workspace_save((p_body->>'p_user_id')::uuid,
        (p_body->>'p_revision')::uuid,p_body->'p_changes');
    WHEN 'admin_workspace_publish' THEN answer:=catalog.admin_workspace_publish((p_body->>'p_user_id')::uuid,
        (p_body->>'p_revision')::uuid,ARRAY(SELECT jsonb_array_elements_text(p_body->'p_ids'))::uuid[]);
    ELSE RAISE EXCEPTION 'Unsupported administrative write' USING ERRCODE='22023';
    END CASE;
    INSERT INTO app_private.remote_receipts(job_id,step,result) VALUES(p_id,p_step,answer);
    RETURN answer;
END;
$$;

CREATE TABLE user_data.difficulty_votes (
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    value smallint NOT NULL CHECK (value BETWEEN 1 AND 10),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(user_id,problem_id)
);
CREATE INDEX difficulty_votes_problem ON user_data.difficulty_votes(problem_id);
ALTER TABLE user_data.difficulty_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_data.difficulty_votes FORCE ROW LEVEL SECURITY;
CREATE POLICY own_vote ON user_data.difficulty_votes TO authenticated USING(user_id=(SELECT auth.uid()))
    WITH CHECK(user_id=(SELECT auth.uid()) AND EXISTS(SELECT 1 FROM catalog.problems WHERE id=problem_id AND is_public));
GRANT SELECT,INSERT,DELETE ON user_data.difficulty_votes TO authenticated;
GRANT UPDATE(value,updated_at) ON user_data.difficulty_votes TO authenticated;
GRANT ALL ON user_data.difficulty_votes TO service_role;

CREATE TABLE user_data.problem_notes (
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    version uuid NOT NULL,
    object_key text NOT NULL,
    size integer NOT NULL CHECK (size BETWEEN 0 AND 131072),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(user_id,problem_id),
    CHECK(object_key='notes/'||user_id::text||'/'||problem_id::text||'/'||version::text||'.md')
);
ALTER TABLE user_data.problem_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_data.problem_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY own_note ON user_data.problem_notes TO authenticated USING(user_id=(SELECT auth.uid()))
    WITH CHECK(user_id=(SELECT auth.uid()) AND EXISTS(SELECT 1 FROM catalog.problems WHERE id=problem_id AND is_public));
GRANT SELECT,INSERT,DELETE ON user_data.problem_notes TO authenticated;
GRANT UPDATE(version,object_key,size,updated_at) ON user_data.problem_notes TO authenticated;
GRANT ALL ON user_data.problem_notes TO service_role;

CREATE FUNCTION public.problem_difficulty(p_problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('count',count(*),'average',round(avg(value),2),
        'vote',max(value) FILTER(WHERE user_id=auth.uid())) FROM user_data.difficulty_votes
        WHERE problem_id=p_problem_id AND EXISTS(SELECT 1 FROM catalog.problems WHERE id=p_problem_id AND is_public);
$$;
CREATE FUNCTION public.set_problem_difficulty(p_problem_id uuid,p_value integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_value IS NULL THEN DELETE FROM user_data.difficulty_votes WHERE problem_id=p_problem_id AND user_id=auth.uid();
    ELSE INSERT INTO user_data.difficulty_votes(problem_id,value) VALUES(p_problem_id,p_value)
        ON CONFLICT(user_id,problem_id) DO UPDATE SET value=EXCLUDED.value,updated_at=clock_timestamp(); END IF;
    RETURN public.problem_difficulty(p_problem_id);
END;
$$;
CREATE FUNCTION public.problem_note(p_problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('version',version,'key',object_key,'size',size,'updatedAt',updated_at)
        FROM user_data.problem_notes WHERE user_id=auth.uid() AND problem_id=p_problem_id;
$$;
CREATE FUNCTION public.save_problem_note(p_problem_id uuid,p_expected uuid,p_version uuid,p_size integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE previous user_data.problem_notes; next_key text;
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('note:'||auth.uid()::text||':'||p_problem_id::text,0));
    SELECT * INTO previous FROM user_data.problem_notes WHERE user_id=auth.uid() AND problem_id=p_problem_id;
    IF previous.version IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'Note changed. Reload before saving.' USING ERRCODE='40001'; END IF;
    IF p_version IS NULL THEN
        DELETE FROM user_data.problem_notes WHERE user_id=auth.uid() AND problem_id=p_problem_id;
    ELSE
        next_key:='notes/'||auth.uid()::text||'/'||p_problem_id::text||'/'||p_version::text||'.md';
        INSERT INTO user_data.problem_notes(problem_id,version,object_key,size) VALUES(p_problem_id,p_version,next_key,p_size)
        ON CONFLICT(user_id,problem_id) DO UPDATE SET version=EXCLUDED.version,object_key=EXCLUDED.object_key,
            size=EXCLUDED.size,updated_at=clock_timestamp();
    END IF;
    RETURN jsonb_build_object('previousKey',previous.object_key,'note',public.problem_note(p_problem_id));
END;
$$;

REVOKE ALL ON FUNCTION app_private.remote_job_json(app_private.remote_jobs),public.deployment_order() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_private.remote_job_json(app_private.remote_jobs) TO service_role;
GRANT EXECUTE ON FUNCTION public.deployment_order() TO anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.deployment_rate_limit(text,integer,integer),
    public.deployment_enqueue(text,text,text,text,jsonb),public.deployment_job(text,text),
    public.deployment_claim(),public.deployment_heartbeat(text,uuid),
    public.deployment_finish(text,uuid,text,integer,boolean,integer),public.deployment_status(),
    public.deployment_set_order(jsonb),public.deployment_admin_step(text,uuid,text,text,jsonb)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.deployment_rate_limit(text,integer,integer),
    public.deployment_enqueue(text,text,text,text,jsonb),public.deployment_job(text,text),
    public.deployment_claim(),public.deployment_heartbeat(text,uuid),
    public.deployment_finish(text,uuid,text,integer,boolean,integer),public.deployment_status(),
    public.deployment_set_order(jsonb),public.deployment_admin_step(text,uuid,text,text,jsonb) TO service_role;
REVOKE ALL ON FUNCTION public.deployment_catalog(),public.deployment_state(),public.problem_difficulty(uuid),
    public.set_problem_difficulty(uuid,integer),public.problem_note(uuid),public.save_problem_note(uuid,uuid,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.deployment_catalog(),public.problem_difficulty(uuid) TO anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.deployment_state(),public.set_problem_difficulty(uuid,integer),
    public.problem_note(uuid),public.save_problem_note(uuid,uuid,uuid,integer) TO authenticated,service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
