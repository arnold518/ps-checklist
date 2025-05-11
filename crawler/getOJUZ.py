import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin
from pathlib import Path
from getSolvedAC import get_problem_original_name

class OJUZCrawler:
    def __init__(self):
        self.url = None
        self.html = None
        self.soup = None

        self.category_name = None
        self.problems = None
        self.pdf_set = None

    def fetch_ojuz_page(self, url, delay=1):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        try:
            time.sleep(delay)  # Respectful crawling delay
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # Check if we got a valid HTML response
            if 'text/html' not in response.headers.get('Content-Type', ''):
                print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                return None
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
        
    def parse_ojuz_category_name(self, soup):
        category = soup.find('ol', class_='breadcrumb')
        if category:
            category = [li.get_text(strip=True) for li in category.find_all('li')]
        category = category[1:]
        if category and category[-1].startswith("Day"):
            category = category[:-1]
        print(f"Category name: {category}")

    def parse_ojuz_problems_table(self, soup, tableidx):
        tables = soup.find_all('table', {'class': 'table table-striped table-hover'})

        if not tables or len(tables) == 0:
            print("Problems table not found in the HTML")
            return None
        
        # Extract table headers for reference
        # headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]
        
        problems = []
        base_url = "https://www.oj.uz"

        if len(tableidx) == 0:
            tableidx = list(range(0, len(tables)))
        
        for tidx in tableidx:
            if tidx >= len(tables): continue
            table = tables[tidx]
            
            # Extract table headers for reference
            headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]
            
            for row in table.find('tbody').find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < 5:  # Skip malformed rows
                    continue
                
                # Extract data from each cell
                problem = {
                    'number': cells[0].get_text(strip=True),
                    'title': cells[3].find('a').get_text(strip=True),
                    'link': urljoin("https://oj.uz", cells[3].find('a')['href']),
                    # 'alias': cells[1].get_text(strip=True),
                    # 'solved_count': cells[4].get_text(strip=True),
                    # 'score': cells[2].find('div', class_='text').get_text(strip=True).split(' / ')[0],
                    # 'max_score': cells[2].find('div', class_='text').get_text(strip=True).split(' / ')[1],
                    'tags': [tag.get_text(strip=True) for tag in cells[3].find_all('span', class_='label')]
                }
                
                problems.append(problem)
        
        return problems
    
    def parse_ojuz_category_table(self, soup):
        tables = soup.find_all('table', {'class': 'table table-striped table-bordered'})
        links = []
        for table in tables:
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                link = row.find('a', href=True)
                if link:
                    links.append(urljoin("https://oj.uz", link['href']+'?locale=en'))
        return links


    def parse_ojuz_pdf_links(self, filepath, soup):
        # Find all links ending with .pdf
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
        pdf_set = {}
        
        for link in pdf_links:
            pdf_url = link['href']  # Get the href
            pdf_name = pdf_url.split('/')[-1]  # Extract filename
            display_text = link.get_text()  # Get the display text
            
            print(f"Found link: [{display_text}]({pdf_url})")
            
            # Download the file
            try:
                response = requests.get(pdf_url, stream=True)
                response.raise_for_status()  # Check for HTTP errors

                pdf_name = 'ojuz-' + pdf_name.replace(' ', '-')
                pdf_set.update({pdf_name: pdf_url})
                path = Path(filepath + pdf_name)
                if not path: raise ValueError("No file path specified")
                path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Downloaded: {pdf_name}")
            except Exception as e:
                print(f"Failed to download {pdf_url}: {e}")
        return pdf_set

    def crawl_ojuz_contest(self, contest_url, pdfpath, tableidx = []):
        # empty list is equivalent to All
        # returns the problems of the intersection of tableidx and keywords
        print(f"Crawling OJUZ contest: {contest_url}")
        self.url = contest_url
        
        self.html = self.fetch_ojuz_page(contest_url)
        if not self.html:
            print("Failed to fetch the page")
            return None, None, None
        
        self.soup = BeautifulSoup(self.html, 'html.parser')

        self.parse_ojuz_category_table(self.soup)
        category_name = self.parse_ojuz_category_name(self.soup)
        problems = self.parse_ojuz_problems_table(self.soup, tableidx)
        pdf_set = self.parse_ojuz_pdf_links(pdfpath, self.soup)

        # Display some basic info
        if category_name is not None and category_name != '':
            print(f"\nCategory name: {category_name}")
        if problems is not None and len(problems) != 0:
            print(f"Found {len(problems)} problems:")
            print(pd.DataFrame(problems))
        if pdf_set is not None and len(pdf_set) != 0:
            print(f"Found {len(pdf_set)} pdf links:")
            print(pdf_set)
        print()
        
        return category_name, problems, pdf_set
    
    def crawl_ojuz_category(self, category_url, pdfpath):
        print(f"Crawling OJUZ category: {category_url}")
        self.url = category_url
        self.html = self.fetch_ojuz_page(category_url)
        
        if not self.html:
            print("Failed to fetch the page")
            return None, None, None
        
        self.soup = BeautifulSoup(self.html, 'html.parser')
        
        category_table = self.parse_ojuz_category_table(self.soup)
        problems = []
        pdf_set = {}
        contest_category = []

        for idx, contest_url in enumerate(category_table):
            _contest_category, _problems, _pdf_set = self.crawl_ojuz_contest(contest_url, pdfpath)
            contest_category = _contest_category
            if _problems:
                for problem in _problems:
                    problem["number"] = f"{idx+1}{chr(64 + int(problem['number']))}"
                problems.extend(_problems)
            if _pdf_set:
                pdf_set.update(_pdf_set)
        
        # Display results
        if contest_category:
            print(f"Contest category: {contest_category}")
        if problems:
            print(f"Found {len(problems)} problems:")
            print(pd.DataFrame(problems))
        if pdf_set:
            print(f"Found {len(pdf_set)} PDF attachments")
        
        return contest_category, problems, pdf_set


# ojuzCrawler = OJUZCrawler()
# crawl_ojuz_category = ojuzCrawler.crawl_ojuz_contest("https://oj.uz/problems/source/apio2024?locale=en", "./test/")
# crawl_ojuz_category = ojuzCrawler.crawl_ojuz_category("https://oj.uz/problems/source/joisc2024?locale=en", "./test/")
# crawl_ojuz_category = ojuzCrawler.crawl_ojuz_category("https://www.acmicpc.net/category/1056", "./test/", tableidx=[1, 2], keywords=["Day"])
# crawl_ojuz_category = ojuzCrawler.crawl_ojuz_category("https://www.acmicpc.net/category/detail/2859", "./test/")