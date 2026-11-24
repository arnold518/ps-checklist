BEGIN;

CREATE TABLE app_private.doj_solvedac_links (
    problem_id uuid PRIMARY KEY REFERENCES catalog.problems(id) ON DELETE CASCADE,
    doj_id bigint NOT NULL CHECK (doj_id BETWEEN 1 AND 999999999999999),
    provider_problem_id bigint NOT NULL,
    sub_id text NOT NULL,
    verified_at timestamptz NOT NULL,
    FOREIGN KEY (provider_problem_id,sub_id) REFERENCES app_private.solvedac_difficulty
);
REVOKE ALL ON app_private.doj_solvedac_links FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON app_private.doj_solvedac_links TO service_role;

CREATE FUNCTION catalog.doj_difficulty_targets(p_problem_ids uuid[]) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'problemId',p.id,'dojId',split_part(p.payload->'link'->>'doj','/',6)::bigint,
        'titles',jsonb_build_array(p.doj_metadata#>>'{titles,ko}',p.payload->>'title',p.doj_metadata#>>'{titles,en}'))
        ORDER BY p.id),'[]')
    FROM catalog.problems p
    WHERE cardinality(p_problem_ids) BETWEEN 1 AND 100 AND p.id=ANY(p_problem_ids) AND p.is_public
        AND p.payload->'link'->>'doj' IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM app_private.catalog_boj_problems b
            WHERE b.catalog_problem_id=p.id AND (b.preferred OR b.part_order IS NOT NULL));
$$;

