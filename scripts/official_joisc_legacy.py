"""Organizer-checked day boundaries for the old year-wide AtCoder JOISC sets."""

from scripts.fetch_raw_contests import request_for


CATEGORY = 'Olympiad > Japan > Japanese Olympiad in Informatics Spring Camp (JOISC)'
FIRST_ROW = {2011: 546, 2010: 547, 2009: 548, 2008: 549, 2007: 550}
PDFS = {
    2011: ('2011-sp-day1.pdf', '2011-sp-day2.pdf', '2011-sp-day3.pdf', '2011-sp-day4.pdf'),
    2010: ('2010-sp-day1_20.pdf', '2010-sp-day2_21.pdf', '2010-sp-day3_22.pdf', '2010-sp-day4_23.pdf'),
    2009: ('2009-sp_tr-day1_20.pdf', '2009-sp_tr-day2_21.pdf', '2009-sp_tr-day3_22.pdf', '2009-sp_tr-day4_23.pdf'),
    2008: ('2008-sp_tr-day1_20.pdf', '2008-sp_tr-day2_21.pdf', '2008-sp_tr-day3_22.pdf', '2008-sp_tr-day4_24.pdf'),
    2007: ('2007-sp-day1_20.pdf', '2007-sp-day2_21.pdf', '2007-sp-day3_23.pdf', '2007-sp-day4_24.pdf'),
}
PDF_SHA256 = {
    2011: ('f38cdb995ff1b9b68a05cafe7edbe26153fa06650d77ed45e6a97380aa32e525',
           'b2dc3386a23e058133e12a8f523dccfd8e9f44de599239b5571a59395eba374a',
           '20b0e057b22679e5010aa3473442c4076515a13fb3c2843ece666a0758af5c15',
           '867c0b3d3fb8e8d0d9a189973c69ef5945e29ba9801b28dbffc6810a444c47ed'),
    2010: ('2ae015672389279156bfe8545a0eb24253875e2da39f9f1c7ce953d92e3f86a1',
           '2a98f1bf555ee82887bc30c558c47801e1d28432199de502611ae29d40eb4edd',
           '84ef6462e2489be29c0a25e8dd12ea07d5ae97d80758506febf84d5c1435d2b6',
           '16748d341b2664f41bcb55be16fd126728dd600bde7b268514a6a476a4ebc9ca'),
    2009: ('04b67b1bcc0b1aeafd9434d4cf81e795938d1666f20254aff46c39d52b16c828',
           '37a4904c60dffc31a1da0867e8fd615cc2894d1c3d51588e113d5721aeb84588',
           'a3db3fbcd5a3c74ea2f7a07034edb565eb050c2f2923a9ceba2eb39aa560ce40',
           'c4745b814aa83d66ab78e68646da23457c1b5588044a76539beb64cba7d22870'),
    2008: ('d47b9192ea30a99a49537d656ff4f0c9b4270bef10b0ee5653cfc4603d962d96',
           '5dcf3c63c2fbffe59a07113063069b88c06663889cf38a1974ef96c7ae119b7a',
           '5d89928203b81fc628c53c0a0e57ccae1a89cc5a3787e9aa3e8f7e2642141475',
           '3357e0d359bad6fb42dfe528200ed775eff6d89c75a32e8a36fefb9f675ba47a'),
    2007: ('d33b5816d3978e270373cff76b75da18e5760d486bbf184fdb6dd8e8bd9dd03c',
           '8d8a39d45c9406ab7280c87260291a2b8cdd66864da0d880ea15a1e5c8e6ebe8',
           '206cce0e12b77e5965609717144d6ce555674514dc24fc89d46e36818ffc16ef',
           'b6f0420583810a211a270abc0b243cd1930630e82b8f3bbe7f169eafab9a7aa1'),
}
TASK_POSITIONS = {
    2011: ((0, 1, 2), (3, 4, 5), (6, 7, 8), (13, 14, 15, 16)),
    2010: ((0, 1, 2), (3, 4, 5), (6, 7, 8), (13, 14, 15, 16)),
    2009: ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)),
    2008: ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)),
    2007: ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11)),
}
TASK_IDS = {
    2011: (('banner', 'dragon', 'joitter'), ('guess', 'keycards', 'shiritori'),
           ('deciphering', 'report', 'ufo1'), ('apples', 'bookshelf', 'ioi', 'orienteering')),
    2010: (('poster', 'sengoku', 'stairs'), ('aplusb', 'dna', 'regions'),
           ('finals', 'hideseek', 'simroad1'), ('contest', 'highway', 'lake', 'plugs')),
    2009: (('sequence', 'stamps', 'pyramid'), ('abduction', 'advertisement', 'contest'),
           ('territory', 'ski', 'logo'), ('distribution', 'chopsticks', 'starry_sky')),
    2008: (('committee', 'sheet', 'flu'), ('nile', 'cheating', 'belt'),
           ('origami', 'fraction', 'nightman'), ('ruins', 'typhoon', 'election1')),
    2007: (('score', 'factor', 'mall'), ('buildi', 'fermat', 'salt'),
           ('anagra', 'route', 'circui'), ('fiber', 'lines', 'packin')),
}
EXTRA_VARIANTS = {2011: ('ufo2', 'ufo3', 'ufo4', 'ufo5'),
                  2010: ('simroad2', 'simroad3', 'simroad4', 'simroad5'),
                  2008: ('election2', 'election3', 'election4', 'election5'),
                  2007: ('packing2', 'packing3', 'packing4', 'packing5')}


