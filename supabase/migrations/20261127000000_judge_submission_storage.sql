-- Private judge evidence and catalog-scoped reads for submission synchronization.
BEGIN;

CREATE FUNCTION app_private.judge_problem_key(p_judge text, p_url text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
    SELECT array_to_string(CASE WHEN p_judge='cf' THEN COALESCE(
        regexp_match(p_url,'^https://codeforces[.]com/(?:contest|gym)/([1-9][0-9]*)/problem/([A-Za-z0-9]+)$'),
        regexp_match(p_url,'^https://codeforces[.]com/(?:problemset/problem|problemsets/acmsguru/problem)/([1-9][0-9]*)/([A-Za-z0-9]+)$')
    ) ELSE regexp_match(p_url, CASE p_judge
        WHEN 'atcoder' THEN '^https://atcoder[.]jp/contests/([A-Za-z0-9_-]+)/tasks/([A-Za-z0-9_-]+)$'
        WHEN 'boj' THEN '^https://(?:www[.])?acmicpc[.]net/problem/([1-9][0-9]*)$'
        WHEN 'doj' THEN '^https://(?:www[.])?doj[.]kr/(?:en|ko|ja|zh-CN)/problems/([1-9][0-9]*)$'
        WHEN 'ojuz' THEN '^https://oj[.]uz/problem/view/([A-Za-z0-9_-]+)$'
        WHEN 'qoj' THEN '^https://qoj[.]ac/(?:contest/[1-9][0-9]*/)?problem/([1-9][0-9]*)$'
    END) END, '/');
$$;

CREATE FUNCTION app_private.judge_submission_url_id(p_judge text, p_url text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
    SELECT substring(p_url FROM CASE p_judge
        WHEN 'cf' THEN '^https://codeforces[.]com/(?:(?:contest|gym)/[1-9][0-9]*|problemsets/[A-Za-z0-9_-]+)/submission/([1-9][0-9]*)$'
        WHEN 'atcoder' THEN '^https://atcoder[.]jp/contests/[A-Za-z0-9_-]+/submissions/([1-9][0-9]*)$'
        WHEN 'boj' THEN '^https://(?:www[.])?acmicpc[.]net/source/([1-9][0-9]*)$'
        WHEN 'doj' THEN '^https://(?:www[.])?doj[.]kr/(?:en|ko|ja|zh-CN)/submissions/([A-Za-z0-9_-]+)$'
        WHEN 'ojuz' THEN '^https://oj[.]uz/submission/([1-9][0-9]*)$'
        WHEN 'qoj' THEN '^https://qoj[.]ac/submission/([1-9][0-9]*)$'
    END);
$$;

CREATE TABLE app_private.judge_sync_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source text NOT NULL CHECK (source IN ('cf','atcoder','boj','solvedac','doj','ojuz','qoj')),
    judge text GENERATED ALWAYS AS (CASE WHEN source='solvedac' THEN 'boj' ELSE source END) STORED,
    handle text NOT NULL CHECK (handle ~ '^[A-Za-z0-9_.-]{1,64}$'),
    linked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (user_id,source),
    UNIQUE (id,judge)
);

CREATE TABLE app_private.judge_sync_checkpoints (
    account_id uuid NOT NULL REFERENCES app_private.judge_sync_accounts(id) ON DELETE CASCADE,
    feed text NOT NULL CHECK (feed IN ('submissions','progress')),
    cursor jsonb NOT NULL CHECK (jsonb_typeof(cursor)='object' AND octet_length(cursor::text)<=4096),
    revision bigint NOT NULL CHECK (revision>0),
    committed_at timestamptz NOT NULL,
    PRIMARY KEY (account_id,feed)
);

CREATE TABLE app_private.judge_submissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL,
    judge text NOT NULL,
    native_submission_id text NOT NULL CHECK (native_submission_id ~ '^[A-Za-z0-9_-]{1,100}$'),
    submission_url text NOT NULL CHECK (
        app_private.judge_submission_url_id(judge,submission_url) IS NOT DISTINCT FROM native_submission_id
        AND length(submission_url)<=500),
    problem_url text,
    native_problem_key text GENERATED ALWAYS AS (app_private.judge_problem_key(judge,problem_url)) STORED,
    native_contest_url text CHECK (native_contest_url IS NULL OR (
        length(native_contest_url)<=500 AND native_contest_url ~ '^https://[a-z.]+/[A-Za-z0-9/_-]+$'
        AND split_part(native_contest_url,'/',3)=split_part(submission_url,'/',3))),
    participation text NOT NULL DEFAULT 'unknown'
        CHECK (participation IN ('contest','virtual','practice','unknown')),
    submitted_at timestamptz CHECK (isfinite(submitted_at)),
    result text NOT NULL CHECK (result IN ('pending','accepted','partial','rejected','unknown')),
    verdict text CHECK (length(btrim(verdict)) BETWEEN 1 AND 100 AND verdict !~ '[[:cntrl:]]'),
    language text CHECK (length(btrim(language)) BETWEEN 1 AND 120 AND language !~ '[[:cntrl:]]'),
    score double precision CHECK (abs(score)<'Infinity'::double precision),
    max_score double precision CHECK (max_score>=0 AND max_score<'Infinity'::double precision),
    runtime_ms bigint CHECK (runtime_ms>=0),
    memory_bytes bigint CHECK (memory_bytes>=0),
    fetched_at timestamptz CHECK (isfinite(fetched_at)),
    observed_at timestamptz NOT NULL,
    FOREIGN KEY (account_id,judge) REFERENCES app_private.judge_sync_accounts(id,judge) ON DELETE CASCADE,
    CHECK (problem_url IS NULL OR (length(problem_url)<=500 AND native_problem_key IS NOT NULL)),
    UNIQUE (account_id,native_submission_id)
);
CREATE INDEX judge_submissions_timeline ON app_private.judge_submissions
    (account_id, (COALESCE(submitted_at,'-infinity'::timestamptz)) DESC, id DESC);
