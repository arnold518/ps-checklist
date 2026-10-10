-- Storage structure only. Business fields and payload formats are undecided.
-- Apply to Supabase, which already provides auth.users, auth.uid(), and API roles.
BEGIN;

CREATE SCHEMA user_data;
CREATE SCHEMA catalog;
CREATE SCHEMA archive;
CREATE SCHEMA app_private;

COMMENT ON SCHEMA user_data IS 'Records owned by individual Supabase Auth users.';
COMMENT ON SCHEMA catalog IS 'Shared entity identities and relationships; publication is server controlled.';
COMMENT ON SCHEMA archive IS 'References to external R2 objects and historical snapshots, not file bytes.';
COMMENT ON SCHEMA app_private IS 'Internal database helpers; do not expose through the Data API.';

REVOKE ALL ON SCHEMA user_data, catalog, archive, app_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA user_data TO authenticated, service_role;
GRANT USAGE ON SCHEMA catalog, archive TO anon, authenticated, service_role;

CREATE FUNCTION app_private.record_timestamps()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.created_at := clock_timestamp();
    ELSE
        NEW.created_at := OLD.created_at;
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION app_private.record_timestamps() FROM PUBLIC, anon, authenticated;

-- These internal UUIDs do not replace the native keys returned by fetch APIs.
-- Source identifiers, display fields, and domain constraints will be added later.
CREATE TABLE catalog.contests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog.problems (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog.categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog.contest_problems (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contest_id uuid NOT NULL REFERENCES catalog.contests(id),
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, problem_id)
);
CREATE INDEX contest_problems_contest_idx ON catalog.contest_problems(contest_id);
CREATE INDEX contest_problems_problem_idx ON catalog.contest_problems(problem_id);

CREATE TABLE catalog.category_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id uuid NOT NULL REFERENCES catalog.categories(id),
    child_category_id uuid REFERENCES catalog.categories(id),
    contest_id uuid REFERENCES catalog.contests(id),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT category_entry_one_child CHECK (
        (child_category_id IS NOT NULL AND contest_id IS NULL)
        OR (child_category_id IS NULL AND contest_id IS NOT NULL)
    )
);
CREATE INDEX category_entries_parent_idx ON catalog.category_entries(category_id);
CREATE INDEX category_entries_child_idx ON catalog.category_entries(child_category_id);
CREATE INDEX category_entries_contest_idx ON catalog.category_entries(contest_id);

CREATE TABLE catalog.statement_variants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    contest_problem_id uuid,
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT variant_membership_problem FOREIGN KEY (contest_problem_id, problem_id)
        REFERENCES catalog.contest_problems(id, problem_id)
);
CREATE INDEX statement_variants_problem_idx ON catalog.statement_variants(problem_id);
CREATE INDEX statement_variants_membership_idx ON catalog.statement_variants(contest_problem_id);

CREATE TABLE catalog.materials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contest_id uuid REFERENCES catalog.contests(id),
    problem_id uuid REFERENCES catalog.problems(id),
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX materials_contest_idx ON catalog.materials(contest_id);
CREATE INDEX materials_problem_idx ON catalog.materials(problem_id);

-- Users store references to catalog entities instead of whole contest copies.
CREATE TABLE user_data.profiles (
    user_id uuid PRIMARY KEY DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_data.preferences (
    user_id uuid PRIMARY KEY DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_data.problem_progress (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    problem_id uuid NOT NULL REFERENCES catalog.problems(id),
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, problem_id)
);

CREATE TABLE user_data.saved_contests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    contest_id uuid NOT NULL REFERENCES catalog.contests(id),
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, contest_id)
);

CREATE TABLE user_data.practice_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    contest_id uuid REFERENCES catalog.contests(id),
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, user_id)
);
CREATE INDEX practice_sessions_owner_idx ON user_data.practice_sessions(user_id);
CREATE INDEX practice_sessions_contest_idx ON user_data.practice_sessions(contest_id);

CREATE TABLE user_data.practice_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id uuid NOT NULL,
    problem_id uuid REFERENCES catalog.problems(id),
    contest_problem_id uuid REFERENCES catalog.contest_problems(id),
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT attempt_session_owner FOREIGN KEY (session_id, user_id)
        REFERENCES user_data.practice_sessions(id, user_id) ON DELETE CASCADE,
    CONSTRAINT attempt_membership_has_problem CHECK (contest_problem_id IS NULL OR problem_id IS NOT NULL),
    CONSTRAINT attempt_membership_problem FOREIGN KEY (contest_problem_id, problem_id)
        REFERENCES catalog.contest_problems(id, problem_id)
);
CREATE INDEX practice_attempts_owner_session_idx ON user_data.practice_attempts(user_id, session_id);
CREATE INDEX practice_attempts_problem_idx ON user_data.practice_attempts(problem_id);
CREATE INDEX practice_attempts_membership_idx ON user_data.practice_attempts(contest_problem_id);

-- R2 bucket names, object keys, checksums, formats, versions, and retention
-- fields are deliberately postponed. No bucket or file is created by this SQL.
CREATE TABLE archive.objects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    is_public boolean NOT NULL DEFAULT false,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT public_object_has_no_private_owner CHECK (NOT is_public OR owner_id IS NULL)
);
CREATE INDEX archive_objects_owner_idx ON archive.objects(owner_id);

