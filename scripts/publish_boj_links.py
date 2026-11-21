"""Replay the reviewed BOJ catalog bindings through the existing publication RPC."""
import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.app import StorageApp


def judge_links(row):
    return {k: v for k, v in row['link'].items() if k in ('qoj', 'cf', 'atcoder', 'ojuz') and v}


def published(problem, match):
    url = f"https://acmicpc.net/problem/{match['bojId']}"
    if match['partOrder'] is None:
        return problem['link'].get('boj') == url
    return any(p['url'] == url and p['order'] == match['partOrder'] for p in problem.get('bojParts', []))


def publish(app, manifest, apply):
    data = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    contests = {c['id']: c for c in data['contests']}
    problems = {p['id']: p for p in data['problems']}
    versions = data['versions']
    changed = skipped = 0
    for entry in manifest['contests']:
        cid = entry['contestId']
        contest = contests[cid]
        if any(contest.get(k) != v for k, v in entry['identity'].items()):
            raise ValueError(f'Contest identity changed for {cid}')
        edition = entry.get('editionPage')
        if edition:
            url = f"https://acmicpc.net/category/{edition['categoryId']}"
            if contest['link'].get('boj') == url:
                skipped += 1
                continue
            if contest['link'].get('boj'):
                raise ValueError(f'Contest {cid} already points to a different BOJ source')
            if apply:
                app.rpc('catalog', 'admin_publish_boj_edition_page', {
                    'p_contest_id': cid, 'p_version': versions['contests'][cid],
                    'p_category_id': edition['categoryId'], 'p_section': edition['section'],
                    'p_observed_at': edition['observedAt'],
                }, privileged=True)
            changed += 1
            continue
        source = manifest['sources'][str(entry['sourceId'])]
        url = f"https://acmicpc.net/category/detail/{entry['sourceId']}"
        if contest['link'].get('boj') not in (None, url):
            raise ValueError(f'Contest {cid} already points to a different BOJ source')
        pending = []
        for match in entry['matches']:
            pid = match['problemId']
            problem = problems[pid]
            if published(problem, match):
                continue
            if judge_links(problem) != match['judgeLinks'] or problem['title'] != match['reviewedTitle']:
                raise ValueError(f'Problem identity changed for {pid}')
            if match['partOrder'] is None and problem['link'].get('boj'):
                raise ValueError(f'Problem {pid} already has a different preferred BOJ source')
            pending.append(match)
        if not pending and contest['link'].get('boj') == url:
            skipped += 1
            continue
        if apply:
            matches = [{k: m[k] for k in ('problemId', 'bojId', 'partOrder', 'evidence')} |
                       {'version': versions['problems'][m['problemId']]} for m in pending]
            app.rpc('catalog', 'admin_publish_boj', {
                'p_contest_id': cid, 'p_version': versions['contests'][cid], 'p_group_id': None,
                'p_source': source, 'p_matches': matches, 'p_reviewer': None,
            }, privileged=True)
            for match in pending:
                problem = problems[match['problemId']]
                problem_url = f"https://acmicpc.net/problem/{match['bojId']}"
                if match['partOrder'] is None:
                    problem['link']['boj'] = problem_url
                else:
                    problem.setdefault('bojParts', []).append({'url': problem_url, 'order': match['partOrder']})
        changed += 1
        if changed % 100 == 0:
            print(f'{changed} contests processed', flush=True)
    return changed, skipped


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'raw/audit/boj-bindings.json.gz')
    parser.add_argument('--apply', action='store_true', help='write to the configured catalog')
    args = parser.parse_args()
    with gzip.open(args.manifest, 'rt', encoding='utf-8') as stream:
        changes, existing = publish(StorageApp(), json.load(stream), args.apply)
    print(f'{changes} contests {"published" if args.apply else "to publish"}, {existing} already current')
