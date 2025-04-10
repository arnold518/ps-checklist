from JSONHandler import *
from getBOJ import BOJCrawler
from getCF import CFCrawler
from getQOJ import QOJCrawler

YEAR = "2020"
FILE_PATH = "../problemlists/icpc/regionals/asia-pacific/korea/2020/"
CATEGORY = ["ICPC", "Regionals", "Asia Pacific", "Korea"]

BOJ_URL = "https://www.acmicpc.net/category/detail/2339"
CF_URL = "https://codeforces.com/gym/102920"
QOJ_URL = "https://qoj.ac/contest/450"

QOJ_USERNAME = "arnold518"
QOJ_PASSWORD = "password"

# =========================================================================

def print_sep(): print("\n"+'='*100)

def update_by_default(category, year):
    handler.update_nested_value(["category"], category)
    handler.update_nested_value(["year"], year)

# =========================================================================

def update_by_boj(handler, name, url, problems):
    handler.update_nested_value(["name"], name, overwrite=True)
    handler.update_nested_value(["link", "BOJ"], url)

    for idx, problem in enumerate(problems):
        handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=True)
        handler.update_problem_value(idx, ["title"], problem["title"], overwrite=True)
        handler.update_problem_value(idx, ["link", "BOJ"], problem["link"])

def boj(bojCrawler):
    name, problems = bojCrawler.crawl_boj_category(BOJ_URL)
    bojCrawler.parse_boj_pdf_links(FILE_PATH)
    update_by_boj(handler, name, BOJ_URL, problems)

# =========================================================================

def update_by_cf(handler, name, url, problems):
    handler.update_nested_value(["name"], name, overwrite=False)
    handler.update_nested_value(["link", "CF"], url)

    for idx, problem in enumerate(problems):
        handler.update_problem_value(idx, ["id"], problem["id"], overwrite=False)
        handler.update_problem_value(idx, ["title"], problem["name"], overwrite=False)
        handler.update_problem_value(idx, ["link", "CF"], problem["link"])

def cf(cfCrawler):
    name, problems = cfCrawler.crawl_cf_contest(CF_URL)
    cfCrawler.parse_cf_pdf_links(FILE_PATH)
    update_by_cf(handler, name, CF_URL, problems)

# =========================================================================

def update_by_qoj(handler, name, url, category, problems):
    handler.update_nested_value(["category"], category, overwrite=False)
    handler.update_nested_value(["name"], name, overwrite=False)
    handler.update_nested_value(["link", "QOJ"], url)

    for idx, problem in enumerate(problems):
        handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=False)
        handler.update_problem_value(idx, ["title"], problem["title"], overwrite=False)
        handler.update_problem_value(idx, ["link", "QOJ"], problem["url"])

def qoj(qojCrawler):
    name, category, problems = qojCrawler.crawl_qoj_contest(QOJ_URL)
    qojCrawler.parse_qoj_pdf_links(FILE_PATH)
    update_by_qoj(handler, name, QOJ_URL, category, problems)

# =========================================================================

handler = JSONHandler(FILE_PATH + "problemlist.json")
bojCrawler = BOJCrawler()
cfCrawler = CFCrawler()
qojCralwer = QOJCrawler(QOJ_USERNAME, QOJ_PASSWORD)

# =========================================================================

handler.clear()

update_by_default(CATEGORY, YEAR)

print_sep()
boj(bojCrawler)
print_sep()
cf(cfCrawler)
print_sep()
qoj(qojCralwer)
print_sep()

handler.save()

print()
print(handler)

cfCrawler.close()