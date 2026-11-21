BEGIN;

CREATE TABLE app_private.solvedac_difficulty (
    provider_problem_id bigint NOT NULL CHECK (provider_problem_id BETWEEN 1 AND 999999999999999),
    sub_id text NOT NULL CHECK (sub_id ~ '^[a-z]{0,16}$'),
    level integer NOT NULL CHECK (level >= 0),
    measures jsonb NOT NULL CHECK (jsonb_typeof(measures)='object'),
    fetched_at timestamptz NOT NULL,
    PRIMARY KEY (provider_problem_id,sub_id)
);
CREATE TABLE app_private.boj_solvedac_links (
    boj_problem_id bigint PRIMARY KEY REFERENCES app_private.boj_problems(problem_id),
    provider_problem_id bigint,
    sub_id text,
    outcome text NOT NULL CHECK(outcome IN ('mapped','unmapped','needs_review')),
    checked_at timestamptz NOT NULL,
    evidence jsonb,
    FOREIGN KEY (provider_problem_id,sub_id) REFERENCES app_private.solvedac_difficulty MATCH FULL,
    CHECK ((outcome='mapped')=(provider_problem_id IS NOT NULL)),
    CHECK ((outcome='mapped')=(evidence IS NOT NULL))
);
CREATE INDEX solvedac_mapping_provider ON app_private.boj_solvedac_links(provider_problem_id,sub_id);
REVOKE ALL ON app_private.solvedac_difficulty,app_private.boj_solvedac_links FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON app_private.solvedac_difficulty,app_private.boj_solvedac_links TO service_role;

