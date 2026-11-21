"""Publish fetched raw rows that pass the admin review rules.

The command refuses to start until every CSV row has a saved base fetch artifact.
Rows requiring a source, problem match, or ordered-document decision remain
unpublished with a reason in the local receipt directory.
"""

import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sys
import unicodedata
import uuid
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.reviewed_qoj_fallbacks import reviewed as reviewed_qoj_fallback  # noqa: E402
from scripts.official_koi import verified_order as verified_koi_order  # noqa: E402
from scripts.official_ktst import verified_order as verified_ktst_order  # noqa: E402
from scripts.official_joisc import (  # noqa: E402
    choose_reviewed_match as choose_reviewed_joisc_match,
    choose_reviewed_translation as choose_reviewed_joisc_translation,
    verified_order as verified_joisc_order,
)
from scripts.official_joisc_legacy import reviewed as reviewed_legacy_joisc  # noqa: E402
from scripts.official_joi_open import verified_order as verified_joi_open_order  # noqa: E402
from scripts.official_jakarta import verified_order as verified_jakarta_order  # noqa: E402
from scripts.official_swerc import (  # noqa: E402
    choose_reviewed_extras as choose_reviewed_swerc_extras,
    reviewed as reviewed_swerc,
    verified_order as verified_swerc_order,
)
from scripts.official_cerc import verified_order as verified_cerc_order  # noqa: E402
from scripts.official_ceoi import (  # noqa: E402
    choose_reviewed_match as choose_reviewed_ceoi_match,
    verified_order as verified_ceoi_order,
)
from scripts.official_apio import (  # noqa: E402
    choose_reviewed_match as choose_reviewed_apio_match,
    verified_order as verified_apio_order,
)
from scripts.ordered_documents import verified_filename_order  # noqa: E402
from scripts.official_ordered_editorials import (  # noqa: E402
    choose_reviewed_ioi_match, choose_reviewed_joi_matches,
    verified_ioi_order, verified_order, verified_recent_joi,
)
from scripts.usaco_official import (  # noqa: E402
    qoj_refs, verified_exception as verified_usaco_exception, verified_official,
)
from storage.admin import make_draft, validate_form  # noqa: E402
from storage.app import StorageApp, StorageError  # noqa: E402
from storage.archive import ArchiveStore, LOCAL_ROOT, MAX_TOTAL, material_url  # noqa: E402
from storage.problem_merge import resolve_choices, title_key  # noqa: E402


MIN_FREE_BYTES = 3 * 1024 ** 3
BACKUP_ARCHIVE = Path.home() / '.local/share/ps-checklist/backups/archive'
REVIEWED_CF_ATTACHMENTS = json.loads(
    (ROOT / 'scripts/reviewed_cf_attachments.json').read_text())

BINUS_2022_EDITORIAL_MIRROR = (
    'https://icpcarchive.github.io/Asia%20Pacific%20Contests/Indonesia/'
    '2022%20Asia%20Jakarta%20Regional%20Contest/solution.pdf')
BINUS_2022_EDITORIAL_SHA256 = '5b209f9d2d2e3e44636fb294b84e59839128ea6959e4d9b5adbde47a0663efc5'


