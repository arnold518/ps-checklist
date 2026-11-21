BEGIN;

-- These RPCs report application-level conflicts. SQLSTATE 40001 makes hosted
-- PostgREST retry the transaction. An explicit HTTP 409 returns to the caller.
DO $migration$
DECLARE
    rpc regprocedure;
    definition text;
BEGIN
    FOREACH rpc IN ARRAY ARRAY[
        'catalog.admin_publish(jsonb,jsonb,jsonb)',
        'catalog.admin_publish_boj(uuid,text,text,jsonb,jsonb,uuid)',
        'catalog.admin_publish_boj_edition_page(uuid,text,bigint,text,timestamp with time zone)',
        'catalog.admin_remove(uuid,text)',
        'catalog.admin_workspace_publish(uuid,uuid,uuid[])',
        'catalog.admin_workspace_save(uuid,uuid,jsonb)',
        'public.deployment_admin_step(text,uuid,text,text,jsonb)',
        'public.deployment_finish(text,uuid,text,integer,boolean,integer)',
        'public.save_problem_note(uuid,uuid,uuid,integer)'
    ]::regprocedure[] LOOP
        definition := pg_get_functiondef(rpc);
        IF strpos(definition, $code$ERRCODE='40001'$code$) = 0 THEN
            RAISE EXCEPTION 'Expected conflict code in %', rpc;
        END IF;
        definition := replace(definition, $code$ERRCODE='40001'$code$, $code$ERRCODE='PT409'$code$);
        definition := replace(definition, $code$SQLSTATE='40001'$code$, $code$SQLSTATE IN ('40001','PT409')$code$);
        EXECUTE definition;
    END LOOP;
END;
$migration$;

COMMIT;
