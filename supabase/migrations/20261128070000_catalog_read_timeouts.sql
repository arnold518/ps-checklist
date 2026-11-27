BEGIN;

-- PostgREST uses these limits for the two read-only catalog RPCs. Each response
-- includes the curated catalog, and the signed-in read also resolves synced
-- progress and personal contests. Keep both inside the Worker's 20s budget.
ALTER FUNCTION public.deployment_catalog() SET statement_timeout TO '10s';
ALTER FUNCTION public.deployment_state() SET statement_timeout TO '15s';

NOTIFY pgrst,'reload schema';
COMMIT;
