"""Exact evidence for six QOJ problem pages that return HTTP 403.

Each replacement is a checked statement, not an assertion that the QOJ page
was fetched. PDF hashes are checked again after the selected files are archived.
"""

import hashlib
import json

from scripts.fetch_raw_contests import request_for


PROOFS = {
    19: {
        'year': '2025', 'category': 'ICPC > Regionals > Asia Pacific > Asia Pacific Championship',
        'qoj': 'https://qoj.ac/contest/2527', 'cf': 'https://codeforces.com/contest/2073',
        'tasksSha256': '0911ba85c76cdfe6c404c8577ec2923d2d7ed7087f8f274943118bafb02bff46',
        'missing': ('H', 'Secret Lilies and Roses', 'https://qoj.ac/problem/14333'),
        'statement': 'https://storage.googleapis.com/files.icpc.jp/championship2025/problemset.pdf#page=15',
        'contestStatement': 'https://storage.googleapis.com/files.icpc.jp/championship2025/problemset.pdf',
        'archive': {
            'https://storage.googleapis.com/files.icpc.jp/championship2025/problemset.pdf': 'e697a780dbc8f9fd78a12ec3d02fa9e14e89070fca67d502e290966c8f81b25b',
            'https://storage.googleapis.com/files.icpc.jp/championship2025/problemset.pdf#page=15': 'e697a780dbc8f9fd78a12ec3d02fa9e14e89070fca67d502e290966c8f81b25b',
        },
    },
    20: {
        'year': '2024', 'category': 'ICPC > Regionals > Asia Pacific > Asia Pacific Championship',
        'qoj': 'https://qoj.ac/contest/1886', 'cf': 'https://codeforces.com/contest/1938',
        'tasksSha256': 'cea1a60555349dc4805b22a2ca8f620d8d2c645d5ca79599aeb1f4f64c658e89',
        'missing': ('I', 'Symmetric Boundary', 'https://qoj.ac/problem/10161'),
        'statement': 'https://storage.googleapis.com/files.icpc.jp/championship2024/tasks.pdf#page=17',
        'contestStatement': 'https://storage.googleapis.com/files.icpc.jp/championship2024/tasks.pdf',
        'archive': {
            'https://storage.googleapis.com/files.icpc.jp/championship2024/tasks.pdf': '85252a6a3fd1cf7cfeb4b326b767b7dc84641ffeef5cb019079fa4711f6974c1',
            'https://storage.googleapis.com/files.icpc.jp/championship2024/tasks.pdf#page=17': '85252a6a3fd1cf7cfeb4b326b767b7dc84641ffeef5cb019079fa4711f6974c1',
        },
    },
    58: {
        'year': '2025', 'category': 'ICPC > Regionals > Asia Pacific > Regionals > Indonesia (Jakarta)',
        'qoj': 'https://qoj.ac/contest/2755', 'cf': '',
        'tasksSha256': 'b813cffc4dc7f7a913ca3ada9bec3c52a3512fd19343c04ada33b83e4fd510c6',
        'missing': ('B', 'Burning Blocks', 'https://qoj.ac/problem/15785'),
        'statement': 'https://raw.githubusercontent.com/prabowo02/icpc-jakarta-2025/master/icpc-block/description.pdf',
        'contestStatement': 'https://qoj.ac/download.php?id=2755&r=0&type=attachments',
        'archive': {
            'https://qoj.ac/download.php?id=2755&r=0&type=attachments': '4635e170a4b747bdd450f605b5b3b156716334b919669acbb01ebc5891a137f8',
            'https://raw.githubusercontent.com/prabowo02/icpc-jakarta-2025/master/icpc-block/description.pdf': 'acaaa9ff002fe3478b361e7a9e4fa2a27bfbc35c3d60baacc76f7b8e511809ad',
        },
    },
    72: {
        'year': '2025', 'category': 'ICPC > Regionals > Asia Pacific > Regionals > Taiwan',
        'qoj': 'https://qoj.ac/contest/2657', 'cf': 'https://codeforces.com/contest/2172',
        'tasksSha256': '0131e57526ca9b1e870031c8d205ad9317237241bbe5108c9c10f9c2ad7ab839',
        'missing': ('G', 'Gene Editor', 'https://qoj.ac/problem/15399'),
        'statement': 'https://codeforces.com/contest/2172/attachments/download/34304/main.pdf#page=17',
        'contestStatement': 'https://codeforces.com/contest/2172/attachments/download/34304/main.pdf',
        'archive': {
            'https://codeforces.com/contest/2172/attachments/download/34304/main.pdf': '8ec435f86c3d17d14d1737bdb909b0573c80f40f59a1da4c50378c6fba62fa35',
            'https://codeforces.com/contest/2172/attachments/download/34304/main.pdf#page=17': '8ec435f86c3d17d14d1737bdb909b0573c80f40f59a1da4c50378c6fba62fa35',
        },
    },
    384: {
        'year': '2006', 'category': 'Olympiad > International Olympiad in Informatics (IOI)',
        'label': 'Day 2', 'qoj': 'https://qoj.ac/contest/2314', 'cf': '',
        'tasksSha256': '0dba60464145f7db1f4d866e74f7b280fadb2c39d7d172231d5ef84fe01f581b',
        'missing': ('C', 'A Black Box Game', 'https://qoj.ac/problem/13078'),
        'statement': 'https://ioinformatics.org/files/ioi2006problem4.pdf',
        'archive': {
            'https://ioinformatics.org/files/ioi2006problem5.pdf': '97b7aae38dc7386b12281e7beb3fb117f78972ea40bc7ea09d4e7f8c07f21f46',
            'https://ioinformatics.org/files/ioi2006problem6.pdf': '8b954c95f00babbc81180b617955f4fbbfe6dd1503ca3f118e1c6034cddb7c12',
            'https://ioinformatics.org/files/ioi2006problem4.pdf': 'ea94d1f0a891c692d9e2813aea7f1d8165f957f458578b57f1c75e8f9acbacec',
            'https://ioinformatics.org/files/ioi2006solutions.zip': 'b8f856d577f532f02d4e04658629c6ad4552e2a38c3232a530758e9d5bcefed6',
        },
    },
    392: {
        'year': '2002', 'category': 'Olympiad > International Olympiad in Informatics (IOI)',
        'label': 'Day 2', 'qoj': 'https://qoj.ac/contest/2492', 'cf': '',
        'tasksSha256': '94cf91240304d230c7294a6d1896e835f04b6e7f966fe86d10523f6987ddadab',
        'missing': ('C', 'Two Rods', 'https://qoj.ac/problem/13819'),
        'statement': 'https://ioinformatics.org/files/ioi2002problem6.pdf',
        'archive': {
            'https://ioinformatics.org/files/ioi2002problem4.pdf': '719e06de761f59e2cddcff5f940e3635b10bf9a7630e6185cbdc026e79a9247b',
            'https://ioinformatics.org/files/ioi2002problem5.pdf': '3d45548d38449998b958d0d008b8e82aa819dc8933b66e38c67169377beac326',
            'https://ioinformatics.org/files/ioi2002problem6.pdf': '6da2ee3d980bcc923188c4110af92deb3aabb30c179ac3fe5d4b669a7deb3cb3',
            'https://ioinformatics.org/files/ioi2002solutions.zip': 'abf3d615f6fec89fae4e07c8ed059f28bc1d344d57284ac8c9e300e41d308249',
        },
    },
}


