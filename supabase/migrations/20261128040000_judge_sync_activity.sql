BEGIN;

CREATE OR REPLACE FUNCTION public.judge_sync_overview()
RETURNS SETOF jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT jsonb_build_object('source',a.source,'handle',a.handle,'feeds',(
        SELECT jsonb_object_agg(j.feed,jsonb_build_object(
            'lastSyncedAt',j.last_success,
            'error',j.error_code,
            'pending',j.due_at<=now() OR j.lease_until>now(),
            'activity',CASE
                WHEN j.error_code IS NOT NULL THEN 'retry'
                WHEN j.feed='submissions' AND (c.cursor-'watermark')<>'{}'::jsonb
                    AND COALESCE(c.cursor->>'watermark','') IN ('','0') THEN 'backfill'
                WHEN j.feed='progress' AND c.cursor<>'{}'::jsonb THEN 'importing'
                WHEN j.feed='contests' AND j.cursor->>'draining'='true' THEN 'importing'
                WHEN j.lease_until>now() THEN 'running'
                WHEN j.due_at<=now() THEN 'queued'
                ELSE 'idle'
            END,
            'count',CASE j.feed
                WHEN 'submissions' THEN (SELECT count(*) FROM app_private.judge_submissions s WHERE s.account_id=a.id)
                WHEN 'progress' THEN (SELECT count(*) FROM app_private.judge_progress_observations p WHERE p.account_id=a.id AND p.status>0)
                WHEN 'contests' THEN (SELECT count(*) FROM app_private.judge_contest_imports i WHERE i.account_id=a.id AND i.imported_at IS NOT NULL)
            END
        ))
        FROM app_private.judge_sync_jobs j LEFT JOIN app_private.judge_sync_checkpoints c
            ON c.account_id=j.account_id AND c.feed=j.feed
        WHERE j.account_id=a.id
    )) FROM app_private.judge_sync_accounts a
    WHERE a.user_id=auth.uid() AND a.source IN ('cf','atcoder','doj','boj','solvedac')
    ORDER BY a.source;
$$;

NOTIFY pgrst,'reload schema';
COMMIT;
