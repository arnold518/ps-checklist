-- Contest-specific documents attached to a particular shared problem.
BEGIN;
ALTER TABLE catalog.contests ADD COLUMN problem_material_count integer CHECK (problem_material_count >= 0);

CREATE OR REPLACE FUNCTION catalog.contest_json(contest_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE entity catalog.contests%ROWTYPE; problem_list jsonb; material_list jsonb; problem_materials jsonb;
BEGIN
    SELECT * INTO entity FROM catalog.contests c WHERE c.id=contest_id;
    IF NOT FOUND OR entity.payload IS NULL THEN RETURN NULL; END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('problemId',cp.problem_id,'index',cp.problem_index)
        || CASE WHEN cp.group_id IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('groupId',cp.group_id) END
        ORDER BY cp.position),'[]'::jsonb) INTO problem_list
        FROM catalog.contest_problems cp JOIN catalog.problems p ON p.id=cp.problem_id
        WHERE cp.contest_id=entity.id AND cp.position IS NOT NULL AND p.payload IS NOT NULL;
    SELECT COALESCE(jsonb_agg(m.payload ORDER BY m.position),'[]'::jsonb) INTO material_list
        FROM catalog.materials m WHERE m.contest_id=entity.id AND m.problem_id IS NULL
        AND m.position IS NOT NULL AND m.payload IS NOT NULL;
    SELECT COALESCE(jsonb_agg(jsonb_build_object('problemId',m.problem_id)||m.payload ORDER BY m.position),'[]'::jsonb)
        INTO problem_materials FROM catalog.materials m JOIN catalog.problems p ON p.id=m.problem_id
        WHERE m.contest_id=entity.id AND m.problem_id IS NOT NULL AND m.position IS NOT NULL
        AND m.payload IS NOT NULL AND p.payload IS NOT NULL
        AND EXISTS (SELECT 1 FROM catalog.contest_problems cp WHERE cp.contest_id=entity.id AND cp.problem_id=m.problem_id);
    IF (entity.problem_count IS NOT NULL AND jsonb_array_length(problem_list)<>entity.problem_count)
        OR (entity.material_count IS NOT NULL AND jsonb_array_length(material_list)<>entity.material_count)
        OR (entity.problem_material_count IS NOT NULL AND jsonb_array_length(problem_materials)<>entity.problem_material_count)
        THEN RETURN NULL;
    END IF;
    RETURN jsonb_build_object('id',entity.id)||entity.payload||jsonb_build_object(
        'problems',CASE WHEN entity.problem_count IS NULL THEN 'null'::jsonb ELSE problem_list END,
        'materials',CASE WHEN entity.material_count IS NULL THEN 'null'::jsonb ELSE material_list END)
        || CASE WHEN entity.problem_material_count IS NULL THEN '{}'::jsonb
                ELSE jsonb_build_object('problemMaterials',problem_materials) END;
END;
$$;