def reviewed_binus_editorial(artifact):
    """Use the matching ICPC Archive copy while BINUS's PDF host is unreachable."""
    if artifact['row'] != 61:
        return None
    raw = artifact['raw']
    original = 'https://competition.binus.ac.id/icpc2022/problem_analysis.pdf'
    if (raw.get('year') != '2022'
            or raw.get('category') != 'ICPC > Regionals > Asia Pacific > Regionals > Indonesia (Jakarta)'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1109'
            or raw.get('link.official') != 'https://competition.binus.ac.id/icpc2022/'
            or raw.get('link.editorial') != original
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    return original, BINUS_2022_EDITORIAL_MIRROR

# Exact, row-scoped judge naming differences checked against both task lists.
REVIEWED_PROBLEM_MATCHES = {
    65: ('https://qoj.ac/contest/2342', 'https://codeforces.com/gym/102001',
         'https://qoj.ac/problem/13154', 'Rotating Gears',
         'https://codeforces.com/gym/102001/problem/B', 'Rotating Gear'),
    74: ('https://qoj.ac/contest/2768', 'https://codeforces.com/gym/105544',
         'https://qoj.ac/problem/15824', 'Baker’s Dilemma',
         'https://codeforces.com/gym/105544/problem/F', "Baker's Dilemma"),
    182: ('https://qoj.ac/contest/2030', 'https://codeforces.com/gym/104945',
          'https://qoj.ac/problem/10675', 'Cards',
          'https://codeforces.com/gym/104945/problem/A', 'Card game'),
    7: ('https://qoj.ac/contest/431', 'https://codeforces.com/gym/102511',
        'https://qoj.ac/problem/2344', "Hobson's Trains",
        'https://codeforces.com/gym/102511/problem/H', "Hobsons' trains"),
    251: ('https://qoj.ac/contest/639', 'https://codeforces.com/contest/1510',
          'https://qoj.ac/problem/1666', 'Equilibrium Point /\\/\\',
          'https://codeforces.com/contest/1510/problem/E',
          'Equilibrium Point /\\textbackslash/\\textbackslash'),
    # The apostrophe style differs, but both lists have the same 15 positions.
    250: ('https://qoj.ac/contest/2862', 'https://codeforces.com/gym/102896',
          'https://qoj.ac/problem/16960', 'Kate’s 2021 Celebration',
          'https://codeforces.com/gym/102896/problem/K', "Kate's 2021 Celebration"),
    # Codeforces includes a literal TeX escape before the percent sign.
    273: ('https://qoj.ac/contest/1792', 'https://codeforces.com/gym/104848',
          'https://qoj.ac/problem/9289', '1%-Euclidean',
          'https://codeforces.com/gym/104848/problem/I', '1\\%-Euclidean'),
    # The merge title key discards the one-word title "Go" as a stopword.
    96: ('https://qoj.ac/contest/1235', 'https://codeforces.com/gym/102992',
         'https://qoj.ac/problem/6424', 'Go',
         'https://codeforces.com/gym/102992/problem/G', 'Go'),
    93: ('https://qoj.ac/contest/1435', 'https://codeforces.com/gym/104821',
         'https://qoj.ac/problem/7733', 'Cool, It’s Yesterday Four Times More',
         'https://codeforces.com/gym/104821/problem/A',
         "Cool, It's Yesterday Four Times More"),
    41: ('https://qoj.ac/contest/1988', 'https://codeforces.com/gym/100803',
         'https://qoj.ac/problem/10534', '$L_{\\infty}$ Jumps',
         'https://codeforces.com/gym/100803/problem/K', '{infinity} Jumps'),
    42: (
        ('https://qoj.ac/contest/1978', 'https://codeforces.com/gym/102014',
         'https://qoj.ac/problem/11395', 'Dragon’s Cruller',
         'https://codeforces.com/gym/102014/problem/E', "Dragon's Cruller"),
        ('https://qoj.ac/contest/1978', 'https://codeforces.com/gym/102014',
         'https://qoj.ac/problem/11398', 'Don’t Burst the Balloon',
         'https://codeforces.com/gym/102014/problem/H', "Don't Burst the Balloon"),
    ),
    45: ('https://qoj.ac/contest/3710', 'https://codeforces.com/gym/101413',
         'https://qoj.ac/problem/17524', "Where's Wally",
         'https://codeforces.com/gym/101413/problem/H', 'Where’s Wally'),
    46: ('https://qoj.ac/contest/3618', 'https://codeforces.com/gym/101414',
         'https://qoj.ac/problem/19650', "Chemist's Math",
         'https://codeforces.com/gym/101414/problem/F', 'Chemist’s Math'),
    298: ('https://qoj.ac/contest/2177', 'https://codeforces.com/gym/101612',
          'https://qoj.ac/problem/12713', 'Boolean Satisfiability',
          'https://codeforces.com/gym/101612/problem/B', 'Boolean Satisfability'),
    300: ('https://qoj.ac/contest/2175', 'https://codeforces.com/gym/100801',
          'https://qoj.ac/problem/12744', 'Journey to the “The World\'s Start”',
          'https://codeforces.com/gym/100801/problem/J', 'Journey to the "The World\'s Start"'),
    302: ('https://qoj.ac/contest/2173', 'https://codeforces.com/gym/100269',
          'https://qoj.ac/problem/12767', 'J',
          'https://codeforces.com/gym/100269/problem/J', 'J'),
    # NWERC's official 2023 problem set prints "Date Picker" at D.
    151: ('https://qoj.ac/contest/1446', 'https://codeforces.com/gym/105112',
          'https://qoj.ac/problem/7910', 'Data Picker',
          'https://codeforces.com/gym/105112/problem/D', 'Date Picker'),
    # SWERC's 2019 problem set prints "Bird Watching" at K.
    186: ('https://qoj.ac/contest/511', 'https://codeforces.com/gym/102501',
          'https://qoj.ac/problem/2657', 'Bird Watching',
          'https://codeforces.com/gym/102501/problem/K', 'Birdwatching'),
    # The 2019 Latin America regional problem set prints "Jumping Grasshopper" at J.
    341: ('https://qoj.ac/contest/2508', 'https://codeforces.com/gym/102428',
          'https://qoj.ac/problem/15691', 'Jumping Grasshopper',
          'https://codeforces.com/gym/102428/problem/J', 'Jumping Grasshoper'),
    # Moscow 2014 has the same 12 tasks in the same positions. QOJ's I
    # statement PDF itself prints "Interactive Primes Guessing"; the CF
    # organizer mirror prints "Advanced 2048" for A.
    280: (
        ('https://qoj.ac/contest/3249', 'https://codeforces.com/gym/100519',
         'https://qoj.ac/problem/16742', 'Game 2048 again',
         'https://codeforces.com/gym/100519/problem/A', 'Advanced 2048'),
        ('https://qoj.ac/contest/3249', 'https://codeforces.com/gym/100519',
         'https://qoj.ac/problem/16750', 'Interactive problem',
         'https://codeforces.com/gym/100519/problem/I', 'Interactive Primes Guessing'),
    ),
    # The original Moscow 2013 problem-set PDF gives these full titles;
    # Codeforces' live table abbreviates both.
    281: (
        ('https://qoj.ac/contest/3248', 'https://codeforces.com/gym/100257',
         'https://qoj.ac/problem/16756', 'Charisma and Skill',
         'https://codeforces.com/gym/100257/problem/C', 'Charisma'),
        ('https://qoj.ac/contest/3248', 'https://codeforces.com/gym/100257',
         'https://qoj.ac/problem/16765', 'Liar, Liar!',
         'https://codeforces.com/gym/100257/problem/L', 'Liar'),
    ),
}


def reviewed_position_variant(row, left, right):
    """Accept only a specifically reviewed same-position title difference."""
    if row not in (65, 74, 93, 182, 250, 281):
        return False
    reviewed = REVIEWED_PROBLEM_MATCHES.get(row)
    variants = reviewed if isinstance(reviewed[0], tuple) else (reviewed,)
    return any((left.get('url'), left.get('name'), right.get('url'),
                right.get('name')) == variant[2:] for variant in variants)

# The organizer PDFs contain these World Finals tasks in this position. The
# two 2020 differences are apostrophe typography; the 2013 PDF prints the
# Cyrillic task name while Codeforces transliterates it.
REVIEWED_WORLD_FINAL_MATCHES = {
    6: ('2020', '782', '104633', (
        ('https://qoj.ac/problem/2169', "'S No Problem",
         'https://codeforces.com/gym/104633/problem/J', '’S No Problem'),
        ('https://qoj.ac/problem/2173', "What's Our Vector, Victor?",
         'https://codeforces.com/gym/104633/problem/N', 'What’s Our Vector, Victor?'),
    )),
    13: ('2013', '278', '101208', (
        ('https://qoj.ac/problem/8859', 'Матрёша',
         'https://codeforces.com/gym/101208/problem/H', 'Matryoshka'),
    )),
}


def choose_reviewed_world_final_matches(draft, artifact):
    reviewed = REVIEWED_WORLD_FINAL_MATCHES.get(artifact['row'])
    if not reviewed:
        return False
    year, qoj_id, gym_id, variants = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > World Finals' or raw.get('year') != year
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_id}'
            or raw.get('link.cf') != f'https://codeforces.com/gym/{gym_id}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    qoj, cf = sources.get('qoj') or [], sources.get('cf') or []
    if (len(qoj) != len(cf) or len(qoj) < 10
            or len({item['url'] for item in qoj}) != len(qoj)
            or len({item['url'] for item in cf}) != len(cf)):
        return False
    pairs = {(left['url'], left['name'], right['url'], right['name'])
             for left, right in zip(qoj, cf)}
    if not set(variants).issubset(pairs):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if len(review) != len(variants):
        return False
    targets = {left: next((problem['id'] for problem in draft['problems']
                           if problem['link'].get('qoj') == left), None)
               for left, _, _, _ in variants}
    if any(not target for target in targets.values()):
        return False
    by_cf = {(right, right_title): left
             for left, _, right, right_title in variants}
    if any(item['source'] != 'cf' or (item['url'], item['title']) not in by_cf
           for item in review):
        return False
    for item in review:
        item['choice'] = targets[by_cf[(item['url'], item['title'])]]
    return True