CREATE FUNCTION catalog.save_solvedac_difficulty(p_observation jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE native_id bigint:=(p_observation->>'bojId')::bigint;
    checked timestamptz:=(p_observation->>'checkedAt')::timestamptz;
    provider_id bigint:=(p_observation->>'providerId')::bigint;
    selector text:=p_observation->>'subId';
    outcome text:=p_observation->>'outcome';
    fetched timestamptz:=(p_observation->>'fetchedAt')::timestamptz;
    fields jsonb:=p_observation->'measures';
    refs jsonb:=p_observation->'evidence';
    existing_outcome text;
BEGIN
    IF outcome IS NULL OR checked IS NULL OR native_id IS NULL
        OR NOT EXISTS(SELECT 1 FROM app_private.catalog_boj_problems WHERE boj_problem_id=native_id)
    THEN RAISE EXCEPTION 'Difficulty needs an approved BOJ identity' USING ERRCODE='22023'; END IF;
    IF outcome='mapped' THEN
        IF NOT app_private.has_json_fields(fields,ARRAY['level','levelAverage','levelStdev','votedUserCount',
            'effectiveVoteCount','isStandard','givesNoRating','noRatingReasons'])
            OR jsonb_typeof(fields->'level') IS DISTINCT FROM 'number'
            OR jsonb_typeof(refs) IS DISTINCT FROM 'object'
            OR COALESCE(refs->>'ojId','')='' OR refs->>'problemId' IS DISTINCT FROM native_id::text
            OR refs->>'subId' IS DISTINCT FROM ''
            OR fetched IS NULL OR provider_id IS NULL OR selector IS NULL
        THEN RAISE EXCEPTION 'Invalid solved.ac snapshot or exact judge reference' USING ERRCODE='22023'; END IF;
        INSERT INTO app_private.solvedac_difficulty AS current(provider_problem_id,sub_id,level,measures,fetched_at)
            VALUES(provider_id,selector,(fields->>'level')::integer,fields,fetched)
            ON CONFLICT (provider_problem_id,sub_id) DO UPDATE SET
                level=EXCLUDED.level,measures=EXCLUDED.measures,fetched_at=EXCLUDED.fetched_at
            WHERE current.fetched_at<EXCLUDED.fetched_at;
    END IF;
    INSERT INTO app_private.boj_solvedac_links AS current(boj_problem_id,provider_problem_id,sub_id,outcome,checked_at,evidence)
        VALUES(native_id,provider_id,selector,outcome,checked,refs)
        ON CONFLICT (boj_problem_id) DO UPDATE SET provider_problem_id=EXCLUDED.provider_problem_id,sub_id=EXCLUDED.sub_id,
            outcome=EXCLUDED.outcome,checked_at=EXCLUDED.checked_at,evidence=EXCLUDED.evidence
        WHERE current.checked_at<EXCLUDED.checked_at;
    SELECT l.outcome INTO existing_outcome FROM app_private.boj_solvedac_links l WHERE l.boj_problem_id=native_id;
    RETURN jsonb_build_object('bojId',native_id,'outcome',existing_outcome);
END;
$$;

-- Return only rated UUIDs and the metadata needed by the checklist.
CREATE FUNCTION catalog.solvedac_problem_difficulty(p_id uuid) RETURNS jsonb
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
    SELECT CASE WHEN count(*)=0 THEN NULL ELSE jsonb_build_object(
        'primary',(SELECT data FROM ratings WHERE preferred),
        'parts',COALESCE(jsonb_agg(data||jsonb_build_object('order',part_order) ORDER BY part_order)
                         FILTER(WHERE part_order IS NOT NULL),'[]')) END
    FROM ratings;
$$;

CREATE OR REPLACE FUNCTION public.problem_difficulty(p_problem_id uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('count',count(*),'average',round(avg(value),2),
        'vote',max(value) FILTER(WHERE user_id=auth.uid()))
        || COALESCE((SELECT jsonb_build_object('solvedAc',rating) FROM
            (SELECT catalog.solvedac_problem_difficulty(p_problem_id) AS rating) r WHERE rating IS NOT NULL),'{}')
    FROM user_data.difficulty_votes
    WHERE problem_id=p_problem_id AND EXISTS(SELECT 1 FROM catalog.problems WHERE id=p_problem_id AND is_public);
$$;

CREATE FUNCTION catalog.due_boj_difficulty(p_limit integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_agg(boj_problem_id ORDER BY priority,checked_at NULLS FIRST,boj_problem_id),'[]')
    FROM (
        SELECT DISTINCT b.boj_problem_id,l.checked_at,CASE WHEN l.outcome='unmapped' THEN 2 WHEN l.outcome='mapped' THEN 1 ELSE 0 END priority
        FROM app_private.catalog_boj_problems b JOIN catalog.problems p ON p.id=b.catalog_problem_id AND p.is_public
        LEFT JOIN app_private.boj_solvedac_links l ON l.boj_problem_id=b.boj_problem_id
        LEFT JOIN app_private.solvedac_difficulty d ON (d.provider_problem_id,d.sub_id)=(l.provider_problem_id,l.sub_id)
        WHERE l.outcome IS NULL OR (l.outcome='mapped' AND
            (d.fetched_at < now()-interval '24 hours' OR l.checked_at < now()-interval '7 days'))
            OR (l.outcome='unmapped' AND l.checked_at < now()-interval '1 hour')
        ORDER BY priority,l.checked_at NULLS FIRST,b.boj_problem_id
        LIMIT least(greatest(p_limit,1),100)
    ) due;
$$;

REVOKE ALL ON FUNCTION catalog.save_solvedac_difficulty(jsonb),catalog.due_boj_difficulty(integer),
    catalog.solvedac_problem_difficulty(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.save_solvedac_difficulty(jsonb),catalog.due_boj_difficulty(integer) TO service_role;

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
    WHEN 'stage_boj_problem' THEN answer:=catalog.stage_boj_problem(p_body->'p_problem');
    ELSE RAISE EXCEPTION 'Unsupported administrative write' USING ERRCODE='22023';
    END CASE;
    INSERT INTO app_private.remote_receipts(job_id,step,result) VALUES(p_id,p_step,answer);
    RETURN answer;
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
