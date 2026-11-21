BEGIN;

CREATE OR REPLACE FUNCTION public.deployment_set_order(p_rows jsonb)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    LOCK TABLE app_private.catalog_order IN SHARE ROW EXCLUSIVE MODE;
    DELETE FROM app_private.catalog_order
    WHERE NOT (COALESCE(p_rows, '{}'::jsonb) ? url);

    INSERT INTO app_private.catalog_order AS existing(url,position)
        SELECT key,value::text::numeric FROM jsonb_each(p_rows)
        ON CONFLICT (url) DO UPDATE SET position=EXCLUDED.position
        WHERE existing.position IS DISTINCT FROM EXCLUDED.position;
END;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