def choose_reviewed_world_final_2022_shared(draft, artifact):
    """Keep five existing 2023 CF URLs for tasks reused in both Finals."""
    if artifact['row'] != 4 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > World Finals' or raw.get('year') != '2022'
            or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1661'
            or raw.get('link.cf') != 'https://codeforces.com/gym/105254'
            or raw.get('link.statement') !=
               'https://icpc.global/worldfinals/problems/2022-ICPC-World-Finals/icpc2022.pdf'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return False
    qoj, cf = sources['qoj']['problems'], sources['cf']['problems']
    if (len(qoj) != len(cf) or len(qoj) != 11
            or [item['index'] for item in qoj] != list('PQRSTUVWXYZ')
            or [item['index'] for item in cf] != list('PQRSTUVWXYZ')
            or any(reviewed_title_key(left['name']) != reviewed_title_key(right['name'])
                   for left, right in zip(qoj, cf))):
        return False
    shared = {
        'P': ('Turning Red', 'https://codeforces.com/gym/105255/problem/G'),
        'S': ('Bridging the Gap', 'https://codeforces.com/gym/105255/problem/J'),
        'T': ('Carl’s Vacation', 'https://codeforces.com/gym/105255/problem/D'),
        'V': ('Three Kinds of Dice', 'https://codeforces.com/gym/105255/problem/C'),
        'W': ('Riddle of the Sphinx', 'https://codeforces.com/gym/105255/problem/A'),
    }
    by_index = {item['index']: item for item in qoj}
    by_problem = {problem['link'].get('qoj'): problem
                  for problem in draft['problems'] if problem['link'].get('qoj')}
    if any(by_problem.get(by_index[index]['url'], {}).get('link', {}).get('cf') != cf_url
           or by_index[index]['name'] != title
           for index, (title, cf_url) in shared.items()):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    expected = {f'https://codeforces.com/gym/105254/problem/{index}'
                for index in shared}
    if (len(review) != len(expected)
            or {item['url'] for item in review} != expected
            or any(item['source'] != 'cf' or
                   reviewed_title_key(item['title']) !=
                   reviewed_title_key(shared[item['url'].rsplit('/', 1)[-1]][0])
                   for item in review)):
        return False
    for item in review:
        item['choice'] = 'ignore'
    return True


def choose_reviewed_asia_east_2017_match(draft, artifact):
    """The original A/M order is in the contest PDF; CF's live table swaps it."""
    if artifact['row'] != 88 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > Regionals > Asia East Continent > Asia East Continent Final Contest'
            or raw.get('year') != '2017' or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/2026'
            or raw.get('link.cf') != 'https://codeforces.com/gym/101775'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return False
    qoj, cf = sources['qoj']['problems'], sources['cf']['problems']
    if (len(qoj) != 13 or len(cf) != 13
            or [item['index'] for item in qoj] != list('ABCDEFGHIJKLM')
            or [item['index'] for item in cf] != list('ABCDEFGHIJKLM')
            or (qoj[0]['name'], qoj[-1]['name']) != ('Chat Group', 'World Cup')
            or (cf[0]['name'], cf[-1]['name']) != ('World Cup', 'Chat Group')
            or not equivalent_task_titles(qoj, cf)
            or any(reviewed_title_key(left['name']) != reviewed_title_key(right['name'])
                   for left, right in zip(qoj[1:-1], cf[1:-1]))
            or not any(item.get('url') ==
                       'https://codeforces.com/gym/101775/attachments/download/6913/20172018-asia-east-continent-league-final-en.pdf'
                       for item in sources['cf'].get('materials') or [])):
        return False
    # The official problem set prints A Chat Group and M World Cup. Unique
    # titles let the normal merge attach CF's swapped A/M URLs by task identity.
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or review[0]['source'] != 'cf'
            or review[0]['url'] != 'https://codeforces.com/gym/101775/problem/I'
            or review[0]['title'] != "PLAYERUNKNOWN'S BATTLEGROUNDS"):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == 'https://qoj.ac/problem/11209'), None)
    if not target:
        return False
    review[0]['choice'] = target
    return True


def choose_reviewed_boi_2019_match(draft, artifact):
    """BOI's Day 1 PDF calls oj.uz's Valley task Alpine valley."""
    if artifact['row'] != 624 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Baltic Olympiad in Informatics (BOI)'
            or raw.get('year') != '2019' or raw.get('contest_label') != 'Day 1'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/2089'
            or raw.get('link.ojuz') != 'https://oj.uz/problems/source/boi2019day1'
            or raw.get('link.statement') != 'https://boi.cses.fi/files/boi2019_day1.pdf'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    qoj, ojuz = sources.get('qoj') or [], sources.get('ojuz') or []
    if ([(item['name'], item['url']) for item in qoj] != [
            ('Flash memory', 'https://qoj.ac/problem/11444'),
            ('Nautilus', 'https://qoj.ac/problem/11445'),
            ('Alpine valley', 'https://qoj.ac/problem/11446')]
            or [(item['name'], item['url']) for item in ojuz] != [
            ('Nautilus', 'https://oj.uz/problem/view/BOI19_nautilus'),
            ('Valley', 'https://oj.uz/problem/view/BOI19_valley')]):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or
            (review[0]['source'], review[0]['url'], review[0]['title']) !=
            ('ojuz', ojuz[1]['url'], ojuz[1]['name'])):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == qoj[2]['url']), None)
    if not target:
        return False
    review[0]['choice'] = target
    return True


