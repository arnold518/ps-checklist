"""Record reviewed statement replacements for the six forbidden QOJ pages."""

import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.enrich_qoj_problems import checkpoint_path  # noqa: E402
from scripts.fetch_raw_contests import atomic_json  # noqa: E402
from scripts.reviewed_qoj_fallbacks import PROOFS, reviewed  # noqa: E402


def main():
    root = ROOT / 'storage/output/raw-fetch'
    backups = root / 'correction-backups/qoj-forbidden-20261023'
    for row, proof in PROOFS.items():
        path = root / 'rows' / f'{row:04d}.json'
        artifact = json.loads(path.read_text())
        checkpoint = checkpoint_path(root / 'qoj-problems', proof['missing'][2])
        inaccessible = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        if (inaccessible.get('status') != 'unavailable'
                or inaccessible.get('code') != 'UPSTREAM_FORBIDDEN'
                or inaccessible.get('url') != proof['missing'][2]
                or not artifact.get('qojMaterialsPending')
                or artifact['status'] not in ('partial', 'deferred')):
            raise RuntimeError(f'Row {row} no longer has the reviewed QOJ blockage.')
        if row == 58:
            tasks = next(item['data']['problems'] for item in artifact['result']['data']['sources']
                         if item['data']['source'] == 'qoj')
            changes = {
                'B': ('https://qoj.ac/problem/15785', 'Burning Block', 'Burning Blocks'),
                'M': ('https://qoj.ac/problem/15796', 'Scrambled Scrabble', 'Predisposed'),
            }
            for task in tasks:
                if task['index'] in changes:
                    url, old, new = changes[task['index']]
                    if task['url'] != url or task['name'] not in (old, new):
                        raise RuntimeError('The Jakarta task title differs from the reviewed PDF.')
                    task['name'] = new
        artifact['qojFallback'] = proof['missing'][2]
        if reviewed(artifact) is None:
            raise RuntimeError(f'Row {row} differs from the reviewed contest and PDF mapping.')
        backups.mkdir(parents=True, exist_ok=True)
        if not (backups / path.name).exists():
            shutil.copy2(path, backups / path.name)
        atomic_json(path, artifact)
        print(f'row {row}: reviewed fallback recorded for {proof["missing"][1]}', flush=True)


if __name__ == '__main__':
    main()
