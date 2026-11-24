BEGIN;

CREATE OR REPLACE FUNCTION public.deployment_enqueue(p_owner text,p_key text,p_kind text,p_source text,p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE j app_private.remote_jobs;
BEGIN
    IF p_owner !~ '^(user:[0-9a-f-]{36}|guest:[0-9a-f]{64}|agent)$'
        OR length(p_key)>200 OR p_kind NOT IN ('fetch','admin')
        OR p_source NOT IN ('cf','atcoder','qoj','ojuz','boj','solvedac','doj','admin','admin-op')
        OR (p_source='doj' AND p_kind<>'fetch')
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

CREATE OR REPLACE FUNCTION app_private.valid_platforms(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) NOT BETWEEN 1 AND 4 THEN RETURN false; END IF;
    RETURN NOT EXISTS (SELECT 1 FROM jsonb_array_elements(value) item WHERE item NOT IN ('"cf"'::jsonb, '"atcoder"'::jsonb, '"ojuz"'::jsonb, '"doj"'::jsonb))
        AND (SELECT count(*) = count(DISTINCT item) FROM jsonb_array_elements(value) item);
END;
$$;

CREATE OR REPLACE FUNCTION user_data.remove_saved(p_contest_id uuid, p_source text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder','ojuz','doj') THEN RAISE EXCEPTION 'Invalid platform' USING ERRCODE='22023'; END IF;
    DELETE FROM user_data.saved_contests WHERE contest_id=p_contest_id AND payload->'platforms' = jsonb_build_array(p_source);
    UPDATE user_data.saved_contests SET payload=jsonb_build_object('platforms',(payload->'platforms') - p_source)
        WHERE contest_id=p_contest_id AND payload->'platforms' ? p_source;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION app_private.valid_json_links(value jsonb, fields text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE item jsonb; allowed text[]:=fields; doj_pattern text;
BEGIN
    IF fields @> ARRAY['cf','qoj','atcoder'] THEN
        IF value ? 'ojuz' THEN allowed:=array_append(allowed,'ojuz'); END IF;
        IF value ? 'doj' THEN
            allowed:=array_append(allowed,'doj');
            doj_pattern:=CASE WHEN 'official'=ANY(fields)
                THEN '^https://doj\.kr/en/contests/[A-Za-z0-9][A-Za-z0-9_-]{0,99}$'
                ELSE '^https://doj\.kr/en/problems/[1-9][0-9]{0,14}$' END;
            IF value->>'doj' IS NOT NULL AND value->>'doj' !~ doj_pattern THEN RETURN false; END IF;
        END IF;
    END IF;
    IF NOT app_private.has_json_fields(value,allowed) THEN RETURN false; END IF;
    FOR item IN SELECT entry.value FROM jsonb_each(value) entry LOOP
        IF item <> 'null'::jsonb AND NOT app_private.https_json_url(item) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;

ALTER TABLE catalog.contests ADD COLUMN doj_metadata jsonb CHECK (jsonb_typeof(doj_metadata)='object');
ALTER TABLE catalog.problems ADD COLUMN doj_metadata jsonb CHECK (jsonb_typeof(doj_metadata)='object');
CREATE UNIQUE INDEX contests_doj_identity ON catalog.contests((payload->'link'->>'doj'))
    WHERE payload->'link'->>'doj' IS NOT NULL;
CREATE UNIQUE INDEX problems_doj_identity ON catalog.problems((payload->'link'->>'doj'))
    WHERE payload->'link'->>'doj' IS NOT NULL;

-- Both personal imports and the catalog backfill use the same native identity locks.
CREATE FUNCTION catalog.write_doj(p_contest jsonb, p_problems jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE native jsonb; details jsonb; tasks jsonb; task_url text; contest_url text;
    contest_id uuid; problem_id uuid; was_public boolean; ids jsonb:='{}';
    previous jsonb; basic jsonb; memberships jsonb;
BEGIN
    IF jsonb_typeof(p_problems) IS DISTINCT FROM 'array' OR jsonb_array_length(p_problems)>100 THEN
        RAISE EXCEPTION 'Provide a DOJ problem page of up to 100 records' USING ERRCODE='22023';
    END IF;
    tasks:=p_problems;
    IF p_contest IS NOT NULL THEN
        contest_url:=p_contest->>'url';
        tasks:=p_contest->'problems';
        details:=p_contest->'details';
        IF p_problems<>'[]' OR p_contest->>'source' IS DISTINCT FROM 'doj'
            OR p_contest->>'phase' IS DISTINCT FROM 'FINISHED'
            OR details->>'status' IS DISTINCT FROM 'ENDED' OR details->>'visibility' IS DISTINCT FROM 'PUBLIC'
            OR COALESCE(contest_url,'') !~ '^https://doj\.kr/en/contests/[A-Za-z0-9][A-Za-z0-9_-]{0,99}$'
            OR contest_url IS DISTINCT FROM 'https://doj.kr/en/contests/'||(details->>'slug')
            OR COALESCE(btrim(p_contest->>'name'),'')='' OR jsonb_typeof(tasks) IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'Provide a finished public DOJ contest' USING ERRCODE='22023';
        END IF;
        IF jsonb_array_length(tasks) NOT BETWEEN 1 AND 500
            OR p_contest->'problemCount' IS DISTINCT FROM to_jsonb(jsonb_array_length(tasks))
            OR details->'problemCount' IS DISTINCT FROM p_contest->'problemCount'
            OR (SELECT count(DISTINCT t->>'index') FROM jsonb_array_elements(tasks) t)<>jsonb_array_length(tasks)
            OR EXISTS (SELECT 1 FROM jsonb_array_elements(tasks) t
                WHERE jsonb_typeof(t->'index') IS DISTINCT FROM 'string'
                    OR length(btrim(t->>'index')) NOT BETWEEN 1 AND 100) THEN
            RAISE EXCEPTION 'The DOJ problem list is incomplete' USING ERRCODE='22023';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(contest_url,0));
        SELECT id,is_public INTO contest_id,was_public FROM catalog.contests WHERE payload->'link'->>'doj'=contest_url;
        IF FOUND AND NOT was_public THEN
            RAISE EXCEPTION 'This contest is under catalog review' USING ERRCODE='42501';
        END IF;
    END IF;

    -- Lock shared problem identities in the same order across concurrent rounds.
    FOR native IN SELECT value FROM jsonb_array_elements(tasks) ORDER BY value->>'url' LOOP
        task_url:=native->>'url';
        IF COALESCE(task_url,'') !~ '^https://doj\.kr/en/problems/[1-9][0-9]{0,14}$'
            OR task_url IS DISTINCT FROM 'https://doj.kr/en/problems/'||(native->>'taskId')
            OR ids ? task_url OR COALESCE(btrim(native->>'name'),'')=''
            OR (p_contest IS NULL AND (native->>'source' IS DISTINCT FROM 'doj'
                OR jsonb_typeof(native->'details') IS DISTINCT FROM 'object'
                OR native->'details'->'displayId' IS DISTINCT FROM native->'taskId')) THEN
            RAISE EXCEPTION 'Invalid or repeated DOJ problem identity' USING ERRCODE='22023';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(task_url,0));
        SELECT id,is_public INTO problem_id,was_public FROM catalog.problems WHERE payload->'link'->>'doj'=task_url;
        IF NOT FOUND THEN
            INSERT INTO catalog.problems(payload,is_public) VALUES (
                jsonb_build_object('title',native->>'name','link',
                    jsonb_build_object('cf',NULL,'qoj',NULL,'atcoder',NULL,'doj',task_url)),true)
                RETURNING id INTO problem_id;
        ELSIF NOT was_public THEN
            RAISE EXCEPTION 'A DOJ problem is under catalog review' USING ERRCODE='42501';
        END IF;
        IF p_contest IS NULL THEN
            details:=native->'details'||jsonb_build_object('limits',native->'limits',
                'tags',native->'tags','problemType',native->'type');
            UPDATE catalog.problems SET doj_metadata=details WHERE id=problem_id AND doj_metadata IS DISTINCT FROM details;
        END IF;
        ids:=ids||jsonb_build_object(task_url,problem_id);
    END LOOP;
    IF p_contest IS NULL THEN RETURN NULL; END IF;

    previous:=catalog.contest_json(contest_id);
    contest_id:=COALESCE(contest_id,gen_random_uuid());
    IF previous IS NULL OR previous->'category'='null'::jsonb THEN
        SELECT jsonb_agg(jsonb_build_object('problemId',ids->(item->>'url'),'index',item->'index') ORDER BY position)
            INTO memberships FROM jsonb_array_elements(tasks) WITH ORDINALITY rows(item,position);
        basic:=COALESCE(previous,jsonb_build_object('id',contest_id,'category',NULL,'materials','[]'::jsonb,
            'link',jsonb_build_object('cf',NULL,'qoj',NULL,'atcoder',NULL,'official',NULL,
                'doj',contest_url,'standings',contest_url||'/standings')))
            ||jsonb_build_object('title',p_contest->>'name','year',left(p_contest->>'startTime',4),'problems',memberships);
        IF basic IS DISTINCT FROM previous THEN
            PERFORM catalog.write_catalog(jsonb_build_array(basic),'[]',true);
        END IF;
    END IF;
    UPDATE catalog.contests SET doj_metadata=details WHERE id=contest_id AND doj_metadata IS DISTINCT FROM details;
    RETURN contest_id;
END;
$$;

ALTER FUNCTION catalog.import_round(text,jsonb,uuid) RENAME TO import_legacy_round;
CREATE FUNCTION catalog.import_round(p_source text,p_native jsonb,p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE entity_id uuid; saved jsonb; round jsonb; problems jsonb;
BEGIN
    IF p_source IS DISTINCT FROM 'doj' THEN
        RETURN catalog.import_legacy_round(p_source,p_native,p_user_id);
    END IF;
    IF p_native IS NULL THEN
        RAISE EXCEPTION 'Provide a finished public DOJ contest' USING ERRCODE='22023';
    END IF;
    entity_id:=catalog.write_doj(p_native,'[]');
    IF p_user_id IS NULL THEN
        saved:=jsonb_build_array(p_source);
    ELSE
        INSERT INTO user_data.saved_contests(user_id,contest_id,payload)
            VALUES(p_user_id,entity_id,jsonb_build_object('platforms',jsonb_build_array(p_source)))
            ON CONFLICT(user_id,contest_id) DO UPDATE SET payload=jsonb_build_object('platforms',
                CASE WHEN user_data.saved_contests.payload->'platforms' ? p_source
                    THEN user_data.saved_contests.payload->'platforms'
                    ELSE (user_data.saved_contests.payload->'platforms')||jsonb_build_array(p_source) END)
            RETURNING payload->'platforms' INTO saved;
    END IF;
    round:=catalog.contest_json(entity_id);
    SELECT COALESCE(jsonb_agg(catalog.problem_json((entry->>'problemId')::uuid) ORDER BY position),'[]')
        INTO problems FROM jsonb_array_elements(round->'problems') WITH ORDINALITY rows(entry,position);
    RETURN jsonb_build_object('contest',round,'problems',problems,
        'saved',jsonb_build_object('contestId',entity_id,'platforms',saved));
END;
$$;

REVOKE ALL ON FUNCTION catalog.import_round(text,jsonb,uuid),catalog.write_doj(jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.import_round(text,jsonb,uuid),catalog.write_doj(jsonb,jsonb) TO service_role;
COMMIT;