def choose_reviewed_problem_match(draft, artifact):
    reviewed = REVIEWED_PROBLEM_MATCHES.get(artifact['row'])
    if not reviewed:
        return False
    variants = reviewed if isinstance(reviewed[0], tuple) else (reviewed,)
    qoj_contest, cf_contest = variants[0][:2]
    if any(variant[:2] != (qoj_contest, cf_contest) for variant in variants):
        return False
    raw = artifact['raw']
    if (raw.get('link.qoj') != qoj_contest or raw.get('link.cf') != cf_contest
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {item['data']['source']: item['data'].get('problems') or []
               for item in artifact['result']['data']['sources']}
    qoj = sources.get('qoj') or []
    cf = sources.get('cf') or []
    if (len(qoj) != len(cf) or len(qoj) < 2
            or len({item['url'] for item in qoj}) != len(qoj)
            or len({item['url'] for item in cf}) != len(cf)):
        return False
    pairs = {(left['url'], left['name'], right['url'], right['name'])
             for left, right in zip(qoj, cf)}
    if not all((qoj_url, qoj_title, cf_url, cf_title) in pairs
               for _, _, qoj_url, qoj_title, cf_url, cf_title in variants):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if len(review) != len(variants):
        return False
    by_cf = {(cf_url, cf_title): qoj_url
             for _, _, qoj_url, _, cf_url, cf_title in variants}
    if any(item['source'] != 'cf' or (item['url'], item['title']) not in by_cf
           for item in review):
        return False
    for item in review:
        qoj_url = by_cf[(item['url'], item['title'])]
        target = next((problem['id'] for problem in draft['problems']
                       if problem['link'].get('qoj') == qoj_url), None)
        if not target:
            return False
        item['choice'] = target
    return True


def ensure_archive_space(archive):
    if archive.backend != 'local':
        return
    missing_backup_bytes = sum(path.stat().st_size for path in LOCAL_ROOT.iterdir()
                               if path.is_file() and not (BACKUP_ARCHIVE / path.name).exists()) if LOCAL_ROOT.exists() else 0
    free = shutil.disk_usage(LOCAL_ROOT if LOCAL_ROOT.exists() else LOCAL_ROOT.parent).free
    if free - missing_backup_bytes - MAX_TOTAL < MIN_FREE_BYTES:
        raise StorageError('Local disk has insufficient room for selected files and their next backup.')


def load_batch(source, fetched):
    raw_bytes = source.read_bytes()
    manifest = json.loads((fetched / 'manifest.json').read_text())
    if hashlib.sha256(raw_bytes).hexdigest() != manifest['sourceSha256']:
        raise RuntimeError('The CSV changed after fetching; publication stopped.')
    with source.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != manifest['rows']:
        raise RuntimeError('The fetch manifest has a different row count.')
    complete_path = fetched / 'base_complete.json'
    if not complete_path.is_file():
        complete_path = fetched / 'complete.json'
    if not complete_path.is_file():
        raise RuntimeError('The base fetch has not completed; publication stopped.')
    complete = json.loads(complete_path.read_text())
    if complete['sourceSha256'] != manifest['sourceSha256'] or complete['rows'] != len(rows):
        raise RuntimeError('The fetch completion marker does not match this CSV.')
    artifacts = []
    for index, row in enumerate(rows, start=1):
        path = fetched / 'rows' / f'{index:04d}.json'
        if not path.is_file():
            raise RuntimeError(f'Row {index} has no saved fetch result; publication stopped.')
        artifact = json.loads(path.read_text())
        if (artifact['row'] != index or artifact['raw'] != row
                or artifact['requestKey'] != request_for(row).request_key):
            raise RuntimeError(f'Row {index} does not match the CSV; publication stopped.')
        artifacts.append(artifact)
    return manifest, artifacts


def selected_contest_materials(draft, raw, preferred_statement=None):
    """Select one contest statement/editorial per role, preferring CSV links."""
    available = draft['contest'].get('materials') or []
    chosen = []
    for role in ('statement', 'editorial'):
        raw_url = preferred_statement if role == 'statement' and preferred_statement else raw.get('link.' + role)
        item = next((item for item in available if item['role'] == role and item['url'] == raw_url), None) if raw_url else None
        item = item or next((item for item in available if item['role'] == role), None)
        if item:
            chosen.append(item)
    draft['contest']['materials'] = chosen


def reviewed_cf_attachment(artifact):
    """Return an attachment whose bytes and complete CF task list were reviewed."""
    proof = REVIEWED_CF_ATTACHMENTS.get(str(artifact['row']))
    if not proof or not artifact.get('result'):
        return None
    warnings = artifact['result']['meta']['warnings']
    if (len(warnings) != 1 or warnings[0].get('field') != 'cf'
            or warnings[0].get('code') not in
            ('PROBLEM_MATERIALS_UNAVAILABLE', 'PROBLEM_MATERIALS_INCOMPLETE')):
        return None
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) not in ({'cf'}, {'qoj', 'cf'}):
        return None
    source = sources['cf']
    tasks = source.get('problems') or []
    digest_input = [{'index': task['index'], 'name': task['name'], 'url': task['url']}
                    for task in tasks]
    digest = hashlib.sha256(json.dumps(digest_input, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (artifact['raw'].get('link.cf') != source.get('url')
            or artifact['requestKey'] != request_for(artifact['raw']).request_key
            or len(tasks) != proof['count'] or source.get('problemCount') != len(tasks)
            or digest != proof['problemsSha256']
            or not any(item.get('scope') == 'contest' and item.get('role') == 'statement'
                       and item.get('url') == proof['attachment']
                       for item in source.get('materials') or [])):
        return None
    if 'qoj' in sources:
        qoj = sources['qoj']
        qoj_tasks = qoj.get('problems') or []
        qoj_digest_input = [{'index': task['index'], 'name': task['name'],
                             'url': task['url']} for task in qoj_tasks]
        qoj_digest = hashlib.sha256(json.dumps(qoj_digest_input,
            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        statements = {item.get('problemKey') for item in qoj.get('materials') or []
                      if item.get('scope') == 'problem' and item.get('role') == 'statement'
                      and item.get('url')}
        contest_only = artifact['row'] == 87 and proof.get('qojContestOnly') is True
        if (artifact['raw'].get('link.qoj') != qoj.get('url')
                or len(qoj_tasks) != len(tasks)
                or qoj.get('problemCount') != len(qoj_tasks)
                or qoj_digest != proof.get('qojProblemsSha256')
                or (not contest_only and not all(task.get('key') in statements
                                             for task in qoj_tasks))
                or (contest_only and any(left.get('index') != right.get('index')
                                         or left.get('name') != right.get('name')
                                         for left, right in zip(qoj_tasks, tasks)))
                or not equivalent_task_titles(qoj_tasks, tasks)):
            return None
    return proof


def reviewed_title_key(title):
    normalized = unicodedata.normalize('NFKD', title or '').casefold()
    return ''.join(char for char in normalized if char.isalnum() and
                   not unicodedata.combining(char))


def equivalent_task_titles(left, right):
    left_keys = [reviewed_title_key(task.get('name')) for task in left]
    right_keys = [reviewed_title_key(task.get('name')) for task in right]
    return (all(left_keys) and len(set(left_keys)) == len(left_keys)
            and sorted(left_keys) == sorted(right_keys))


def choose_reviewed_attachment_matches(draft, artifact):
    """Resolve punctuation/diacritic variants for the reviewed two-judge PDFs."""
    if not reviewed_cf_attachment(artifact):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return False
    qoj = sources['qoj']['problems']
    cf = sources['cf']['problems']
    by_title = {reviewed_title_key(item['name']): item['url'] for item in qoj}
    by_cf = {(item['url'], item['name']): by_title[reviewed_title_key(item['name'])]
             for item in cf}
    review = draft.get('problemMerge', {}).get('review') or []
    if not review or any(item['source'] != 'cf' or
                         (item['url'], item['title']) not in by_cf for item in review):
        return False
    for item in review:
        qoj_url = by_cf[(item['url'], item['title'])]
        target = next((problem['id'] for problem in draft['problems']
                       if problem['link'].get('qoj') == qoj_url), None)
        if not target:
            return False
        item['choice'] = target
    return True


def required_attachment_urls(artifact):
    """Return files required to resolve the remaining harmless source warnings."""
    warnings = artifact['result']['meta']['warnings']
    if not warnings:
        return set()
    reviewed_pdf = reviewed_cf_attachment(artifact)
    if reviewed_pdf:
        return {reviewed_pdf['attachment']}
    swerc = reviewed_swerc(artifact)
    if swerc:
        return {swerc['statement']}
    if reviewed_large_nwerc_editorial(artifact):
        return {material_url(artifact['raw']['link.editorial'])}
    raw_category = [part.strip() for part in artifact['raw']['category'].split('>')]
    curated_category = artifact['request'].get('curation', {}).get('category')
    saved_category = artifact['result']['data'].get('curation', {}).get('category')
    if curated_category == saved_category == raw_category:
        warnings = [warning for warning in warnings
                    if not (warning.get('code') == 'CATEGORY_UNKNOWN'
                            and warning.get('field') == 'category')]
    if not warnings:
        return set()
    editorial = artifact['raw'].get('link.editorial') or ''
    if (all(warning.get('code') == 'UNSUPPORTED_RESOURCE' and warning.get('field') == 'editorial'
            for warning in warnings)
            and urlsplit(editorial).path.lower().endswith(('.zip', '.pptx'))):
        return {material_url(editorial)}
    return None


def reviewed_large_nwerc_editorial(artifact):
    """The 2021 organizer solution slides exceed discovery's 8 MB read cap."""
    if artifact['row'] != 153 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > Regionals > Europe > Regionals > Northwestern European Regional Contest (NWERC)'
            or raw.get('year') != '2021' or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/810'
            or raw.get('link.cf') != 'https://codeforces.com/gym/104064'
            or raw.get('link.official') != 'https://2021.nwerc.eu/'
            or raw.get('link.editorial') != 'https://2021.nwerc.eu/files/nwerc2021slides.pdf'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    warnings = artifact['result']['meta']['warnings']
    if (len(warnings) != 1 or warnings[0].get('code') != 'RESOURCE_TOO_LARGE'
            or warnings[0].get('field') != 'editorial'):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return False
    qoj, cf = sources['qoj'], sources['cf']
    left, right = qoj.get('problems') or [], cf.get('problems') or []
    if (len(left) != 12 or len(right) != 12
            or qoj['url'] != raw['link.qoj'] or cf['url'] != raw['link.cf']
            or any(a['index'] != b['index'] or title_key(a['name']) != title_key(b['name'])
                   for a, b in zip(left, right))):
        return False
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    return all(problem['key'] in statements for problem in left)


def covered_cf_material_warnings(artifact):
    """Accept reviewed CF detail warnings when QOJ covers the same task list.

    The Codeforces contest still supplies each problem link. Only its
    statement/editorial inspection or API metadata failed; QOJ supplied every statement.
    Other warning types and disagreements continue to require review.
    """
    warnings = artifact['result']['meta']['warnings']
    if not warnings or any(item.get('field') != 'cf' or item.get('code') not in
            ('PROBLEM_MATERIALS_UNAVAILABLE', 'PROBLEM_MATERIALS_INCOMPLETE',
             'CONTEST_METADATA_UNAVAILABLE')
            for item in warnings):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    qoj, cf = sources.get('qoj'), sources.get('cf')
    if not qoj or not cf:
        return False
    qoj_tasks, cf_tasks = qoj.get('problems') or [], cf.get('problems') or []
    if (not qoj_tasks or len(qoj_tasks) != len(cf_tasks)
            or qoj.get('problemCount') != len(qoj_tasks)
            or cf.get('problemCount') != len(cf_tasks)
            or artifact['raw'].get('link.qoj') != qoj.get('url')
            or artifact['raw'].get('link.cf') != cf.get('url')):
        return False
    if any(left.get('index') != right.get('index')
           or not (left.get('name') or '').strip()
           or ((title_key(left.get('name')) != title_key(right.get('name'))
                or not title_key(left.get('name')))
               and left.get('name') != right.get('name')
               and not reviewed_position_variant(artifact['row'], left, right))
           for left, right in zip(qoj_tasks, cf_tasks)):
        return False
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    return all(task.get('key') in statements for task in qoj_tasks)


def covered_moscow_2016_subset(artifact):
    """Codeforces lists nine of the twelve QOJ Moscow tasks, with matching labels."""
    if artifact['row'] != 278 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > Regionals > Northern Eurasia > Regionals > Moscow'
            or raw.get('year') != '2016' or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/3251'
            or raw.get('link.cf') != 'https://codeforces.com/gym/101137'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    warnings = artifact['result']['meta']['warnings']
    if ({(item.get('code'), item.get('field')) for item in warnings} != {
            ('PROBLEM_MATERIALS_UNAVAILABLE', 'cf'),
            ('SOURCE_LIST_MISMATCH', 'problems')} or len(warnings) != 2):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return False
    qoj, cf = sources['qoj'], sources['cf']
    full = qoj.get('problems') or []
    subset = cf.get('problems') or []
    if (qoj['url'] != raw['link.qoj'] or cf['url'] != raw['link.cf']
            or len(full) != 12 or len(subset) != 9
            or [item['index'] for item in full] != list('ABCDEFGHIJKL')
            or [item['index'] for item in subset] != list('ABDEFGIKL')):
        return False
    by_index = {item['index']: item for item in full}
    if any(title_key(item['name']) != title_key(by_index[item['index']]['name'])
           for item in subset):
        return False
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    return all(item['key'] in statements for item in full)


def covered_ojuz_list_warning(artifact):
    """Accept an incomplete oj.uz day index when all its tasks match QOJ.

    A missing oj.uz entry does not erase the QOJ task or its statement. A
    different task variant, duplicate title, or other warning still blocks.
    """
    warnings = artifact['result']['meta']['warnings']
    if len(warnings) != 1 or warnings[0].get('code') != 'SOURCE_LIST_MISMATCH' \
            or warnings[0].get('field') != 'problems':
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'ojuz'}:
        return False
    qoj, ojuz = sources['qoj'], sources['ojuz']
    qoj_tasks, ojuz_tasks = qoj.get('problems') or [], ojuz.get('problems') or []
    if (not qoj_tasks or not ojuz_tasks or len(ojuz_tasks) >= len(qoj_tasks)
            or qoj.get('problemCount') != len(qoj_tasks)
            or ojuz.get('problemCount') != len(ojuz_tasks)
            or artifact['raw'].get('link.qoj') != qoj.get('url')
            or artifact['raw'].get('link.ojuz') != ojuz.get('url')):
        return False
    names = [title_key(item.get('name')) for item in qoj_tasks]
    if not all(names) or len(set(names)) != len(names):
        return False
    if any(title_key(item.get('name')) not in names for item in ojuz_tasks):
        return reviewed_ceoi_2013_variant(artifact)
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    return all(task.get('key') in statements for task in qoj_tasks)


def reviewed_ceoi_2013_variant(artifact):
    """The oj.uz Treasure mirror explicitly uses a different grader."""
    raw = artifact['raw']
    if (artifact['row'] != 592 or artifact.get('requestKey') != request_for(raw).request_key
            or raw.get('category') != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
            or raw.get('year') != '2013' or raw.get('contest_label') != 'Day 1'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/2422'
            or raw.get('link.ojuz') != 'https://oj.uz/problems/source/ceoi2013day1'
            or raw.get('link.editorial') != 'https://ceoi2013.hsin.hr/tasks/tasks_and_solutions.pdf'):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'ojuz'}:
        return False
    qoj, ojuz = sources['qoj'], sources['ojuz']
    qoj_tasks, ojuz_tasks = qoj.get('problems') or [], ojuz.get('problems') or []
    if (qoj.get('url') != raw['link.qoj'] or ojuz.get('url') != raw['link.ojuz']
            or [(item['index'], item['name'], item['url']) for item in qoj_tasks] != [
                ('A', 'Treasure', 'https://qoj.ac/problem/13445'),
                ('B', 'Tram', 'https://qoj.ac/problem/13446'),
                ('C', 'Splot', 'https://qoj.ac/problem/13447')]
            or [(item['name'], item['url']) for item in ojuz_tasks] != [
                ('Treasure (different grader from official contest)',
                 'https://oj.uz/problem/view/CEOI13_treasure2'),
                ('Tram', 'https://oj.uz/problem/view/CEOI13_tram')]):
        return False
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    return all(task.get('key') in statements for task in qoj_tasks)


def choose_reviewed_ceoi_2013_variant(draft, artifact):
    if not reviewed_ceoi_2013_variant(artifact):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or review[0]['source'] != 'ojuz'
            or review[0]['url'] != 'https://oj.uz/problem/view/CEOI13_treasure2'
            or review[0]['title'] != 'Treasure (different grader from official contest)'):
        return False
    review[0]['choice'] = 'ignore'
    return True


def choose_reviewed_ceoi_2014_variant(draft, artifact):
    """Do not attach the oj.uz Question entry with a different grader."""
    if artifact['row'] != 590 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
            or raw.get('year') != '2014' or raw.get('contest_label') != 'Day 1'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/2413'
            or raw.get('link.ojuz') != 'https://oj.uz/problems/source/ceoi2014day1'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'ojuz'}:
        return False
    qoj = sources['qoj'].get('problems') or []
    ojuz = sources['ojuz'].get('problems') or []
    if ([(item['index'], item['name'], item['url']) for item in qoj] != [
            ('A', 'Carnival', 'https://qoj.ac/problem/13611'),
            ('B', 'The Forest of Fangorn', 'https://qoj.ac/problem/13612'),
            ('C', 'Question', 'https://qoj.ac/problem/13613')]
            or [(item['name'], item['url']) for item in ojuz] != [
            ('Carnival', 'https://oj.uz/problem/view/CEOI14_carnival'),
            ('The Forest of Fangorn', 'https://oj.uz/problem/view/CEOI14_fangorn'),
            ('Question (Grader is different from the original contest)',
             'https://oj.uz/problem/view/CEOI14_question_grader')]):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or review[0]['source'] != 'ojuz'
            or review[0]['url'] != ojuz[2]['url']
            or review[0]['title'] != ojuz[2]['name']):
        return False
    review[0]['choice'] = 'ignore'
    return True