CREATE INDEX judge_submissions_problem ON app_private.judge_submissions
    (account_id, native_problem_key, (COALESCE(submitted_at,'-infinity'::timestamptz)) DESC, id DESC)
    WHERE native_problem_key IS NOT NULL;

CREATE TABLE app_private.judge_progress_observations (
    account_id uuid NOT NULL,
    judge text NOT NULL,
    problem_url text NOT NULL CHECK (length(problem_url)<=500),
    native_problem_key text GENERATED ALWAYS AS (app_private.judge_problem_key(judge,problem_url)) STORED,
    status integer NOT NULL CHECK (status BETWEEN 0 AND 2),
    observed_at timestamptz NOT NULL,
    FOREIGN KEY (account_id,judge) REFERENCES app_private.judge_sync_accounts(id,judge) ON DELETE CASCADE,
    PRIMARY KEY (account_id,native_problem_key)
);

ALTER TABLE app_private.judge_sync_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.judge_sync_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.judge_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.judge_progress_observations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_private.judge_sync_accounts,app_private.judge_sync_checkpoints,
    app_private.judge_submissions,app_private.judge_progress_observations FROM PUBLIC,anon,authenticated,service_role;

-- Use current published bindings to resolve even history imported before a catalog entry existed.
CREATE VIEW app_private.judge_problem_bindings AS
WITH native_links AS (
    SELECT p.id AS problem_id, j.judge, app_private.judge_problem_key(j.judge,p.payload->'link'->>j.judge) AS native_key
    FROM catalog.problems p
    CROSS JOIN (VALUES ('cf'),('atcoder'),('doj'),('ojuz'),('qoj')) AS j(judge)
    WHERE p.is_public
), unambiguous AS (
    SELECT n.*, count(*) OVER (PARTITION BY judge,native_key) AS candidates
    FROM native_links n WHERE native_key IS NOT NULL
)
SELECT problem_id,judge,native_key,NULL::integer AS part_order FROM unambiguous WHERE candidates=1
UNION ALL
SELECT b.catalog_problem_id,'boj',b.boj_problem_id::text,b.part_order
FROM app_private.catalog_boj_problems b JOIN catalog.problems p ON p.id=b.catalog_problem_id WHERE p.is_public;

