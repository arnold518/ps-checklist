-- Allow the selected archive ID on problem-specific material metadata.
BEGIN;
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
            IF NOT app_private.has_json_fields(item-'archiveId',ARRAY['problemId','role','title','language','url'])
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