def reviewed_standings_replacement(artifact):
    """Use the live NERC archive page for one broken Southern Russia URL."""
    raw = artifact['raw']
    if (artifact['row'] == 327
            and raw.get('category') == 'ICPC > Regionals > Northern Eurasia > Regionals > Southern Russia'
            and raw.get('year') == '2010' and not raw.get('contest_label')
            and raw.get('link.cf') == 'https://codeforces.com/gym/101246'
            and raw.get('link.standings') == 'https://contest.sgu.ru/history/acm-icpc/standings2010.html'
            and artifact.get('requestKey') == request_for(raw).request_key
            and artifact['result']['meta']['warnings'] == [{
                'code': 'RESOURCE_UNAVAILABLE', 'field': 'standings',
                'message': 'Resource returned HTTP 404.'}]):
        return 'https://nerc.icpc.global/archive/2010/southern/standings.html'
    return None


def existing_contest(catalog, artifact):
    links = artifact['result']['data']['links']
    return [contest for contest in catalog['contests']
            if any(links.get(source) and contest['link'].get(source) == links[source]
                   for source in ('qoj', 'cf', 'atcoder', 'ojuz'))]


def reviewed_existing_world_final_2023(catalog, artifact):
    """Recognize the already published manual row without creating a duplicate."""
    if artifact['row'] != 3 or not artifact.get('result'):
        return None
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > World Finals' or raw.get('year') != '2023'
            or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1662'
            or raw.get('link.cf') != 'https://codeforces.com/gym/105255'
            or raw.get('link.statement') !=
               'https://icpc.global/worldfinals/problems/2023-ICPC-World-Finals/icpc2023.pdf'
            or raw.get('link.editorial') !=
               'https://icpc.global/worldfinals/problems/2023-ICPC-World-Finals/finals2023solutions.pdf'
            or raw.get('link.standings') !=
               'https://icpc.global/worldfinals/scoreboard/2023/scoreboards/47/index.html'
            or artifact.get('requestKey') != request_for(raw).request_key
            or artifact['status'] != 'complete'
            or artifact['result']['meta']['warnings']):
        return None
    matches = existing_contest(catalog, artifact)
    if len(matches) != 1:
        return None
    contest = matches[0]
    if (contest['id'] != '624c6083-9d05-4555-9e59-d9c6f264e77b'
            or contest['title'] != 'The 2023 ICPC World Finals Luxor'
            or contest['year'] != '2023'
            or contest['category'] != ['ICPC', 'World Finals']
            or any(contest['link'].get(key) != raw['link.' + key]
                   for key in ('qoj', 'cf', 'official', 'standings'))):
        return None
    materials = {(item['role'], item['url']) for item in contest.get('materials') or []
                 if item.get('archiveId')}
    if materials != {('statement', raw['link.statement']),
                     ('editorial', raw['link.editorial'])}:
        return None
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return None
    qoj, cf = sources['qoj']['problems'], sources['cf']['problems']
    members = contest.get('problems') or []
    by_id = {problem['id']: problem for problem in catalog['problems']}
    if (len(qoj) != len(cf) or len(qoj) != len(members) or len(qoj) != 11
            or [item['index'] for item in qoj] != list('ABCDEFGHIJK')
            or [item['index'] for item in cf] != list('ABCDEFGHIJK')):
        return None
    for original, mirror, member in zip(qoj, cf, members):
        problem = by_id.get(member['problemId'])
        if (not problem or member['index'] != original['index']
                or reviewed_title_key(original['name']) != reviewed_title_key(mirror['name'])
                or problem['link'].get('qoj') != original['url']
                or problem['link'].get('cf') != mirror['url']):
            return None
    return contest


