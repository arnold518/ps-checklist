import json
from datetime import datetime
from getContest import ContestCrawler
import pandas
import sys

class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()  # Ensure immediate output

    def flush(self):
        for f in self.files:
            f.flush()

def parseJsonStr(jsonstr):
    lvl = 0
    ret = ''
    in_quote = False
    
    for c in jsonstr:
        should_append = True
        
        if c == '"':
            in_quote = not in_quote
        if c == '[':
            lvl += 1
        elif c == ']':
            lvl -= 1
        elif lvl == 2:
            if not in_quote:
                if c == '\n':
                    ret += ' '
                    should_append = False
                elif c == ' ':
                    should_append = False
        
        if should_append:
            ret += c
    
    return ret


pandas.set_option('display.max_columns', None)
pandas.set_option('display.width', 2000)

log_file = open("output.log", "w", encoding="utf-8")
original_stdout = sys.stdout
sys.stdout = Tee(sys.stdout, log_file)

# ==========================================================================

contestList = None
contestListRaw = []

with open('../problemlists/contestlist.json', 'r', encoding='utf-8') as f:
    contestList = json.load(f)

if not isinstance(contestList, list):
    print("Failed to load problemlists/contestlist.json")
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
    
    contestListRaw.append(contest.copy())

    nullkey = [k for k, v in contest.items() if v is None]
    for k in nullkey:
        del contest[k]
    
    if contestCrawler.open(contest):
        contestCrawler.process()

contestCrawler.close()

with open('../problemlists/contestlist.json', 'w', encoding='utf-8') as f:
    jsonstr = list(json.dumps(contestList, indent=4, ensure_ascii=False))
    f.write(parseJsonStr(jsonstr))
with open('../problemlists/contestlist_history.log', 'a', encoding='utf-8') as f:
    jsonstr = list(json.dumps(contestListRaw, indent=4, ensure_ascii=False))
    f.write(parseJsonStr(jsonstr) + "\n" + str(datetime.now()) + "\n")