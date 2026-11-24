"""Apply reviewed DOJ archive links to the existing ICPC and Olympiad catalog."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.app import StorageApp, StorageError, read_environment


def load_bindings(path):
    with path.open(newline='', encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    editions = {}
    categories = Counter()
    for row in rows:
        url = row['url']
        identity = {'contestId': row['contestId'], 'title': row['contestTitle'], 'url': url}
        edition = editions.get(url)
        if edition is None:
            edition = {**identity, 'problems': []}
            editions[url] = edition
            categories[row['category']] += 1
        if any(edition[key] != value for key, value in identity.items()):
            raise ValueError(f'Archive points to conflicting catalog editions: {url}')
        edition['problems'].append({'problemId': row['problemId'], 'title': row['problemTitle'],
                                    'dojId': int(row['dojId'])})
    return list(editions.values()), len({row['problemId'] for row in rows}), categories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'raw/audit/doj-archive-bindings.csv')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.storage')
    parser.add_argument('--apply', action='store_true', help='Write the reviewed links to the selected Supabase project.')
    args = parser.parse_args()
    try:
        editions, problems, categories = load_bindings(args.manifest)
        print(f'{categories["ICPC"]} ICPC and {categories["Olympiad"]} Olympiad editions. {problems} distinct problems.')
        if args.apply:
            app = StorageApp(read_environment(args.env_file))
            result = app.rpc('catalog', 'publish_doj_archives', {'p_editions': editions}, privileged=True)
            print(f"{result['editions']} editions published, {result['problemLinksAdded']} problem links added.")
    except (OSError, ValueError, StorageError) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    main()