def contest_id(manifest, index):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                           f"ps-checklist:raw:{manifest.get('batchId', manifest['sourceSha256'])}:{index}"))


def attach_verified_usaco(draft, artifact, official):
    """Attach exact CSV editorials and official statements to final problem IDs."""
    ordered = draft.get('orderedMaterials') or {}
    editorials = [item['editorial'] for item in official]
    if set(ordered) != {'editorial'} or ordered['editorial'] != editorials:
        raise StorageError('Official USACO documents differ from ordered CSV editorials.')
    refs = qoj_refs(artifact)
    members = draft['contest'].get('problems') or []
    if len(members) != len(refs) or len({item['problemId'] for item in members}) != len(refs):
        raise StorageError('Official USACO problem order differs from the final contest.')
    by_url = {problem['link']['qoj']: problem['id'] for problem in draft['problems']
              if problem['link'].get('qoj')}
    if any(ref['url'] not in by_url for ref in refs) or [item['problemId'] for item in members] != [
            by_url.get(ref['url']) for ref in refs]:
        raise StorageError('Official USACO problems do not match final QOJ problem IDs.')
    materials = list(draft['contest'].get('problemMaterials') or [])
    rules = draft['refresh']['contest']
    provenance = rules.setdefault('problemMaterialSources', {})
    manual = set(rules.get('manual', []))
    for ref, item in zip(refs, official):
        pid = by_url[ref['url']]
        for role in ('statement', 'editorial'):
            key = f'problemMaterials.{pid}.{role}'
            prior = next((entry for entry in materials
                          if entry['problemId'] == pid and entry['role'] == role), None)
            # A real QOJ statement has higher priority. A QOJ problem-page URL
            # is only a fallback, so replace that with the official statement.
            if role == 'statement' and prior and prior['url'] != ref['url']:
                continue
            selected = {'problemId': pid, 'role': role,
                        'title': 'Problem statement' if role == 'statement' else 'Editorial',
                        'language': None, 'url': item[role]}
            if prior:
                prior.update(selected)
            else:
                materials.append(selected)
            if role == 'editorial':
                manual.add(key)
                provenance.pop(key, None)
            else:
                provenance[key] = {'source': 'official', 'url': item[role]}
    draft['contest']['problemMaterials'] = materials
    rules['manual'] = sorted(manual)
    del draft['orderedMaterials']