CREATE FUNCTION public.set_judge_sync_account(p_source text,p_handle text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE owner_id uuid := auth.uid(); account_id uuid;
BEGIN
    IF owner_id IS NULL THEN RAISE EXCEPTION 'Login required' USING ERRCODE='42501'; END IF;
    IF p_source IS NULL OR p_source NOT IN ('cf','atcoder','boj','solvedac','doj','ojuz','qoj')
        OR (p_handle IS NOT NULL AND p_handle !~ '^[A-Za-z0-9_.-]{1,64}$')
    THEN RAISE EXCEPTION 'Invalid judge source or handle' USING ERRCODE='22023'; END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('judge-account:'||owner_id::text||':'||p_source,0));
    DELETE FROM app_private.judge_sync_accounts
    WHERE user_id=owner_id AND source=p_source AND handle IS DISTINCT FROM p_handle;
    IF p_handle IS NULL THEN RETURN NULL; END IF;
    INSERT INTO app_private.judge_sync_accounts(user_id,source,handle)
    VALUES(owner_id,p_source,p_handle) ON CONFLICT (user_id,source) DO NOTHING;
    SELECT id INTO account_id FROM app_private.judge_sync_accounts WHERE user_id=owner_id AND source=p_source;
    RETURN account_id;
END;
$$;