CREATE TABLE archive.snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    contest_id uuid REFERENCES catalog.contests(id),
    problem_id uuid REFERENCES catalog.problems(id),
    category_id uuid REFERENCES catalog.categories(id),
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX archive_snapshots_owner_idx ON archive.snapshots(owner_id);
CREATE INDEX archive_snapshots_contest_idx ON archive.snapshots(contest_id);
CREATE INDEX archive_snapshots_problem_idx ON archive.snapshots(problem_id);
CREATE INDEX archive_snapshots_category_idx ON archive.snapshots(category_id);

CREATE TABLE archive.snapshot_objects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id uuid NOT NULL REFERENCES archive.snapshots(id) ON DELETE CASCADE,
    -- Account removal cascades snapshots and owned objects in one transaction.
    -- Check the reference after both cascades finish, without dropping history
    -- links when an unrelated object is deleted on its own.
    object_id uuid NOT NULL REFERENCES archive.objects(id) DEFERRABLE INITIALLY DEFERRED,
    payload jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, object_id)
);
CREATE INDEX snapshot_objects_object_idx ON archive.snapshot_objects(object_id);

-- Every table gets timestamp maintenance, RLS, and explicit privileges.
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname IN ('user_data', 'catalog', 'archive')
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', item.schemaname, item.tablename);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', item.schemaname, item.tablename);
        EXECUTE format('REVOKE ALL ON TABLE %I.%I FROM PUBLIC, anon, authenticated', item.schemaname, item.tablename);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO service_role', item.schemaname, item.tablename);
        EXECUTE format(
            'CREATE TRIGGER record_timestamps BEFORE INSERT OR UPDATE ON %I.%I FOR EACH ROW EXECUTE FUNCTION app_private.record_timestamps()',
            item.schemaname, item.tablename
        );
        EXECUTE format('COMMENT ON COLUMN %I.%I.payload IS %L', item.schemaname, item.tablename,
            'Reserved nullable JSONB slot. No business payload format has been selected.');
    END LOOP;
END;
$$;

-- Users may manage only their own rows. Identity and timestamps are not writable
-- through client UPDATE grants. Relationship changes can be decided later.
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'user_data'
    LOOP
        EXECUTE format('GRANT SELECT, INSERT, DELETE ON TABLE user_data.%I TO authenticated', item.tablename);
        EXECUTE format('GRANT UPDATE (payload) ON TABLE user_data.%I TO authenticated', item.tablename);
        EXECUTE format(
            'CREATE POLICY own_records ON user_data.%I FOR ALL TO authenticated USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id)',
            item.tablename
        );
    END LOOP;
END;
$$;

GRANT SELECT ON ALL TABLES IN SCHEMA catalog TO anon, authenticated;

CREATE POLICY published_contests ON catalog.contests FOR SELECT TO anon, authenticated USING (is_public);
CREATE POLICY published_problems ON catalog.problems FOR SELECT TO anon, authenticated USING (is_public);
CREATE POLICY published_categories ON catalog.categories FOR SELECT TO anon, authenticated USING (is_public);

-- Relationship reads also respect the publication of their parent records.
CREATE POLICY published_memberships ON catalog.contest_problems FOR SELECT TO anon, authenticated USING (
    is_public
    AND EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id = contest_id)
    AND EXISTS (SELECT 1 FROM catalog.problems p WHERE p.id = problem_id)
);
CREATE POLICY published_entries ON catalog.category_entries FOR SELECT TO anon, authenticated USING (
    is_public
    AND EXISTS (SELECT 1 FROM catalog.categories c WHERE c.id = category_id)
    AND (child_category_id IS NULL OR EXISTS (SELECT 1 FROM catalog.categories c WHERE c.id = child_category_id))
    AND (contest_id IS NULL OR EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id = contest_id))
);
CREATE POLICY published_variants ON catalog.statement_variants FOR SELECT TO anon, authenticated USING (
    is_public
    AND EXISTS (SELECT 1 FROM catalog.problems p WHERE p.id = problem_id)
    AND (contest_problem_id IS NULL OR EXISTS (SELECT 1 FROM catalog.contest_problems cp WHERE cp.id = contest_problem_id))
);
CREATE POLICY published_materials ON catalog.materials FOR SELECT TO anon, authenticated USING (
    is_public
    AND (contest_id IS NULL OR EXISTS (SELECT 1 FROM catalog.contests c WHERE c.id = contest_id))
    AND (problem_id IS NULL OR EXISTS (SELECT 1 FROM catalog.problems p WHERE p.id = problem_id))
);

-- Public object metadata can be read; private objects require their owner.
-- Publication and all archive writes remain server-only.
GRANT SELECT ON archive.objects TO anon, authenticated;
CREATE POLICY public_objects ON archive.objects FOR SELECT TO anon USING (is_public);
CREATE POLICY accessible_objects ON archive.objects FOR SELECT TO authenticated USING (
    is_public OR owner_id = (SELECT auth.uid())
);

-- Historical snapshots are owner/server-only even for published catalog data.
GRANT SELECT ON archive.snapshots, archive.snapshot_objects TO authenticated;
CREATE POLICY own_snapshots ON archive.snapshots FOR SELECT TO authenticated USING (
    owner_id = (SELECT auth.uid())
);
CREATE POLICY own_snapshot_links ON archive.snapshot_objects FOR SELECT TO authenticated USING (
    EXISTS (SELECT 1 FROM archive.snapshots s WHERE s.id = snapshot_id)
    AND EXISTS (SELECT 1 FROM archive.objects o WHERE o.id = object_id)
);

-- New migrations must explicitly add grants and RLS for any new tables.
ALTER DEFAULT PRIVILEGES IN SCHEMA user_data, catalog, archive
    REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA app_private
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

COMMIT;
