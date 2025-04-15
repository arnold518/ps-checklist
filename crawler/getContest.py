from JSONHandler import *
from getBOJ import BOJCrawler
from getCF import CFCrawler
from getQOJ import QOJCrawler
from getPDF import PDFCrawler

def print_sep(): print("\n"+'='*100)
def print_wall(): 
    for i in range(3): print("="*100)

class ContestCrawler:
    def __init__(self):
        self.ID = None
        self.CATEGORY = None
        self.YEAR = None
        self.FILE_PATH = None
        self.PDF_PATH = None

        self.RAW_URL_PREFIX = './' # "https://raw.githubusercontent.com/arnold518/ps-checklist/data/"
        self.OFFICIAL_URL = None
        self.STANDING_URL = None
        self.BOJ_URL = None
        self.CF_URL = None
        self.QOJ_URL = None
        self.STATEMENTS_URL = None
        self.EDITORIALS_URL = None

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

        print('\n'*5)
        print_wall()
        print("Processing contest:")
        print(f"ID: {self.ID}")
        print(f"Category: {self.CATEGORY}")
        print(f"Year: {self.YEAR}")
        print(f"File Path: {self.FILE_PATH}")
        print_wall()

        self.OFFICIAL_URL = data.get("official_url")
        self.STANDING_URL = data.get("standing_url")
        self.BOJ_URL = data.get("boj_url")
        self.CF_URL = data.get("cf_url")
        self.QOJ_URL = data.get("qoj_url")
        self.STATEMENTS_URL = data.get("statements_url")
        self.EDITORIALS_URL = data.get("editorials_url")

        if self.STATEMENTS_URL is not None:
            if PDFCrawler(self.STATEMENTS_URL, 'statements.pdf', self.FILE_PATH) :
                self.STATEMENTS_URL = self.RAW_URL_PREFIX + data.get("filepath") + 'statements.pdf'
                data["statements_url"] = self.STATEMENTS_URL
        if self.EDITORIALS_URL is not None:
            if PDFCrawler(self.EDITORIALS_URL, 'editorials.pdf', self.FILE_PATH) :
                self.EDITORIALS_URL = self.RAW_URL_PREFIX + data.get("filepath") + 'editorials.pdf'        
                data["editorials_url"] = self.EDITORIALS_URL

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

        print_wall()
        print(f"Contest {self.ID} processed successfully.")
        print(f"Contest data saved to {self.FILE_PATH}contest.json")
        print_wall()
        print('\n'*5)
    
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

        self.handler.update_nested_value(["name"], "")
        
        self.handler.update_nested_value(["link", "statements"], self.STATEMENTS_URL)
        self.handler.update_nested_value(["link", "editorials"], self.EDITORIALS_URL)

        self.handler.update_nested_value(["link", "official"], self.OFFICIAL_URL)
        self.handler.update_nested_value(["link", "standing"], self.STANDING_URL)

    # =========================================================================

    def update_by_boj(self, name, url, problems, pdf_set):
        self.handler.update_nested_value(["name"], name, overwrite=True)
        self.handler.update_nested_value(["link", "BOJ"], url)
        if pdf_set is not None:
            for pdfname, pdflink in pdf_set.items():
                self.handler.update_nested_value(["crawled_data", pdfname], pdflink)

        if problems is not None:
            for idx, problem in enumerate(problems):
                self.handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=True)
                self.handler.update_problem_value(idx, ["title"], problem["title"], overwrite=True)
                self.handler.update_problem_value(idx, ["link", "BOJ"], problem["link"])

    def boj(self):
        name, problems, pdf_set = self.bojCrawler.crawl_boj_category(self.BOJ_URL, self.PDF_PATH, [0])
        self.update_by_boj(name, self.BOJ_URL, problems, pdf_set)

    # =========================================================================

    def update_by_cf(self, name, url, problems, pdf_set):
        self.handler.update_nested_value(["name"], name, overwrite=True)
        self.handler.update_nested_value(["link", "CF"], url)
        if pdf_set is not None:
            for pdfname, pdflink in pdf_set.items():
                self.handler.update_nested_value(["crawled_data", pdfname], pdflink)

        if problems is not None:
            for idx, problem in enumerate(problems):
                self.handler.update_problem_value(idx, ["id"], problem["id"], overwrite=True)
                self.handler.update_problem_value(idx, ["title"], problem["name"], overwrite=True)
                self.handler.update_problem_value(idx, ["link", "CF"], problem["link"])

    def cf(self):
        name, problems, pdf_set = self.cfCrawler.crawl_cf_contest(self.CF_URL, self.PDF_PATH)
        self.update_by_cf(name, self.CF_URL, problems, pdf_set)

    # =========================================================================

    def update_by_qoj(self, name, url, category, problems, pdf_set):
        self.handler.update_nested_value(["category"], category, overwrite=False)
        self.handler.update_nested_value(["name"], name, overwrite=True)
        self.handler.update_nested_value(["link", "QOJ"], url)
        if pdf_set is not None:
            for pdfname, pdflink in pdf_set.items():
                self.handler.update_nested_value(["crawled_data", pdfname], pdflink)

        if problems is not None:
            for idx, problem in enumerate(problems):
                self.handler.update_problem_value(idx, ["id"], problem["letter"], overwrite=False)
                self.handler.update_problem_value(idx, ["title"], problem["title"], overwrite=False)
                self.handler.update_problem_value(idx, ["link", "QOJ"], problem["url"])

    def qoj(self):
        name, category, problems, pdf_set = self.qojCrawler.crawl_qoj_contest(self.QOJ_URL, self.PDF_PATH)
        self.update_by_qoj(name, self.QOJ_URL, category, problems, pdf_set)

    # =========================================================================
