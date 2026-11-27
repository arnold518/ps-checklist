BEGIN;

CREATE OR REPLACE FUNCTION catalog.save_doj_statements(p_statements jsonb,p_contest_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE target_id uuid; item record; selected_id uuid; selected_url text; archived boolean;
    rules jsonb; provenance jsonb; field text;
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
        SELECT c.refresh_policy INTO rules FROM catalog.contests c WHERE c.id=target_id;
        provenance:=COALESCE(rules->'problemMaterialSources','{}');
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
            field:='problemMaterials.'||item.problem_id::text||'.statement';
            IF (rules->'manual') ? field THEN CONTINUE; END IF;
            SELECT m.id,m.payload->>'url',m.payload ? 'archiveId' INTO selected_id,selected_url,archived
                FROM catalog.materials m WHERE m.contest_id=target_id AND m.problem_id=item.problem_id
                    AND m.is_public AND m.position IS NOT NULL AND m.payload->>'role'='statement'
                ORDER BY m.position LIMIT 1;
            IF selected_id IS NULL THEN
                ordinal:=ordinal+1;
                INSERT INTO catalog.materials(contest_id,problem_id,position,payload,is_public)
                    VALUES(target_id,item.problem_id,ordinal,jsonb_build_object('role','statement','title','Problem statement',
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

-- The first DOJ backfill added an extra statement. Retain only the selected link.
DO $$
DECLARE target record; item record; provenance jsonb; field text;
BEGIN
    FOR target IN SELECT c.id,c.refresh_policy FROM catalog.contests c
        WHERE EXISTS (SELECT 1 FROM catalog.materials m WHERE m.contest_id=c.id AND m.is_public AND m.position IS NOT NULL
            AND m.payload->>'role'='statement' AND m.payload->>'title'='DOJ statement'
            AND m.payload->>'url' LIKE 'https://doj.kr/api/problem-statements/%'
            AND NOT (m.payload ? 'archiveId'))
        ORDER BY c.id FOR UPDATE OF c
    LOOP
        provenance:=COALESCE(target.refresh_policy->'problemMaterialSources','{}');
        FOR item IN SELECT m.id,m.problem_id,m.payload->>'url' AS url FROM catalog.materials m
            WHERE m.contest_id=target.id AND m.is_public AND m.position IS NOT NULL AND m.problem_id IS NOT NULL
                AND m.payload->>'role'='statement' AND m.payload->>'title'='DOJ statement'
                AND m.payload->>'url' LIKE 'https://doj.kr/api/problem-statements/%'
                AND NOT (m.payload ? 'archiveId')
            ORDER BY m.position,m.id
        LOOP
            field:='problemMaterials.'||item.problem_id::text||'.statement';
            IF EXISTS (SELECT 1 FROM catalog.materials m WHERE m.contest_id=target.id
                    AND m.problem_id=item.problem_id AND m.id<>item.id AND m.is_public AND m.position IS NOT NULL
                    AND m.payload->>'role'='statement') THEN
                UPDATE catalog.materials SET is_public=false,position=NULL WHERE id=item.id;
                IF provenance->field->>'source'='doj' AND provenance->field->>'url'=item.url THEN
                    provenance:=provenance-field;
                END IF;
            ELSE
                UPDATE catalog.materials SET payload=jsonb_set(payload,'{title}','"Problem statement"') WHERE id=item.id;
                IF NOT COALESCE((target.refresh_policy->'manual') ? field,false) AND NOT (provenance ? field) THEN
                    provenance:=jsonb_set(provenance,ARRAY[field],jsonb_build_object('source','doj','url',item.url));
                END IF;
            END IF;
        END LOOP;
        IF provenance IS DISTINCT FROM COALESCE(target.refresh_policy->'problemMaterialSources','{}') THEN
            UPDATE catalog.contests SET refresh_policy=jsonb_set(refresh_policy,'{problemMaterialSources}',provenance)
            WHERE id=target.id;
        END IF;
        PERFORM catalog.update_doj_material_count(target.id);
    END LOOP;
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
