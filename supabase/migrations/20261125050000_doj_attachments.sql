BEGIN;

CREATE FUNCTION catalog.save_doj_problem_files(p_files jsonb,p_contest_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE target_id uuid; item record; selected_id uuid; selected_url text; archived boolean;
    rules jsonb; provenance jsonb; field text;
    ordinal integer; added integer:=0; updated integer:=0;
BEGIN
    IF jsonb_typeof(p_files) IS DISTINCT FROM 'array' OR jsonb_array_length(p_files)>500 THEN
        RAISE EXCEPTION 'Provide up to 500 selected DOJ problem files' USING ERRCODE='22023';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_files) s
        WHERE NOT app_private.has_json_fields(s,ARRAY['dojId','url','language','role'])
            OR COALESCE(s->>'dojId','') !~ '^[1-9][0-9]{0,14}$'
            OR COALESCE(s->>'role','') NOT IN ('statement','editorial')
            OR COALESCE(s->>'language','en') NOT IN ('en','ko','ja','zh-CN')
            OR NOT (
                COALESCE(s->>'url','') ~ '^https://doj\.kr/api/problem-attachments/[A-Za-z0-9_-]{1,100}$'
                OR (s->>'role'='statement'
                    AND COALESCE(s->>'url','') ~ '^https://doj\.kr/api/problem-statements/[A-Za-z0-9_-]{1,100}\?locale=(en|ko|ja|zh-CN)$'
                    AND split_part(s->>'url','=',2) IS NOT DISTINCT FROM s->>'language'))
        )
        OR (SELECT count(DISTINCT (s->>'dojId',s->>'role')) FROM jsonb_array_elements(p_files) s)<>jsonb_array_length(p_files) THEN
        RAISE EXCEPTION 'Invalid or repeated DOJ problem file' USING ERRCODE='22023';
    END IF;

    -- Take problem locks before contest locks, like catalog publication.
    PERFORM 1 FROM catalog.problems p JOIN jsonb_to_recordset(p_files) s("dojId" bigint)
        ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
        WHERE p.is_public ORDER BY p.id FOR KEY SHARE OF p;
    FOR target_id IN
        SELECT c.id FROM catalog.contests c
        WHERE c.is_public AND (p_contest_id IS NULL OR c.id=p_contest_id) AND EXISTS (
            SELECT 1 FROM catalog.contest_problems cp
            JOIN catalog.problems p ON p.id=cp.problem_id AND p.is_public
            JOIN jsonb_to_recordset(p_files) s("dojId" bigint)
                ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
            WHERE cp.contest_id=c.id AND cp.is_public
        ) ORDER BY c.id FOR UPDATE OF c
    LOOP
        SELECT c.refresh_policy INTO rules FROM catalog.contests c WHERE c.id=target_id;
        provenance:=COALESCE(rules->'problemMaterialSources','{}');
        SELECT greatest(999999,MAX(position)) INTO ordinal FROM catalog.materials WHERE contest_id=target_id;
        FOR item IN
            SELECT p.id AS problem_id,s.url,s.language,s.role
            FROM catalog.problems p JOIN jsonb_to_recordset(p_files) s("dojId" bigint,url text,language text,role text)
                ON p.payload->'link'->>'doj'='https://doj.kr/en/problems/'||s."dojId"::text
            WHERE p.is_public AND EXISTS (
                SELECT 1 FROM catalog.contest_problems cp WHERE cp.contest_id=target_id
                    AND cp.problem_id=p.id AND cp.is_public
            ) ORDER BY p.id
        LOOP
            field:='problemMaterials.'||item.problem_id::text||'.'||item.role;
            IF (rules->'manual') ? field THEN CONTINUE; END IF;
            SELECT m.id,m.payload->>'url',m.payload ? 'archiveId' INTO selected_id,selected_url,archived
                FROM catalog.materials m WHERE m.contest_id=target_id AND m.problem_id=item.problem_id
                    AND m.is_public AND m.position IS NOT NULL AND m.payload->>'role'=item.role
                ORDER BY m.position LIMIT 1;
            IF selected_id IS NULL THEN
                ordinal:=ordinal+1;
                INSERT INTO catalog.materials(contest_id,problem_id,position,payload,is_public)
                    VALUES(target_id,item.problem_id,ordinal,jsonb_build_object('role',item.role,
                        'title',CASE WHEN item.role='statement' THEN 'Problem statement' ELSE 'Editorial' END,
                        'language',item.language,'url',item.url),true);
                added:=added+1;
            ELSIF NOT archived AND (provenance->field->>'source')='doj'
                AND (provenance->field->>'url')=selected_url AND selected_url<>item.url THEN
                UPDATE catalog.materials SET payload=payload||jsonb_build_object('language',item.language,'url',item.url)
                WHERE id=selected_id;
                updated:=updated+1;
            ELSE
                CONTINUE;
            END IF;
            provenance:=jsonb_set(provenance,ARRAY[field],jsonb_build_object('source','doj','url',item.url));
        END LOOP;
        IF provenance IS DISTINCT FROM COALESCE(rules->'problemMaterialSources','{}') THEN
            UPDATE catalog.contests SET refresh_policy=jsonb_set(rules,'{problemMaterialSources}',provenance)
            WHERE id=target_id;
        END IF;
        PERFORM catalog.update_doj_material_count(target_id);
    END LOOP;
    RETURN jsonb_build_object('added',added,'updated',updated);
