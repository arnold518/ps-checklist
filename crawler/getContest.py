from JSONHandler import *
from getBOJ import BOJCrawler
from getCF import CFCrawler
from getQOJ import QOJCrawler

def print_sep(): print("\n"+'='*100)

class ContestCrawler:
    def __init__(self):
        self.ID = None
        self.CATEGORY = None
        self.YEAR = None
        self.FILE_PATH = None
        self.PDF_PATH = None

        self.OFFICIAL_URL = None
        self.STANDING_URL = None
        self.BOJ_URL = None
        self.CF_URL = None
        self.QOJ_URL = None

        self.handler = None

        self.QOJ_USERNAME = "qoj_username"
        self.QOJ_PASSWORD = "qoj_password"
        self.load_credential_data()
        
        self.bojCrawler = BOJCrawler()
        self.cfCrawler = CFCrawler()
        self.qojCrawler = QOJCrawler(self.QOJ_USERNAME, self.QOJ_PASSWORD)

    # =========================================================================

    def open(self, data):
        essential = ["id", "category", "year", "filepath"]
        for item in essential:
            if data.get(item) == None:
                return False

        self.ID = data.get("id")
        self.CATEGORY = data.get("category")
        self.YEAR = data.get("year")
        self.FILE_PATH = "../" + data.get("filepath")
        self.PDF_PATH = self.FILE_PATH + "crawled-data/"

        self.OFFICIAL_URL = data.get("official_url")
        self.STANDING_URL = data.get("standing_url")
        self.BOJ_URL = data.get("boj_url")
        self.CF_URL = data.get("cf_url")
        self.QOJ_URL = data.get("qoj_url")

        self.handler = JSONHandler(self.FILE_PATH + "contest.json")
        self.handler.clear()

        return True

    def process(self):
        self.update_by_default(self.ID, self.CATEGORY, self.YEAR, self.FILE_PATH.lstrip('../'))
        print_sep()

        if self.BOJ_URL is not None:
            self.boj()
            print_sep()

        if self.CF_URL is not None:
            self.cf()
            print_sep()

        if self.QOJ_URL is not None:
            self.qoj()
            print_sep()

        self.handler.save()
        print()
        print(self.handler)
    
    def close(self):
        if self.cfCrawler is not None:
            self.cfCrawler.close()

    # =========================================================================

    def load_credential_data(self):
        with open('credential.json', 'r', encoding='utf-8') as f:
            cred = json.load(f)
        if isinstance(cred, dict):
            self.QOJ_USERNAME = cred.get('QOJ_USERNAME') or "qoj_username"
            self.QOJ_PASSWORD = cred.get('QOJ_PASSWORD') or "qoj_password"

    def update_by_default(self, id, category, year, filepath):
        self.handler.update_nested_value(["id"], id)
        self.handler.update_nested_value(["category"], category)
        self.handler.update_nested_value(["year"], year)
        self.handler.update_nested_value(["filepath"], filepath)
        
        self.update_by_default2()

    def update_by_default2(self):
        self.handler.update_nested_value(["link", "official"], self.OFFICIAL_URL)
        self.handler.update_nested_value(["link", "standing"], self.STANDING_URL)

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