def attach_verified_filenames(draft, artifact, ordered, *, source='qoj', refs=None):
    """Attach reviewed raw documents to their final native problem IDs."""
    if draft.get('orderedMaterials') != ordered:
        raise StorageError('Verified filenames differ from the ordered CSV documents.')
    refs = qoj_refs(artifact) if refs is None else refs
    members = draft['contest'].get('problems') or []
    by_url = {problem['link'][source]: problem['id'] for problem in draft['problems']
              if problem['link'].get(source)}
    if (len(members) != len(refs) or len({item['problemId'] for item in members}) != len(refs)
            or [item['problemId'] for item in members] != [by_url.get(ref['url']) for ref in refs]):
        raise StorageError('Verified document order differs from the final contest.')
    materials = list(draft['contest'].get('problemMaterials') or [])
    rules = draft['refresh']['contest']
    manual = set(rules.get('manual', []))
    provenance = rules.setdefault('problemMaterialSources', {})
    for position, ref in enumerate(refs):
        pid = by_url[ref['url']]
        for role, urls in ordered.items():
            key = f'problemMaterials.{pid}.{role}'
            selected = {'problemId': pid, 'role': role,
                        'title': 'Problem statement' if role == 'statement' else 'Editorial',
                        'language': None, 'url': urls[position]}
            prior = next((item for item in materials
                          if item['problemId'] == pid and item['role'] == role), None)
            if prior:
                prior.update(selected)
            else:
                materials.append(selected)
            manual.add(key)
            provenance.pop(key, None)
    draft['contest']['problemMaterials'] = materials
    rules['manual'] = sorted(manual)
    del draft['orderedMaterials']


def attach_reviewed_qoj_statement(draft, proof):
    """Replace one forbidden QOJ statement with its checked document."""
    qoj_url = proof['missing'][2]
    matches = [problem['id'] for problem in draft['problems']
               if problem['link'].get('qoj') == qoj_url]
    if len(matches) != 1:
        raise StorageError('The reviewed QOJ task is missing from the draft.')
    problem_id = matches[0]
    materials = draft['contest'].get('problemMaterials') or []
    entries = [item for item in materials
               if item['problemId'] == problem_id and item['role'] == 'statement']
    if len(entries) != 1:
        raise StorageError('The reviewed problem statement is missing from the draft.')
    if proof.get('label'):
        if entries[0]['url'] != proof['statement']:
            raise StorageError('The official IOI statement differs from the reviewed task.')
        return
    entries[0].update({'url': proof['statement'], 'title': 'Problem statement',
                       'language': 'en'})
    key = f'problemMaterials.{problem_id}.statement'
    rules = draft['refresh']['contest']
    rules['manual'] = sorted(set(rules.get('manual', [])) | {key})
    rules.setdefault('problemMaterialSources', {}).pop(key, None)


