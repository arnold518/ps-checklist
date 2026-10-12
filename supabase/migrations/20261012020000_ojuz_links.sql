-- Optional fourth judge links. Existing catalog JSON and UUIDs remain intact.
BEGIN;
CREATE OR REPLACE FUNCTION app_private.valid_json_links(value jsonb, fields text[])
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
DECLARE item jsonb; allowed text[]:=fields;
BEGIN
    IF fields @> ARRAY['cf','qoj','atcoder'] AND value ? 'ojuz' THEN
        allowed:=array_append(fields,'ojuz');
    END IF;
    IF NOT app_private.has_json_fields(value,allowed) THEN RETURN false; END IF;
    FOR item IN SELECT entry.value FROM jsonb_each(value) entry LOOP
        IF item <> 'null'::jsonb AND NOT app_private.https_json_url(item) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END;
$$;
CREATE UNIQUE INDEX contests_ojuz_identity ON catalog.contests((payload->'link'->>'ojuz'))
    WHERE payload->'link'->>'ojuz' IS NOT NULL;
CREATE UNIQUE INDEX problems_ojuz_identity ON catalog.problems((payload->'link'->>'ojuz'))
    WHERE payload->'link'->>'ojuz' IS NOT NULL;
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
            SELECT value AS url FROM jsonb_each_text(p_contest->'link') WHERE key IN ('cf','qoj','atcoder','ojuz')
            UNION SELECT value FROM catalog.contests c, jsonb_each_text(c.payload->'link')
                WHERE c.id=(p_contest->>'id')::uuid AND key IN ('cf','qoj','atcoder','ojuz')
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
COMMIT;
