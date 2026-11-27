BEGIN;

-- The BOJ binding was published before QOJ titles were protected.
UPDATE catalog.problems
SET payload=jsonb_set(payload,'{title}','"Catfish Farm"'),
    refresh_policy=jsonb_set(refresh_policy,'{fields,title}',jsonb_build_object(
        'source','qoj','value','Catfish Farm','url','https://qoj.ac/problem/4561','fetchedAt',now()))
        || '{"source":"qoj"}'::jsonb
WHERE payload->'link'->>'qoj'='https://qoj.ac/problem/4561'
    AND payload->>'title'='메기 농장'
    AND refresh_policy->'fields'->'title'->>'source'='boj'
    AND refresh_policy->'fields'->'title'->>'url'='https://acmicpc.net/problem/25438'
    AND NOT COALESCE(refresh_policy->'manual' ? 'title',false);

COMMIT;