CREATE OR REPLACE FUNCTION catalog.admin_publish_with_refresh(p_contest jsonb,p_problems jsonb,p_versions jsonb,p_refresh jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE item jsonb; entity_id uuid; rules jsonb; actual text; scoped jsonb; metadata jsonb;
    material_id uuid; kept uuid[]:=ARRAY[]::uuid[]; ordinal integer; seen text[]:=ARRAY[]::text[]; identity text;
BEGIN
    IF p_refresh IS NOT NULL AND p_refresh <> 'null'::jsonb
        AND (jsonb_typeof(p_refresh->'contest') IS DISTINCT FROM 'object'
            OR jsonb_typeof(p_refresh->'problems') IS DISTINCT FROM 'object') THEN
        RAISE EXCEPTION 'Invalid refresh settings' USING ERRCODE='22023';
    END IF;
    scoped:=p_contest->'problemMaterials';
    IF scoped IS NOT NULL THEN
        IF jsonb_typeof(scoped) IS DISTINCT FROM 'array' OR jsonb_array_length(scoped)>200 THEN
            RAISE EXCEPTION 'Invalid problem material list' USING ERRCODE='22023';
        END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(scoped) LOOP
            IF NOT app_private.has_json_fields(item,ARRAY['problemId','role','title','language','url'])
                OR NOT app_private.valid_material_metadata(item-'problemId')
                OR jsonb_typeof(item->'problemId') IS DISTINCT FROM 'string'
                OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(
                    COALESCE(NULLIF(p_contest->'problems','null'::jsonb),'[]'::jsonb)) member
                    WHERE member->>'problemId'=item->>'problemId') THEN
                RAISE EXCEPTION 'Problem material must reference a contest member' USING ERRCODE='22023';
            END IF;
            identity:=(item->>'problemId')||'|'||(item->>'role')||'|'||(item->>'url');
            IF identity=ANY(seen) THEN
                RAISE EXCEPTION 'Duplicate problem material' USING ERRCODE='22023';
            END IF;
            seen:=array_append(seen,identity);
        END LOOP;
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(p_problems) LOOP
        entity_id:=(item->>'id')::uuid;
        rules:=p_refresh->'problems'->entity_id::text;
        SELECT p.updated_at::text INTO actual FROM catalog.problems p WHERE p.id=entity_id
            AND p.payload=item-'id' AND (rules IS NULL OR p.refresh_policy-'fields'=rules-'fields');
        IF FOUND THEN p_versions:=jsonb_set(p_versions,ARRAY['problems',entity_id::text],to_jsonb(actual)); END IF;
    END LOOP;
    PERFORM catalog.admin_publish(p_contest-'problemMaterials',p_problems,p_versions);
    entity_id:=(p_contest->>'id')::uuid;
    IF scoped IS NOT NULL THEN
        SET CONSTRAINTS catalog.contest_material_position_unique DEFERRED;
        -- Keep scoped positions clear of the existing contest-wide writer's 0-based positions.
        ordinal:=1000000;
        FOR item IN SELECT value FROM jsonb_array_elements(scoped) LOOP
            metadata:=item-'problemId';
            SELECT m.id INTO material_id FROM catalog.materials m
                WHERE m.contest_id=entity_id AND m.problem_id=(item->>'problemId')::uuid
                    AND m.payload->>'url'=item->>'url' AND m.id<>ALL(kept)
                ORDER BY (m.payload=metadata) DESC,m.position NULLS LAST,m.id LIMIT 1 FOR UPDATE;
            IF FOUND THEN
                UPDATE catalog.materials SET position=ordinal,payload=metadata,is_public=true WHERE id=material_id;
            ELSE
                INSERT INTO catalog.materials(contest_id,problem_id,position,payload,is_public)
                    VALUES(entity_id,(item->>'problemId')::uuid,ordinal,metadata,true) RETURNING id INTO material_id;
            END IF;
            kept:=array_append(kept,material_id);
            ordinal:=ordinal+1;
        END LOOP;
        DELETE FROM catalog.materials WHERE contest_id=entity_id AND problem_id IS NOT NULL AND id<>ALL(kept);
        UPDATE catalog.contests SET problem_material_count=jsonb_array_length(scoped) WHERE id=entity_id;
        SET CONSTRAINTS catalog.contest_material_position_unique IMMEDIATE;
    END IF;
    IF p_refresh IS NOT NULL AND p_refresh <> 'null'::jsonb THEN
        rules:=p_refresh->'contest';
        UPDATE catalog.contests SET refresh_policy=rules WHERE id=entity_id AND refresh_policy IS DISTINCT FROM rules;
        FOR item IN SELECT value FROM jsonb_array_elements(p_problems) LOOP
            entity_id:=(item->>'id')::uuid;
            rules:=p_refresh->'problems'->entity_id::text;
            IF rules IS NOT NULL THEN
                UPDATE catalog.problems SET refresh_policy=rules WHERE id=entity_id AND refresh_policy IS DISTINCT FROM rules;
            END IF;
        END LOOP;
    END IF;
    RETURN catalog.admin_catalog();
END;
$$;
COMMIT;