def reviewed(artifact):
    proof = PROOFS.get(artifact.get('row'))
    if not proof or not artifact.get('result'):
        return None
    raw = artifact['raw']
    if (artifact.get('qojFallback') != proof['missing'][2]
            or artifact.get('requestKey') != request_for(raw).request_key
            or raw.get('year') != proof['year'] or raw.get('category') != proof['category']
            or raw.get('contest_label', '') != proof.get('label', '')
            or raw.get('link.qoj') != proof['qoj']
            or (raw.get('link.cf') or '') != proof['cf']):
        return None
    allowed_warnings = {('PROBLEM_MATERIALS_INCOMPLETE', 'qoj'),
                        ('PROBLEM_MATERIALS_UNAVAILABLE', 'qoj')}
    if artifact['row'] in (19, 20, 72):
        allowed_warnings.add(('PROBLEM_MATERIALS_INCOMPLETE', 'cf'))
    if artifact['row'] in (384, 392):
        allowed_warnings.update({('RATE_LIMITED', 'qoj'),
                                 ('UNSUPPORTED_RESOURCE', 'editorial')})
    if any((item.get('code'), item.get('field')) not in allowed_warnings
           for item in artifact['result']['meta']['warnings']):
        return None
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != ({'qoj', 'cf'} if proof['cf'] else {'qoj'}):
        return None
    qoj = sources['qoj']
    tasks = qoj.get('problems') or []
    digest_input = [{'index': task['index'], 'name': task['name'], 'url': task['url']}
                    for task in tasks]
    digest = hashlib.sha256(json.dumps(digest_input, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (qoj.get('url') != proof['qoj'] or qoj.get('problemCount') != len(tasks)
            or digest != proof['tasksSha256']
            or sum((task['index'], task['name'], task['url']) == proof['missing']
                   for task in tasks) != 1):
        return None
    if proof['cf']:
        cf = sources['cf']
        if (cf.get('url') != proof['cf'] or cf.get('problemCount') != len(tasks)
                or len(cf.get('problems') or []) != len(tasks)
                or any(a['index'] != b['index'] or a['name'] != b['name']
                       for a, b in zip(tasks, cf['problems']))):
            return None
    statement = proof.get('contestStatement')
    if statement:
        if (artifact['row'] in (19, 20) and raw.get('link.statement') != statement):
            return None
        if not any(item.get('role') == 'statement' and item.get('scope') == 'contest'
                   and item.get('url') == statement for source in sources.values()
                   for item in source.get('materials') or []) and artifact['row'] not in (19, 20):
            return None
    if artifact['row'] in (384, 392):
        statements = [url for url in proof['archive'] if url.endswith('.pdf')]
        if (json.loads(raw.get('link.statement_per_problem') or 'null') != statements
                or raw.get('link.editorial') not in proof['archive']):
            return None
    return proof
