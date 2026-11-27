BEGIN;

CREATE FUNCTION catalog.doj_statement_targets() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT COALESCE(jsonb_agg(native_id ORDER BY curated DESC,native_id),'[]')
    FROM (
        SELECT split_part(p.payload->'link'->>'doj','/',6)::bigint AS native_id,
            bool_or(COALESCE(c.payload->'category'->>0 IN ('ICPC','Olympiad'),false)) AS curated
        FROM catalog.problems p
        JOIN catalog.contest_problems m ON m.problem_id=p.id AND m.is_public
        JOIN catalog.contests c ON c.id=m.contest_id AND c.is_public
        WHERE p.is_public AND p.payload->'link'->>'doj' IS NOT NULL
        GROUP BY p.id
    ) targets;
$$;

CREATE FUNCTION catalog.update_doj_material_count(p_contest_id uuid) RETURNS void
LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $$
    UPDATE catalog.contests c SET problem_material_count=counts.total
    FROM (SELECT count(*) AS total FROM catalog.materials m
          WHERE m.contest_id=p_contest_id AND m.problem_id IS NOT NULL AND m.position IS NOT NULL
              AND m.payload IS NOT NULL AND m.is_public
              AND EXISTS (SELECT 1 FROM catalog.contest_problems cp
                  WHERE cp.contest_id=m.contest_id AND cp.problem_id=m.problem_id AND cp.is_public)) counts
    WHERE c.id=p_contest_id AND (counts.total>0 OR c.problem_material_count IS NOT NULL)
        AND c.problem_material_count IS DISTINCT FROM counts.total;
$$;

CREATE FUNCTION catalog.save_doj_statements(p_statements jsonb,p_contest_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE target_id uuid; item record; managed_id uuid; managed_url text; archived boolean;
    ordinal integer; added integer:=0; updated integer:=0;
BEGIN
    IF jsonb_typeof(p_statements) IS DISTINCT FROM 'array' OR jsonb_array_length(p_statements)>500 THEN
        RAISE EXCEPTION 'Provide up to 500 DOJ statement links' USING ERRCODE='22023';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_statements) s
        WHERE NOT app_private.has_json_fields(s,ARRAY['dojId','url','language'])
            OR COALESCE(s->>'dojId','') !~ '^[1-9][0-9]{0,14}$'
            OR COALESCE(s->>'language','') NOT IN ('en','ko','ja','zh-CN')
            OR COALESCE(s->>'url','') !~ '^https://doj\.kr/api/problem-statements/[A-Za-z0-9_-]{1,100}\?locale=(en|ko|ja|zh-CN)$'
            OR split_part(s->>'url','=',2) IS DISTINCT FROM s->>'language')
        OR (SELECT count(DISTINCT s->>'dojId') FROM jsonb_array_elements(p_statements) s)<>jsonb_array_length(p_statements) THEN
        RAISE EXCEPTION 'Invalid or repeated DOJ statement identity' USING ERRCODE='22023';
    END IF;

    -- Take problem locks before contest locks, like catalog publication.
    PERFORM 1 FROM catalog.problems p JOIN jsonb_to_recordset(p_statements) s("dojId" bigint)
        ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
        WHERE p.is_public ORDER BY p.id FOR KEY SHARE OF p;
    FOR target_id IN
        SELECT c.id FROM catalog.contests c
        WHERE c.is_public AND (p_contest_id IS NULL OR c.id=p_contest_id) AND EXISTS (
            SELECT 1 FROM catalog.contest_problems cp
            JOIN catalog.problems p ON p.id=cp.problem_id AND p.is_public
            JOIN jsonb_to_recordset(p_statements) s("dojId" bigint)
                ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
            WHERE cp.contest_id=c.id AND cp.is_public
        ) ORDER BY c.id FOR UPDATE OF c
    LOOP
        SELECT greatest(999999,MAX(position)) INTO ordinal FROM catalog.materials WHERE contest_id=target_id;
        FOR item IN
            SELECT p.id AS problem_id,s.url,s.language
            FROM catalog.problems p JOIN jsonb_to_recordset(p_statements) s("dojId" bigint,url text,language text)
                ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
            WHERE p.is_public AND EXISTS (
                SELECT 1 FROM catalog.contest_problems cp WHERE cp.contest_id=target_id
                    AND cp.problem_id=p.id AND cp.is_public
            ) ORDER BY p.id
        LOOP
            IF EXISTS (SELECT 1 FROM catalog.materials m WHERE m.contest_id=target_id
                AND m.problem_id=item.problem_id AND m.is_public AND m.payload->>'url'=item.url
                AND m.payload->>'role'='statement') THEN CONTINUE; END IF;
            SELECT m.id,m.payload->>'url',m.payload ? 'archiveId' INTO managed_id,managed_url,archived
                FROM catalog.materials m WHERE m.contest_id=target_id AND m.problem_id=item.problem_id
                    AND m.is_public AND m.payload->>'title'='DOJ statement'
                    AND m.payload->>'role'='statement'
                    AND m.payload->>'url' LIKE 'https://doj.kr/api/problem-statements/%'
                ORDER BY m.position LIMIT 1;
            IF managed_id IS NULL THEN
                ordinal:=ordinal+1;
                INSERT INTO catalog.materials(contest_id,problem_id,position,payload,is_public)
                    VALUES(target_id,item.problem_id,ordinal,jsonb_build_object('role','statement','title','DOJ statement',
                        'language',item.language,'url',item.url),true);
                added:=added+1;
            ELSIF NOT archived AND managed_url IS DISTINCT FROM item.url THEN
                UPDATE catalog.materials SET payload=payload||jsonb_build_object('language',item.language,'url',item.url)
                WHERE id=managed_id;
                updated:=updated+1;
            END IF;
        END LOOP;
        PERFORM catalog.update_doj_material_count(target_id);
    END LOOP;
    RETURN jsonb_build_object('added',added,'updated',updated);
END;
$$;

REVOKE ALL ON FUNCTION catalog.doj_statement_targets(),catalog.save_doj_statements(jsonb,uuid),
    catalog.update_doj_material_count(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.doj_statement_targets(),catalog.save_doj_statements(jsonb,uuid),
    catalog.update_doj_material_count(uuid) TO service_role;

CREATE OR REPLACE FUNCTION catalog.write_doj(p_contest jsonb, p_problems jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE native jsonb; details jsonb; tasks jsonb; task_url text; contest_url text;
    contest_id uuid; problem_id uuid; was_public boolean; ids jsonb:='{}';
    previous jsonb; basic jsonb; memberships jsonb; statements jsonb;
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

    previous:=catalog.contest_json(contest_id)-'problemMaterials';
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
            PERFORM catalog.update_doj_material_count(contest_id);
        END IF;
    END IF;
    UPDATE catalog.contests SET doj_metadata=details WHERE id=contest_id AND doj_metadata IS DISTINCT FROM details;
    IF jsonb_typeof(p_contest->'materials')='array' THEN
        SELECT jsonb_agg(DISTINCT jsonb_build_object(
            'dojId',task->'taskId','url',entry->>'url','language',entry->>'language')) INTO statements
        FROM jsonb_array_elements(p_contest->'materials') entry
        JOIN jsonb_array_elements(tasks) task ON task->>'key'=entry->>'problemKey'
        WHERE entry->>'role'='statement' AND entry->>'scope'='problem' AND entry->>'type'='pdf';
        IF statements IS NOT NULL THEN PERFORM catalog.save_doj_statements(statements,contest_id); END IF;
    END IF;
    RETURN contest_id;
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