CREATE FUNCTION catalog.save_doj_difficulty(p_observation jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE problem uuid:=(p_observation->>'problemId')::uuid;
    native bigint:=(p_observation->>'dojId')::bigint;
    provider bigint:=(p_observation->>'providerId')::bigint;
    selector text:=p_observation->>'subId';
    fetched timestamptz:=(p_observation->>'fetchedAt')::timestamptz;
    measures jsonb:=p_observation->'measures';
    reference jsonb:=p_observation->'evidence';
BEGIN
    IF problem IS NULL OR native IS NULL OR provider IS NULL OR selector IS NULL OR fetched IS NULL
        OR reference->>'ojId' IS DISTINCT FROM 'doj' OR reference->>'problemId' IS DISTINCT FROM native::text
        OR reference->>'subId' IS DISTINCT FROM ''
        OR NOT app_private.has_json_fields(measures,ARRAY['level','levelAverage','levelStdev','votedUserCount',
            'effectiveVoteCount','isStandard','givesNoRating','noRatingReasons'])
        OR jsonb_typeof(measures->'level') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'Invalid solved.ac snapshot or DOJ reference' USING ERRCODE='22023';
    END IF;
    PERFORM 1 FROM catalog.problems p WHERE p.id=problem AND p.is_public
        AND p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||native::text FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'The catalog DOJ identity changed' USING ERRCODE='22023'; END IF;
    INSERT INTO app_private.solvedac_difficulty AS current(provider_problem_id,sub_id,level,measures,fetched_at)
        VALUES(provider,selector,(measures->>'level')::integer,measures,fetched)
        ON CONFLICT (provider_problem_id,sub_id) DO UPDATE SET
            level=EXCLUDED.level,measures=EXCLUDED.measures,fetched_at=EXCLUDED.fetched_at
        WHERE current.fetched_at<EXCLUDED.fetched_at;
    INSERT INTO app_private.doj_solvedac_links AS current(problem_id,doj_id,provider_problem_id,sub_id,verified_at)
        VALUES(problem,native,provider,selector,fetched)
        ON CONFLICT (problem_id) DO UPDATE SET doj_id=EXCLUDED.doj_id,provider_problem_id=EXCLUDED.provider_problem_id,
            sub_id=EXCLUDED.sub_id,verified_at=EXCLUDED.verified_at
        WHERE current.verified_at<EXCLUDED.verified_at;
    RETURN jsonb_build_object('problemId',problem);
END;
$$;

CREATE FUNCTION catalog.doj_published_ratings(p_ids uuid[])
RETURNS TABLE(problem_id uuid,level integer,fetched_at timestamptz,url text)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT p.id,d.level,d.fetched_at,'https://solved.ac/p/'||d.provider_problem_id||d.sub_id
    FROM catalog.problems p
    JOIN app_private.doj_solvedac_links l ON l.problem_id=p.id
        AND p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||l.doj_id::text
    JOIN app_private.solvedac_difficulty d ON (d.provider_problem_id,d.sub_id)=(l.provider_problem_id,l.sub_id)
    WHERE p.is_public AND p.id=ANY(p_ids)
        AND NOT EXISTS (SELECT 1 FROM app_private.catalog_boj_problems b
            WHERE b.catalog_problem_id=p.id AND (b.preferred OR b.part_order IS NOT NULL));
$$;

CREATE OR REPLACE FUNCTION catalog.solvedac_problem_difficulty(p_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    WITH ratings AS (
        SELECT b.preferred,b.part_order,jsonb_build_object(
            'url','https://solved.ac/p/'||d.provider_problem_id||d.sub_id,
            'level',d.level,'fetchedAt',d.fetched_at) data
        FROM app_private.catalog_boj_problems b
        JOIN catalog.problems p ON p.id=b.catalog_problem_id AND p.is_public
        JOIN app_private.boj_solvedac_links l ON l.boj_problem_id=b.boj_problem_id AND l.outcome='mapped'
        JOIN app_private.solvedac_difficulty d ON (d.provider_problem_id,d.sub_id)=(l.provider_problem_id,l.sub_id)
        WHERE p.id=p_id AND (b.preferred OR b.part_order IS NOT NULL)
    )
    SELECT CASE WHEN count(*)=0 THEN (
        SELECT jsonb_build_object('primary',jsonb_build_object('url',url,'level',level,'fetchedAt',fetched_at),'parts','[]'::jsonb)
        FROM catalog.doj_published_ratings(ARRAY[p_id])
    ) ELSE jsonb_build_object(
        'primary',(SELECT data FROM ratings WHERE preferred),
        'parts',COALESCE(jsonb_agg(data||jsonb_build_object('order',part_order) ORDER BY part_order)
                         FILTER(WHERE part_order IS NOT NULL),'[]')) END
    FROM ratings;
$$;

CREATE OR REPLACE FUNCTION public.problem_difficulty_batch(p_problem_ids uuid[]) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE ratings jsonb;
BEGIN
    IF p_problem_ids IS NULL OR cardinality(p_problem_ids) NOT BETWEEN 1 AND 100 THEN
        RAISE EXCEPTION 'Provide one to one hundred problem IDs' USING ERRCODE='22023';
    END IF;
    SELECT COALESCE(jsonb_object_agg(problem_id,jsonb_build_object('level',level,'fetchedAt',fetched_at)),'{}')
        INTO ratings FROM (
        SELECT p.id AS problem_id,d.level,d.fetched_at
        FROM catalog.problems p
        JOIN app_private.catalog_boj_problems b ON b.catalog_problem_id=p.id AND b.preferred
        JOIN app_private.boj_solvedac_links l ON l.boj_problem_id=b.boj_problem_id AND l.outcome='mapped'
        JOIN app_private.solvedac_difficulty d ON (d.provider_problem_id,d.sub_id)=(l.provider_problem_id,l.sub_id)
        WHERE p.id=ANY(p_problem_ids) AND p.is_public
        UNION ALL
        SELECT problem_id,level,fetched_at FROM catalog.doj_published_ratings(p_problem_ids)
    ) entries;
    RETURN ratings;
END;
$$;

REVOKE ALL ON FUNCTION catalog.doj_difficulty_targets(uuid[]),catalog.save_doj_difficulty(jsonb),
    catalog.doj_published_ratings(uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.doj_difficulty_targets(uuid[]),catalog.save_doj_difficulty(jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.deployment_admin_step(p_id text,p_lease uuid,p_step text,p_function text,p_body jsonb)
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
    WHEN 'admin_publish_boj' THEN answer:=catalog.admin_publish_boj((p_body->>'p_contest_id')::uuid,
        p_body->>'p_version',p_body->>'p_group_id',p_body->'p_source',p_body->'p_matches',(p_body->>'p_reviewer')::uuid);
    WHEN 'save_solvedac_difficulty' THEN answer:=catalog.save_solvedac_difficulty(p_body->'p_observation');
    WHEN 'save_doj_difficulty' THEN answer:=catalog.save_doj_difficulty(p_body->'p_observation');
    WHEN 'stage_boj_problem' THEN answer:=catalog.stage_boj_problem(p_body->'p_problem');
    ELSE RAISE EXCEPTION 'Unsupported administrative write' USING ERRCODE='22023';
    END CASE;
    INSERT INTO app_private.remote_receipts(job_id,step,result) VALUES(p_id,p_step,answer);
    RETURN answer;
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