CREATE FUNCTION public.judge_sync_accounts()
RETURNS TABLE(id uuid,source text,judge text,handle text,linked_at timestamptz,
              submissions_committed_at timestamptz,progress_committed_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT a.id,a.source,a.judge,a.handle,a.linked_at,s.committed_at,p.committed_at
    FROM app_private.judge_sync_accounts a
    LEFT JOIN app_private.judge_sync_checkpoints s ON s.account_id=a.id AND s.feed='submissions'
    LEFT JOIN app_private.judge_sync_checkpoints p ON p.account_id=a.id AND p.feed='progress'
    WHERE a.user_id=auth.uid() ORDER BY a.source;
$$;

CREATE FUNCTION public.judge_sync_targets(p_after uuid DEFAULT NULL,p_limit integer DEFAULT 50,p_account_id uuid DEFAULT NULL)
RETURNS TABLE(id uuid,source text,judge text,handle text,checkpoints jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT a.id,a.source,a.judge,a.handle,
        COALESCE((SELECT jsonb_object_agg(c.feed,jsonb_build_object(
            'cursor',c.cursor,'revision',c.revision,'committedAt',c.committed_at))
        FROM app_private.judge_sync_checkpoints c WHERE c.account_id=a.id),'{}'::jsonb)
    FROM app_private.judge_sync_accounts a
    WHERE (p_after IS NULL OR a.id>p_after) AND (p_account_id IS NULL OR a.id=p_account_id)
    ORDER BY a.id LIMIT GREATEST(1,LEAST(100,COALESCE(p_limit,50)));
$$;

-- A scheduler reads targets and cursors. A page commits only against the revision it read.
CREATE FUNCTION public.commit_judge_sync_batch(
    p_account_id uuid,p_feed text,p_expected_revision bigint,p_cursor jsonb,p_records jsonb
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account app_private.judge_sync_accounts; revision bigint; observed timestamptz;
BEGIN
    IF p_feed IS NULL OR p_feed NOT IN ('submissions','progress')
        OR p_expected_revision IS NULL OR p_expected_revision<0
        OR jsonb_typeof(p_cursor) IS DISTINCT FROM 'object' OR octet_length(p_cursor::text)>4096
        OR jsonb_typeof(p_records) IS DISTINCT FROM 'array'
    THEN RAISE EXCEPTION 'Invalid judge sync batch' USING ERRCODE='22023'; END IF;
    IF jsonb_array_length(p_records)>500 THEN
        RAISE EXCEPTION 'Judge sync batch exceeds 500 records' USING ERRCODE='22023';
    END IF;

    SELECT * INTO account FROM app_private.judge_sync_accounts WHERE id=p_account_id FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF (p_feed='submissions' AND account.source='solvedac')
        OR (p_feed='progress' AND account.source NOT IN ('solvedac','ojuz','doj'))
    THEN RAISE EXCEPTION 'This source does not provide the requested feed' USING ERRCODE='22023'; END IF;

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

CREATE FUNCTION public.judge_problem_status(p_problem_id uuid DEFAULT NULL)
RETURNS TABLE(problem_id uuid,manual_status integer,synced_status integer,status integer)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    WITH owned AS (
        SELECT id FROM app_private.judge_sync_accounts WHERE user_id=auth.uid()
    ), bindings AS MATERIALIZED (
        SELECT b.* FROM app_private.judge_problem_bindings b WHERE p_problem_id IS NULL OR b.problem_id=p_problem_id
    ), evidence AS (
        SELECT s.account_id,s.judge,s.native_problem_key,
            CASE s.result WHEN 'accepted' THEN 2 ELSE 1 END AS status
        FROM owned a JOIN app_private.judge_submissions s ON s.account_id=a.id
        WHERE EXISTS (SELECT 1 FROM bindings b WHERE b.judge=s.judge AND b.native_key=s.native_problem_key)
        UNION ALL
        SELECT p.account_id,p.judge,p.native_problem_key,p.status
        FROM owned a JOIN app_private.judge_progress_observations p ON p.account_id=a.id
        WHERE p.status>0 AND EXISTS (SELECT 1 FROM bindings b WHERE b.judge=p.judge AND b.native_key=p.native_problem_key)
    ), observed AS MATERIALIZED (
        SELECT e.account_id,e.judge,e.native_problem_key,max(e.status) AS status
        FROM evidence e GROUP BY e.account_id,e.judge,e.native_problem_key
    ), candidates AS (
        SELECT DISTINCT e.account_id,b.judge,b.problem_id
        FROM observed e JOIN bindings b ON b.judge=e.judge AND b.native_key=e.native_problem_key
    ), per_account AS (
        SELECT c.problem_id,CASE
            WHEN bool_or(b.part_order IS NULL AND e.status=2) THEN 2
            WHEN count(*) FILTER (WHERE b.part_order IS NOT NULL)>0
              AND bool_and(COALESCE(e.status,0)=2) FILTER (WHERE b.part_order IS NOT NULL) THEN 2
            ELSE 1 END AS status
        FROM candidates c JOIN bindings b ON b.problem_id=c.problem_id AND b.judge=c.judge
        LEFT JOIN observed e ON e.account_id=c.account_id AND e.native_problem_key=b.native_key
        GROUP BY c.problem_id,c.account_id
    ), synced AS (
        SELECT a.problem_id,max(a.status) AS status FROM per_account a GROUP BY a.problem_id
    ), manual AS (
        SELECT d.problem_id,(d.payload->>'status')::integer AS status
        FROM user_data.problem_progress d JOIN catalog.problems p ON p.id=d.problem_id AND p.is_public
        WHERE d.user_id=auth.uid() AND (p_problem_id IS NULL OR d.problem_id=p_problem_id)
    )
    SELECT COALESCE(m.problem_id,s.problem_id),COALESCE(m.status,0),COALESCE(s.status,0),
        GREATEST(COALESCE(m.status,0),COALESCE(s.status,0))
    FROM manual m FULL JOIN synced s USING (problem_id) ORDER BY 1;
$$;

CREATE FUNCTION public.judge_submission_history(
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
            SELECT s.*,a.source,COALESCE(s.submitted_at,'-infinity'::timestamptz) AS sort_time
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
                'id',n.id,'judge',n.judge,'source',n.source,'nativeSubmissionId',n.native_submission_id,
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

REVOKE ALL ON FUNCTION app_private.judge_problem_key(text,text),
    app_private.judge_submission_url_id(text,text) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON app_private.judge_problem_bindings FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.set_judge_sync_account(text,text),public.judge_sync_accounts(),
    public.judge_problem_status(uuid),public.judge_submission_history(uuid,uuid,text,uuid,integer),
    public.judge_sync_targets(uuid,integer,uuid),public.commit_judge_sync_batch(uuid,text,bigint,jsonb,jsonb)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.set_judge_sync_account(text,text),public.judge_sync_accounts(),
    public.judge_problem_status(uuid),public.judge_submission_history(uuid,uuid,text,uuid,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.judge_sync_targets(uuid,integer,uuid),
    public.commit_judge_sync_batch(uuid,text,bigint,jsonb,jsonb) TO service_role;

NOTIFY pgrst,'reload schema';
COMMIT;
