-- TEST ONLY: minimum Supabase Auth interfaces for isolated PostgreSQL tests.
-- Production migrations never create/replace Supabase's auth schema or roles.
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid()
RETURNS uuid LANGUAGE sql STABLE
AS $$
    SELECT (NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid;
$$;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;

-- Simulate permissive pre-existing grants: the migration must revoke them.
ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO anon, authenticated;
