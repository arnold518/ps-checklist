"""Summarize the unpublished raw contest fetch checkpoints."""

from collections import Counter
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'storage/output/raw-fetch'


def main():
    manifest = json.loads((OUTPUT / 'manifest.json').read_text())
    saved = [json.loads(path.read_text()) for path in sorted((OUTPUT / 'rows').glob('*.json'))]
    statuses = Counter(item['status'] for item in saved)
    warnings = Counter(warning['code'] for item in saved if item.get('result')
                       for warning in item['result']['meta']['warnings'])
    sources = Counter(item.get('sourceCount', 0) for item in saved if item.get('result'))
    print(f"CSV: {manifest['rows']} rows; saved: {len(saved)}; remaining: {manifest['rows'] - len(saved)}")
    print('Results:', ', '.join(f'{key}={value}' for key, value in sorted(statuses.items())))
    print('Sources per row:', ', '.join(f'{key}={value}' for key, value in sorted(sources.items())))
    print('Warnings:', ', '.join(f'{key}={value}' for key, value in warnings.most_common(10)))
    print('QOJ materials pending:', sum(bool(item.get('qojMaterialsPending')) for item in saved))
    cooldown = OUTPUT / 'cooldown.json'
    if cooldown.exists():
        remaining = int(json.loads(cooldown.read_text()).get('untilEpoch', 0) - time.time())
        if remaining > 0:
            print(f'Legacy row cooldown (base pass ignores it): {remaining}s remaining')
    print('Full fetch complete:', (OUTPUT / 'complete.json').is_file())
    print('Base fetch complete:', (OUTPUT / 'base_complete.json').is_file())
    qoj_cooldown = OUTPUT / 'qoj-problems-cooldown.json'
    if qoj_cooldown.exists():
        state = json.loads(qoj_cooldown.read_text())
        remaining = int(state.get('untilEpoch', 0) - time.time())
        if remaining > 0:
            print(f"QOJ problem queue: {remaining}s cooldown after {state.get('strikes', 0)} rate limit(s)")
    print('Output:', OUTPUT)


if __name__ == '__main__':
    main()
