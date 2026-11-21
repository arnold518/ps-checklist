-- Admit operator-owned BOJ and solved.ac jobs through the existing queue.
BEGIN;

CREATE OR REPLACE FUNCTION public.deployment_enqueue(p_owner text,p_key text,p_kind text,p_source text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs;
BEGIN
    IF p_owner !~ '^(user:[0-9a-f-]{36}|guest:[0-9a-f]{64}|agent)$'
        OR length(p_key)>200 OR p_kind NOT IN ('fetch','admin')
        OR p_source NOT IN ('cf','atcoder','qoj','ojuz','boj','solvedac','admin','admin-op')
        OR (p_source IN ('boj','solvedac') AND (p_kind<>'fetch' OR p_owner LIKE 'guest:%'))
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

COMMIT;
