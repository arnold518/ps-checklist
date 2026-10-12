-- Admin metadata lives in the existing catalog. No additional business tables.
BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS contests_qoj_identity ON catalog.contests((payload->'link'->>'qoj'))
    WHERE payload->'link'->>'qoj' IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS problems_qoj_identity ON catalog.problems((payload->'link'->>'qoj'))
    WHERE payload->'link'->>'qoj' IS NOT NULL;

CREATE OR REPLACE FUNCTION catalog.admin_catalog()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT catalog.read_catalog() || jsonb_build_object(
        'versions', jsonb_build_object(
            'contests', (SELECT COALESCE(jsonb_object_agg(id,updated_at::text),'{}') FROM catalog.contests),
            'problems', (SELECT COALESCE(jsonb_object_agg(id,updated_at::text),'{}') FROM catalog.problems)),
        'usages', (SELECT COALESCE(jsonb_object_agg(p.id,
            (SELECT COALESCE(jsonb_agg(item),'[]') FROM
                (SELECT DISTINCT jsonb_build_object('id',c.id,'title',c.payload->>'title') AS item
                 FROM catalog.contest_problems cp JOIN catalog.contests c ON c.id=cp.contest_id
                 WHERE cp.problem_id=p.id) uses)),'{}') FROM catalog.problems p));
$$;

CREATE OR REPLACE FUNCTION catalog.admin_publish(p_contest jsonb, p_problems jsonb, p_versions jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE entity_id uuid; actual text; expected text; existed boolean; lock_key text; changed_problems jsonb;
BEGIN
    IF jsonb_typeof(p_contest) IS DISTINCT FROM 'object' OR jsonb_typeof(p_problems) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_versions) IS DISTINCT FROM 'object'
        OR p_contest->'category'->>0 NOT IN ('ICPC','Olympiad')
        OR p_contest->'category'->>0 IS NULL THEN
        RAISE EXCEPTION 'Provide a global contest and expected versions' USING ERRCODE='22023';
    END IF;
    -- Use the same source identity locks as personal round ingestion, before
    -- reading versions or writing metadata. Imports then see the curated record.
    FOR lock_key IN
        SELECT DISTINCT url FROM (
            SELECT value AS url FROM jsonb_each_text(p_contest->'link') WHERE key IN ('cf','qoj','atcoder')
            UNION SELECT value FROM catalog.contests c, jsonb_each_text(c.payload->'link')
                WHERE c.id=(p_contest->>'id')::uuid AND key IN ('cf','qoj','atcoder')
        ) links WHERE url IS NOT NULL ORDER BY url
    LOOP PERFORM pg_advisory_xact_lock(hashtextextended(lock_key,0)); END LOOP;
    FOR lock_key IN
        SELECT DISTINCT url FROM (
            SELECT link.value AS url FROM jsonb_array_elements(p_problems) records(item), jsonb_each_text(records.item->'link') link
            UNION SELECT link.value FROM catalog.problems p, jsonb_each_text(p.payload->'link') link
                WHERE p.id IN (SELECT (records.item->>'id')::uuid FROM jsonb_array_elements(p_problems) records(item))
        ) links WHERE url IS NOT NULL ORDER BY url
    LOOP PERFORM pg_advisory_xact_lock(hashtextextended(lock_key,0)); END LOOP;
    -- Lock rows in the same order for all admin writers. Imports and other writers
    -- still use the catalog's uniqueness constraints and transactional locks.
    FOR entity_id IN SELECT (value->>'id')::uuid FROM jsonb_array_elements(p_problems) ORDER BY 1 LOOP
        SELECT updated_at::text INTO actual FROM catalog.problems WHERE id=entity_id FOR UPDATE;
        existed := FOUND;
        expected := p_versions->'problems'->>entity_id::text;
        IF (existed AND (expected IS NULL OR actual IS DISTINCT FROM expected)) OR (NOT existed AND expected IS NOT NULL) THEN
            RAISE EXCEPTION 'Problem changed while editing' USING ERRCODE='40001';
        END IF;
    END LOOP;
    entity_id := (p_contest->>'id')::uuid;
    SELECT updated_at::text INTO actual FROM catalog.contests WHERE id=entity_id FOR UPDATE;
    existed := FOUND;
    expected := p_versions->'contests'->>entity_id::text;
    IF (existed AND (expected IS NULL OR actual IS DISTINCT FROM expected)) OR (NOT existed AND expected IS NOT NULL) THEN
        RAISE EXCEPTION 'Contest changed while editing' USING ERRCODE='40001';
    END IF;
    -- An unchanged shared problem must not invalidate the next row in a batch.
    SELECT COALESCE(jsonb_agg(records.item),'[]') INTO changed_problems
        FROM jsonb_array_elements(p_problems) records(item)
        LEFT JOIN catalog.problems p ON p.id=(records.item->>'id')::uuid
        WHERE p.id IS NULL OR NOT p.is_public OR p.payload IS DISTINCT FROM records.item-'id';
    PERFORM catalog.write_catalog(jsonb_build_array(p_contest),changed_problems,true);
    RETURN catalog.admin_catalog();
END;
$$;

CREATE OR REPLACE FUNCTION catalog.admin_remove(p_id uuid, p_version text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE actual text; lock_key text;
BEGIN
    FOR lock_key IN SELECT value FROM catalog.contests c, jsonb_each_text(c.payload->'link')
        WHERE c.id=p_id AND key IN ('cf','qoj','atcoder') AND value IS NOT NULL ORDER BY value
    LOOP PERFORM pg_advisory_xact_lock(hashtextextended(lock_key,0)); END LOOP;
    SELECT updated_at::text INTO actual FROM catalog.contests WHERE id=p_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown contest' USING ERRCODE='22023'; END IF;
    IF p_version IS NULL OR p_version IS DISTINCT FROM actual THEN
        RAISE EXCEPTION 'Contest changed while editing' USING ERRCODE='40001';
    END IF;
    UPDATE catalog.contests SET payload=jsonb_set(payload,'{category}','null') WHERE id=p_id;
    RETURN catalog.admin_catalog();
END;
$$;

REVOKE ALL ON FUNCTION catalog.admin_catalog(),catalog.admin_publish(jsonb,jsonb,jsonb),catalog.admin_remove(uuid,text)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_catalog(),catalog.admin_publish(jsonb,jsonb,jsonb),catalog.admin_remove(uuid,text)
    TO service_role;
COMMIT;
