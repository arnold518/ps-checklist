import json
from datetime import datetime
from getContest import ContestCrawler

def parseJsonStr(jsonstr):
    lvl = 0
    flag = False
    ret = ''
    for c in jsonstr:
        if c == '[':
            lvl += 1
            flag = True
        elif c == ']':
            lvl -= 1
            flag = True
        elif lvl == 2 and c == '\n':
            ret += ' '
            flag = False
        elif lvl == 2 and c == ' ':
            pass
        else:
            flag = True
        if flag: ret += c
    return ret

contestList = None
with open('../problemlists/contest_list.json', 'r', encoding='utf-8') as f:
    contestList = json.load(f)

if not isinstance(contestList, list):
    print("Failed to load problemlists/contest_list.json")
    exit(0)

contestCrawler = ContestCrawler()

for contest in contestList:
    if not isinstance(contest, dict): continue
    if all(value is None or len(value) == 0 for value in contest.values()): continue
    
    nullkey = [k for k, v in contest.items() if v is not None and len(v) == 0]
    for k in nullkey:
        contest[k] = None

    if contest.get("id") is not None: continue

    essential = ["category", "year", "filepath"]
    if not all(contest.get(key) is not None for key in essential): continue

    contest["id"]=" > ".join(map(str, contest.get("category"))) + " > " + contest.get("year") + " > " + str(datetime.now())

    nullkey = [k for k, v in contest.items() if v is None]
    for k in nullkey:
        del contest[k]
    
    if contestCrawler.open(contest):
        contestCrawler.process()

contestCrawler.close()

with open('../problemlists/contest_list.json', 'w', encoding='utf-8') as f:
    jsonstr = list(json.dumps(contestList, indent=4, ensure_ascii=False))
    f.write(parseJsonStr(jsonstr))
