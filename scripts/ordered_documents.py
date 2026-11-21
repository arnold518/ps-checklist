"""Verify raw per-problem PDF order from distinct names in the file URLs."""

import json
from pathlib import PurePosixPath
import re
import unicodedata
from urllib.parse import unquote, urlsplit


def title_pattern(title):
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().casefold()
    words = re.findall(r'[a-z0-9]+', ascii_title)
    if len(''.join(words)) < 4:
        return None
    return re.compile(r'(?<![a-z0-9])' + r'[^a-z0-9]*'.join(map(re.escape, words))
                      + r'(?![a-z0-9])')


def verified_filename_order(artifact):
    """Return ordered URLs only if each basename names exactly its QOJ problem."""
    if not artifact.get('result'):
        return None
    sources = artifact['result']['data']['sources']
    refs = [problem for source in sources if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]
    if not refs or len({ref['url'] for ref in refs}) != len(refs):
        return None
    patterns = [title_pattern(ref['name']) for ref in refs]
    if any(pattern is None for pattern in patterns):
        return None
    raw = artifact['raw']
    curation = artifact['result']['data'].get('curation') or {}
    ordered = {}
    for role in ('statement', 'editorial'):
        value = raw.get(f'link.{role}_per_problem')
        if not value:
            continue
        try:
            urls = json.loads(value)
        except (TypeError, ValueError):
            return None
        if (not isinstance(urls, list) or not all(isinstance(url, str) for url in urls)
                or len(urls) != len(refs)
                or len(set(urls)) != len(urls)
                or curation.get(role + 'PerProblem') != urls):
            return None
        for index, url in enumerate(urls):
            parts = urlsplit(url)
            if parts.scheme != 'https' or not parts.hostname or not parts.path.lower().endswith('.pdf'):
                return None
            stem = unquote(PurePosixPath(parts.path).stem).casefold()
            if [position for position, pattern in enumerate(patterns) if pattern.search(stem)] != [index]:
                return None
        ordered[role] = urls
    return ordered or None
