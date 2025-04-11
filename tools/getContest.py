from JSONHandler import *
from getBOJ import BOJCrawler
from getCF import CFCrawler
from getQOJ import QOJCrawler

def print_sep(): print("\n"+'='*100)

class ContestCrawler:
    def __init__(self):
        self.CATEGORY = []
        self.YEAR = ""
        self.FILE_PATH = ""
        self.PDF_PATH = ""

        self.BOJ_URL = ""
        self.CF_URL = ""
        self.QOJ_URL = ""

        self.handler = None

        self.QOJ_USERNAME = "qoj_username"
        self.QOJ_PASSWORD = "qoj_password"
        self.load_credential_data()
        
        self.bojCrawler = BOJCrawler()
        self.cfCrawler = CFCrawler()
        self.qojCrawler = QOJCrawler(self.QOJ_USERNAME, self.QOJ_PASSWORD)

    # =========================================================================

    def open(self):
        self.CATEGORY = ["ICPC", "Regionals", "Asia Pacific", "Korea"]
        self.YEAR = "2020"
        self.FILE_PATH = "../problemlists/icpc/regionals/asia-pacific/korea/2020/"
        self.PDF_PATH = self.FILE_PATH + "crawled-data/"

        self.BOJ_URL = "https://www.acmicpc.net/category/detail/2339"
        self.CF_URL = "https://codeforces.com/gym/102920"
        self.QOJ_URL = "https://qoj.ac/contest/450"

        self.handler = JSONHandler(self.FILE_PATH + "contest.json")
        self.handler.clear()

    def process(self):
        self.update_by_default(self.CATEGORY, self.YEAR)
        print_sep()
        self.boj()
        print_sep()
        self.cf()
        print_sep()
        self.qoj()
        print_sep()

        self.handler.save()
        print()
        print(self.handler)
    
    def close(self):
        self.cfCrawler.close()

    # =========================================================================

    def load_credential_data(self):
        with open('credential.json', 'r', encoding='utf-8') as f:
            cred = json.load(f)
        if isinstance(cred, dict):
            self.QOJ_USERNAME = cred.get('QOJ_USERNAME') or "qoj_username"
            self.QOJ_PASSWORD = cred.get('QOJ_PASSWORD') or "qoj_password"

    def update_by_default(self, category, year):
        self.handler.update_nested_value(["category"], category)
        self.handler.update_nested_value(["year"], year)

    # =========================================================================

    def update_by_boj(self, name, url, problems, pdf_set):
        self.handler.update_nested_value(["name"], name, overwrite=True)
        self.handler.update_nested_value(["link", "BOJ"], url)
        for pdfname, pdflink in pdf_set.items():
            self.handler.update_nested_value(["pdflink", pdfname], pdflink)

        for idx, problem in enumerate(problems):
            self.handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=True)
            self.handler.update_problem_value(idx, ["title"], problem["title"], overwrite=True)
            self.handler.update_problem_value(idx, ["link", "BOJ"], problem["link"])

    def boj(self):
        name, problems, pdf_set = self.bojCrawler.crawl_boj_category(self.BOJ_URL, self.PDF_PATH)
        self.update_by_boj(name, self.BOJ_URL, problems, pdf_set)

    # =========================================================================

    def update_by_cf(self, name, url, problems, pdf_set):
        self.handler.update_nested_value(["name"], name, overwrite=False)
        self.handler.update_nested_value(["link", "CF"], url)
        for pdfname, pdflink in pdf_set.items():
            self.handler.update_nested_value(["pdflink", pdfname], pdflink)

        for idx, problem in enumerate(problems):
            self.handler.update_problem_value(idx, ["id"], problem["id"], overwrite=False)
            self.handler.update_problem_value(idx, ["title"], problem["name"], overwrite=False)
            self.handler.update_problem_value(idx, ["link", "CF"], problem["link"])

    def cf(self):
        name, problems, pdf_set = self.cfCrawler.crawl_cf_contest(self.CF_URL, self.PDF_PATH)
        self.update_by_cf(name, self.CF_URL, problems, pdf_set)

    # =========================================================================

    def update_by_qoj(self, name, url, category, problems, pdf_set):
        self.handler.update_nested_value(["category"], category, overwrite=False)
        self.handler.update_nested_value(["name"], name, overwrite=False)
        self.handler.update_nested_value(["link", "QOJ"], url)
        for pdfname, pdflink in pdf_set.items():
            self.handler.update_nested_value(["pdflink", pdfname], pdflink)

        for idx, problem in enumerate(problems):
            self.handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=False)
            self.handler.update_problem_value(idx, ["title"], problem["title"], overwrite=False)
            self.handler.update_problem_value(idx, ["link", "QOJ"], problem["url"])

    def qoj(self):
        name, category, problems, pdf_set = self.qojCrawler.crawl_qoj_contest(self.QOJ_URL, self.PDF_PATH)
        self.update_by_qoj(name, self.QOJ_URL, category, problems, pdf_set)

    # =========================================================================

contestCrawler = ContestCrawler()
contestCrawler.open()
contestCrawler.process()
contestCrawler.close()