def prepare(artifact, catalog, manifest, allow_warnings):
    qoj_fallback = reviewed_qoj_fallback(artifact)
    if artifact['status'] in ('error', 'deferred'):
        raise StorageError('The source fetch failed or was rate limited.')
    if artifact.get('qojMaterialsPending') and not qoj_fallback:
        raise StorageError('QOJ problem materials are still queued for enrichment.')
    discovery = artifact['result']
    required_archives = required_attachment_urls(artifact)
    standings_replacement = reviewed_standings_replacement(artifact)
    if (discovery['meta']['warnings'] and not allow_warnings
            and required_archives is None
            and not covered_cf_material_warnings(artifact)
            and not covered_moscow_2016_subset(artifact)
            and not covered_ojuz_list_warning(artifact)
            and not standings_replacement
            and not qoj_fallback
            and not reviewed_legacy_joisc(artifact)):
        raise StorageError('Source warnings need review before publication.')
    if not discovery['data']['sources']:
        raise StorageError('No judge returned a contest or problem list.')
    if existing_contest(catalog, artifact):
        raise StorageError('A judge link already belongs to a catalog contest; review before reusing it.')
    draft = make_draft(discovery, catalog)
    recent_joi = verified_recent_joi(artifact)
    reviewed_ioi = verified_ioi_order(artifact)
    reviewed_joisc = verified_joisc_order(artifact)
    reviewed_ceoi = verified_ceoi_order(artifact)
    if draft.get('problemMerge', {}).get('review'):
        if not ((recent_joi and choose_reviewed_joi_matches(draft, artifact, recent_joi[1]))
                or (reviewed_ioi and choose_reviewed_ioi_match(draft, artifact, reviewed_ioi[1]))
                or (reviewed_joisc and choose_reviewed_joisc_match(draft, artifact, reviewed_joisc[1]))
                or choose_reviewed_joisc_translation(draft, artifact, reviewed_joisc)
                or (reviewed_ceoi and choose_reviewed_ceoi_match(draft, artifact, reviewed_ceoi[1]))
                or choose_reviewed_ceoi_2013_variant(draft, artifact)
                or choose_reviewed_ceoi_2014_variant(draft, artifact)
                or choose_reviewed_apio_match(draft, artifact)
                or choose_reviewed_swerc_extras(draft, artifact)
                or choose_reviewed_boi_2019_match(draft, artifact)
                or choose_reviewed_world_final_matches(draft, artifact)
                or choose_reviewed_world_final_2022_shared(draft, artifact)
                or choose_reviewed_asia_east_2017_match(draft, artifact)
                or choose_reviewed_attachment_matches(draft, artifact)
                or choose_reviewed_problem_match(draft, artifact)):
            raise StorageError('Problem correspondences need review.')
    draft = resolve_choices(draft, require_all=True)
    official = verified_official(artifact) or verified_usaco_exception(artifact)
    reviewed_order = (verified_koi_order(artifact) or verified_ktst_order(artifact)
                      or reviewed_joisc or verified_joi_open_order(artifact)
                      or verified_jakarta_order(artifact)
                      or verified_swerc_order(artifact)
                      or verified_cerc_order(artifact)
                      or reviewed_ceoi or verified_apio_order(artifact)
                      or verified_order(artifact))
    if official:
        attach_verified_usaco(draft, artifact, official)
    elif reviewed_order:
        source, refs, ordered = reviewed_order
        attach_verified_filenames(draft, artifact, ordered, source=source, refs=refs)
    elif draft.get('orderedMaterials'):
        ordered = verified_filename_order(artifact)
        if not ordered:
            raise StorageError('Ordered CSV problem documents need an order check.')
        attach_verified_filenames(draft, artifact, ordered)
    if qoj_fallback:
        attach_reviewed_qoj_statement(draft, qoj_fallback)
    contest = draft['contest']
    if standings_replacement:
        contest['link']['standings'] = standings_replacement
    if not contest.get('problems'):
        raise StorageError('No complete problem list was discovered.')
    # Judges sometimes advertise an HTTP event homepage. The catalog permits
    # HTTPS only; omit that uncurated suggestion instead of guessing a redirect.
    for field in ('official', 'standings'):
        value = contest['link'].get(field)
        if value and not value.startswith('https://'):
            contest['link'][field] = None
    contest['id'] = contest_id(manifest, artifact['row'])
    reviewed_pdf = reviewed_cf_attachment(artifact)
    selected_contest_materials(draft, artifact['raw'],
                               (reviewed_pdf['attachment'] if reviewed_pdf else
                                qoj_fallback.get('contestStatement') if qoj_fallback else None))
    binus_editorial = reviewed_binus_editorial(artifact)
    if binus_editorial:
        original, mirror = binus_editorial
        editorial = [item for item in contest['materials']
                     if item.get('role') == 'editorial' and item.get('url') == original]
        if len(editorial) != 1:
            raise StorageError('The reviewed BINUS editorial was not selected.')
        editorial[0]['url'] = mirror
    if required_archives and not required_archives.issubset(
            material_url(item['url']) for item in contest['materials']):
        raise StorageError('The reviewed attachment was not selected for archiving.')
    ids = {item['problemId'] for item in contest['problems']}
    problems = [problem for problem in draft['problems'] if problem['id'] in ids]
    body = {'contest': contest, 'problems': problems, 'versions': draft['versions'],
            'refresh': draft.get('refresh')}
    validate_form(body)
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='write eligible rows to the local catalog')
    parser.add_argument('--allow-warnings', action='store_true', help='include rows with source warnings')
    parser.add_argument('--csv', type=Path, default=ROOT / 'raw/contests.csv')
    parser.add_argument('--fetched', type=Path, default=ROOT / 'storage/output/raw-fetch')
    parser.add_argument('--receipts', type=Path, default=ROOT / 'storage/output/raw-publish')
    parser.add_argument('--row', type=int, action='append', help='process only this CSV row (repeatable)')
    args = parser.parse_args()
    publication_lock = None
    if args.publish:
        args.receipts.mkdir(parents=True, exist_ok=True)
        publication_lock = (args.receipts / '.publish.lock').open('a+')
        try:
            fcntl.flock(publication_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another raw publication is already running.') from None
    manifest, artifacts = load_batch(args.csv, args.fetched)
    if args.row and any(index < 1 or index > len(artifacts) for index in args.row):
        parser.error('--row must refer to an existing CSV row')
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    archive = ArchiveStore(app.config) if args.publish else None
    counts = {'published': 0, 'existing': 0, 'blocked': 0, 'ready': 0}
    for artifact in artifacts:
        index = artifact['row']
        if args.row and index not in args.row:
            continue
        receipt_path = args.receipts / 'rows' / f'{index:04d}.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if receipt and receipt.get('status') == 'existing':
            existing = reviewed_existing_world_final_2023(catalog, artifact)
            if (not existing or receipt.get('requestKey') != artifact['requestKey']
                    or receipt.get('contestId') != existing['id']):
                raise RuntimeError(f'Existing row {index} differs from its catalog contest.')
            counts['existing'] += 1
            continue
        if receipt and receipt.get('status') == 'published':
            if receipt.get('requestKey') != artifact['requestKey']:
                raise RuntimeError(f'Published row {index} has a different request key.')
            if receipt['contestId'] not in {contest['id'] for contest in catalog['contests']}:
                raise RuntimeError(f'Published row {index} is missing from the catalog.')
            counts['existing'] += 1
            continue
        rpc_attempted = False
        try:
            matches = existing_contest(catalog, artifact) if artifact.get('result') else []
            expected_id = contest_id(manifest, index)
            existing = reviewed_existing_world_final_2023(catalog, artifact)
            if existing:
                if args.publish:
                    atomic_json(receipt_path, {'row': index,
                        'requestKey': artifact['requestKey'], 'status': 'existing',
                        'contestId': existing['id'], 'reconciled': True})
                counts['existing'] += 1
                continue
            if matches and len(matches) == 1 and matches[0]['id'] == expected_id:
                if args.publish:
                    atomic_json(receipt_path, {'row': index, 'requestKey': artifact['requestKey'],
                        'status': 'published', 'contestId': expected_id, 'reconciled': True})
                counts['existing'] += 1
                continue
            body = prepare(artifact, catalog, manifest, args.allow_warnings)
            if not args.publish:
                counts['ready'] += 1
                continue
            ensure_archive_space(archive)
            prepared, files, skipped = archive.prepare(body['contest'])
            qoj_fallback = reviewed_qoj_fallback(artifact)
            if qoj_fallback and not all(any(
                    file['sourceUrl'] == url and file['sha256'] == digest
                    for file in files) for url, digest in qoj_fallback['archive'].items()):
                raise StorageError('A reviewed QOJ replacement differs from its checked PDF or ZIP.')
            binus_editorial = reviewed_binus_editorial(artifact)
            if binus_editorial and not any(
                    file['sourceUrl'] == binus_editorial[1]
                    and file['sha256'] == BINUS_2022_EDITORIAL_SHA256 for file in files):
                raise StorageError('The BINUS editorial mirror differs from the reviewed PDF.')
            required_archives = required_attachment_urls(artifact)
            if required_archives and not required_archives.issubset(file['sourceUrl'] for file in files):
                raise StorageError('The reviewed attachment could not be archived.')
            legacy_joisc = reviewed_legacy_joisc(artifact)
            if legacy_joisc and not any(file['sourceUrl'] == legacy_joisc[0]
                                       and file['sha256'] == legacy_joisc[1]
                                       for file in files):
                raise StorageError('The JOISC day statement differs from the organizer-checked PDF.')
            reviewed_pdf = reviewed_cf_attachment(artifact)
            if reviewed_pdf and not any(file['sourceUrl'] == reviewed_pdf['attachment']
                                        and file['sha256'] == reviewed_pdf['attachmentSha256']
                                        and file['size'] == reviewed_pdf['bytes'] for file in files):
                raise StorageError('The Codeforces statement attachment differs from the reviewed copy.')
            rpc_attempted = True
            published = app.rpc('catalog', 'admin_publish_archived',
                {'p_contest': prepared, 'p_problems': body['problems'],
                 'p_versions': body['versions'], 'p_refresh': body['refresh'],
                 'p_archives': files}, privileged=True)
            catalog = published
            atomic_json(receipt_path, {'row': index, 'requestKey': artifact['requestKey'],
                'status': 'published', 'contestId': prepared['id'],
                'archivedFiles': len(files), 'sourceOnlyLinks': len(skipped)})
            counts['published'] += 1
        except (StorageError, ValueError, KeyError, TypeError) as error:
            if args.publish and rpc_attempted and isinstance(error, StorageError):
                # A timed-out RPC might have committed even if its response was
                # lost. Refresh before preparing the next row.
                catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
                if any(contest['id'] == contest_id(manifest, index) for contest in catalog['contests']):
                    atomic_json(receipt_path, {'row': index, 'requestKey': artifact['requestKey'],
                        'status': 'published', 'contestId': contest_id(manifest, index),
                        'reconciled': True})
                    counts['existing'] += 1
                    continue
            counts['blocked'] += 1
            if args.publish:
                atomic_json(receipt_path, {'row': index, 'requestKey': artifact['requestKey'],
                    'status': 'blocked', 'reason': str(error)})
            print(f'row {index}: blocked: {error}', flush=True)
        if index % 20 == 0:
            print(f'row {index}/{len(artifacts)}: {counts}', flush=True)
    print(counts, flush=True)
    if publication_lock:
        publication_lock.close()


if __name__ == '__main__':
    main()