def pdf_url(year, day):
    return f'https://www2.ioi-jp.org/camp/{year}/{year}-sp-tasks/{PDFS[year][day - 1]}'


def source_scope(request):
    """Recognize an exact day request backed by the annual AtCoder source."""
    curation = request.curation or {}
    try:
        year = int(curation['year'])
        day = int(curation['contestLabel'].removeprefix('Day '))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    if year not in FIRST_ROW or day not in (1, 2, 3, 4):
        return None
    if (curation != {'category': CATEGORY.split(' > '), 'year': str(year),
                    'contestLabel': f'Day {day}',
                    'official': f'https://www2.ioi-jp.org/camp/{year}/{year}-sp-tasks/index.html'}
            or request.links != {'atcoder': f'https://atcoder.jp/contests/joisc{year}',
                                 'statement': pdf_url(year, day)}):
        return None
    return year, day


def scope_atcoder_source(native, year, day):
    """Keep exactly the organizer's day tasks before task-page enrichment."""
    data = native.get('data') or {}
    problems = data.get('problems') or []
    if data.get('source') != 'atcoder' or data.get('url') != f'https://atcoder.jp/contests/joisc{year}' \
            or len(problems) != (17 if year in (2010, 2011) else 16 if year in (2007, 2008) else 12):
        return False
    selected = [problems[position] for position in TASK_POSITIONS[year][day - 1]]
    if [item.get('taskId') for item in selected] != [
            f'joisc{year}_{suffix}' for suffix in TASK_IDS[year][day - 1]]:
        return False
    keys = {item['key'] for item in selected}
    data['problems'] = selected
    data['problemCount'] = len(selected)
    data['materials'] = [item for item in data.get('materials') or []
                         if item.get('scope') == 'problem'
                         and item.get('role') in ('statement', 'editorial')
                         and item.get('problemKey') in keys]
    return True


def reviewed(artifact):
    """Accept only the exact 20 curated day slices and their PDF provenance."""
    raw = artifact.get('raw') or {}
    try:
        year = int(raw['year'])
        day = int(raw['contest_label'].removeprefix('Day '))
        source = artifact['result']['data']['sources'][0]['data']
        origin = artifact['curatedFromRow']
    except (KeyError, ValueError, TypeError, IndexError):
        return None
    if year not in FIRST_ROW or day not in (1, 2, 3, 4):
        return None
    expected_row = FIRST_ROW[year] if day == 1 else 1031 + (2011 - year) * 3 + day - 2
    expected_url = pdf_url(year, day)
    data = artifact['result']['data']
    expected_curation = {'category': CATEGORY.split(' > '), 'year': str(year),
                         'contestLabel': f'Day {day}',
                         'official': f'https://www2.ioi-jp.org/camp/{year}/{year}-sp-tasks/index.html'}
    expected_warning_codes = ['PROBLEM_MATERIALS_UNAVAILABLE']
    if year != 2011:
        expected_warning_codes.append('CATEGORY_UNKNOWN')
    if (artifact['row'] != expected_row or origin != FIRST_ROW[year]
            or raw['category'] != CATEGORY or raw['contest_label'] != f'Day {day}'
            or raw['link.official'] != expected_curation['official']
            or raw['link.statement'] != expected_url
            or raw['link.atcoder'] != f'https://atcoder.jp/contests/joisc{year}'
            or any(raw['link.' + source] for source in ('qoj', 'cf', 'ojuz', 'editorial'))
            or artifact['officialStatementSha256'] != PDF_SHA256[year][day - 1]
            or artifact['requestKey'] != request_for(raw).request_key
            or source_scope(request_for(raw)) != (year, day)
            or artifact['request']['links'] != request_for(raw).links
            or artifact['status'] != 'partial'
            or [item['code'] for item in artifact['result']['meta']['warnings']] != expected_warning_codes
            or data['links'] != {'statement': expected_url}
            or data['curation'] != expected_curation
            or data['title'] != f'JOISC {year} Day {day}'
            or data['year'] != str(year)
            or len(data['sources']) != 1
            or source['source'] != 'atcoder'
            or source['url'] != f'https://atcoder.jp/contests/joisc{year}'
            or source['problemCount'] != len(TASK_POSITIONS[year][day - 1])
            or len(source['problems']) != source['problemCount']):
        return None
    if day == 4 and artifact.get('omittedAtCoderVariants') != list(EXTRA_VARIANTS.get(year, ())):
        return None
    if [item['taskId'] for item in source['problems']] != [
            f'joisc{year}_{suffix}' for suffix in TASK_IDS[year][day - 1]]:
        return None
    if any(item['url'] != f'https://atcoder.jp/contests/joisc{year}/tasks/{item["taskId"]}'
           or not item.get('name') for item in source['problems']):
        return None
    selected_keys = {item['key'] for item in source['problems']}
    if any(item.get('scope') != 'problem' or item.get('problemKey') not in selected_keys
           or item.get('role') not in ('statement', 'editorial')
           for item in source.get('materials') or []):
        return None
    return expected_url, PDF_SHA256[year][day - 1]
