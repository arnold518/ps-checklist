BEGIN;

-- An edition can list a day even when every task in that section is unavailable.
-- Keep the observed page separate from native contest IDs and problem bindings.
CREATE TABLE app_private.boj_edition_pages (
    contest_id uuid PRIMARY KEY REFERENCES catalog.contests ON DELETE CASCADE,
    category_id bigint NOT NULL CHECK (category_id BETWEEN 1 AND 999999999999999),
    section text NOT NULL CHECK (length(btrim(section)) BETWEEN 1 AND 200),
    observed_at timestamptz NOT NULL
);
REVOKE ALL ON app_private.boj_edition_pages FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON app_private.boj_edition_pages TO service_role;

CREATE FUNCTION catalog.admin_publish_boj_edition_page(p_contest_id uuid, p_version text,
    p_category_id bigint, p_section text, p_observed_at timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE selected catalog.contests;
BEGIN
    SELECT * INTO selected FROM catalog.contests WHERE id=p_contest_id AND is_public FOR UPDATE;
    IF NOT FOUND OR selected.updated_at::text IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION 'Contest changed while reviewing' USING ERRCODE='40001';
    END IF;
    IF selected.payload->>'contestLabel' IS DISTINCT FROM p_section THEN
        RAISE EXCEPTION 'Edition section must identify the catalog contest' USING ERRCODE='22023';
    END IF;
    IF EXISTS (SELECT 1 FROM app_private.catalog_boj_contests WHERE contest_id=p_contest_id AND group_id IS NULL) THEN
        RAISE EXCEPTION 'Contest already has a native BOJ source' USING ERRCODE='23505';
    END IF;
    INSERT INTO app_private.boj_edition_pages(contest_id,category_id,section,observed_at)
        VALUES(p_contest_id,p_category_id,p_section,p_observed_at)
        ON CONFLICT(contest_id) DO NOTHING;
    IF NOT EXISTS (SELECT 1 FROM app_private.boj_edition_pages WHERE contest_id=p_contest_id
        AND category_id=p_category_id AND section=p_section) THEN
        RAISE EXCEPTION 'Contest already has another BOJ edition page' USING ERRCODE='23505';
    END IF;
    UPDATE catalog.contests SET updated_at=clock_timestamp() WHERE id=p_contest_id;
END;
$$;
REVOKE ALL ON FUNCTION catalog.admin_publish_boj_edition_page(uuid,text,bigint,text,timestamptz)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION catalog.admin_publish_boj_edition_page(uuid,text,bigint,text,timestamptz) TO service_role;

CREATE OR REPLACE FUNCTION catalog.boj_contest_links(p_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT COALESCE((
        SELECT jsonb_build_object('','https://acmicpc.net/category/'||ep.category_id)
        FROM app_private.boj_edition_pages ep JOIN catalog.contests c ON c.id=ep.contest_id
        WHERE ep.contest_id=p_id AND c.is_public AND ep.section=c.payload->>'contestLabel'), '{}')
    || COALESCE((
        SELECT jsonb_object_agg(coalesce(b.group_id,''),'https://acmicpc.net/category/detail/'||b.source_id)
        FROM app_private.catalog_boj_contests b JOIN catalog.contests c ON c.id=b.contest_id
        WHERE b.contest_id=p_id AND c.is_public), '{}');
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