END;
$$;

CREATE OR REPLACE FUNCTION catalog.save_doj_statements(p_statements jsonb,p_contest_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE statements jsonb;
BEGIN
    IF jsonb_typeof(p_statements) IS DISTINCT FROM 'array' OR jsonb_array_length(p_statements)>500
        OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_statements) entry
            WHERE NOT app_private.has_json_fields(entry,ARRAY['dojId','url','language'])) THEN
        RAISE EXCEPTION 'Provide up to 500 DOJ statement links' USING ERRCODE='22023';
    END IF;
    SELECT COALESCE(jsonb_agg(entry||jsonb_build_object('role','statement')),'[]')
        INTO statements FROM jsonb_array_elements(p_statements) entry;
    RETURN catalog.save_doj_problem_files(statements,p_contest_id);
END;
$$;

CREATE FUNCTION catalog.save_doj_contest_files(p_url text,p_files jsonb)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE target uuid; entry jsonb; ordinal integer; added integer:=0;
BEGIN
    IF jsonb_typeof(p_files) IS DISTINCT FROM 'array' OR jsonb_array_length(p_files)>200
        OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_files) item
            WHERE NOT app_private.valid_material_metadata(item)
                OR COALESCE(item->>'url','') !~ '^https://doj\.kr/api/(contest|category)-attachments/[A-Za-z0-9_-]{1,100}$') THEN
        RAISE EXCEPTION 'Invalid DOJ contest attachments' USING ERRCODE='22023';
    END IF;
    SELECT id INTO target FROM catalog.contests c WHERE c.is_public AND c.payload->'link'->>'doj'=p_url FOR UPDATE;
    IF NOT FOUND THEN RETURN 0; END IF;
    SELECT COALESCE(MAX(position),-1) INTO ordinal FROM catalog.materials WHERE contest_id=target;
    FOR entry IN SELECT value FROM jsonb_array_elements(p_files) LOOP
        IF EXISTS(SELECT 1 FROM catalog.materials WHERE contest_id=target AND problem_id IS NULL AND is_public
            AND position IS NOT NULL AND payload->>'url'=entry->>'url') THEN CONTINUE; END IF;
        ordinal:=ordinal+1;
        INSERT INTO catalog.materials(contest_id,position,payload,is_public) VALUES(target,ordinal,entry,true);
        added:=added+1;
    END LOOP;
    IF added>0 THEN
        UPDATE catalog.contests SET material_count=(SELECT count(*) FROM catalog.materials
            WHERE contest_id=target AND problem_id IS NULL AND position IS NOT NULL AND is_public) WHERE id=target;
    END IF;
    RETURN added;
END;
$$;

ALTER FUNCTION catalog.write_doj(jsonb,jsonb) RENAME TO write_doj_records;
CREATE FUNCTION catalog.write_doj(p_contest jsonb,p_problems jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE target uuid; files jsonb;
BEGIN
    target:=catalog.write_doj_records(p_contest-'materials',p_problems);
    IF target IS NULL OR jsonb_typeof(p_contest->'materials') IS DISTINCT FROM 'array' THEN RETURN target; END IF;
    SELECT jsonb_agg(jsonb_build_object('dojId',native_id,'role',role,'language',language,'url',url))
        INTO files FROM (
        SELECT DISTINCT ON (task->'taskId',m->>'role') task->'taskId' AS native_id,m->>'role' AS role,
            m->'language' AS language,m->>'url' AS url
        FROM jsonb_array_elements(p_contest->'materials') WITH ORDINALITY entries(m,slot)
        JOIN jsonb_array_elements(p_contest->'problems') task ON task->>'key'=m->>'problemKey'
        WHERE m->>'scope'='problem' AND (m->>'role'='editorial' OR (m->>'role'='statement' AND m->>'type'='pdf'))
        ORDER BY task->'taskId',m->>'role',slot
    ) chosen;
    IF files IS NOT NULL THEN PERFORM catalog.save_doj_problem_files(files,target); END IF;

    SELECT jsonb_agg(jsonb_build_object('role',m->>'role','title',m->>'title',
        'language',m->'language','url',m->>'url') ORDER BY slot) INTO files
    FROM jsonb_array_elements(p_contest->'materials') WITH ORDINALITY entries(m,slot)
    WHERE m->>'scope'='contest';
    IF files IS NOT NULL THEN PERFORM catalog.save_doj_contest_files(p_contest->>'url',files); END IF;
    RETURN target;
END;
$$;

REVOKE ALL ON FUNCTION catalog.save_doj_problem_files(jsonb,uuid),catalog.save_doj_contest_files(text,jsonb),
    catalog.write_doj(jsonb,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.save_doj_problem_files(jsonb,uuid),catalog.save_doj_contest_files(text,jsonb),
    catalog.write_doj(jsonb,jsonb) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
