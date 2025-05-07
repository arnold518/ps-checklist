import cloudscraper
import hashlib
import time
import re
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path
import getPDF

class QOJCrawler:
    def __init__(self, username, password):
        # Create a cloudscraper instance that will be used for all requests
        self.scraper = cloudscraper.create_scraper()
        self.username = username
        self.password = password
        self.url = None
        self.html = None
        self.soup = None
        
        if not self.successful_login():
            raise Exception("Login failed")

    def successful_login(self):
        login_url = "https://qoj.ac/login"
        
        try:
            # First GET request to get CSRF token and cookies
            get_resp = self.scraper.get(login_url)
            if "Just a moment" in get_resp.text:
                raise Exception("Initial Cloudflare challenge failed")

            # Extract CSRF token from JavaScript
            csrf_token = None
            match = re.search(r"_token\s*:\s*\"([^\"]+)\"", get_resp.text)
            if match:
                csrf_token = match.group(1)
            
            if not csrf_token:
                raise Exception("CSRF token not found")

            # Prepare login data with MD5 hashed password
            login_data = {
                '_token': csrf_token,
                'login': '',
                'username': self.username,
                'password': hashlib.md5(self.password.encode()).hexdigest(),
            }

            # Add necessary headers for AJAX-style login
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://qoj.ac',
                'Referer': login_url,
                'Accept': 'application/json, text/javascript, */*; q=0.01',
            }

            # Submit login with custom headers
            post_resp = self.scraper.post(login_url, 
                                        data=login_data, 
                                        headers=headers)
            
            # The site returns "OK" for successful login
            if post_resp.text.strip() == "ok":
                # Verify by accessing a protected page
                test_resp = self.scraper.get("https://qoj.ac/contest/450")
                if 'contest' in test_resp.text.lower():
                    print("Login successful!")
                    return True
                else:
                    raise Exception("Login verification failed")
            else:
                raise Exception(f"Unexpected login response: {post_resp.text}")
                
        except Exception as e:
            print(f"Login error: {str(e)}")
            return False

    def fetch_qoj_page(self, url, delay=1):
        time.sleep(delay)  # Respectful delay between requests
        try:
            response = self.scraper.get(url)
            if 'text/html' not in response.headers.get('Content-Type', ''):
                print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                return None
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
        
    def parse_qoj_contest_name(self, soup):
        h1_tag = soup.select_one('div.text-center h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        print("Contest heading not found")
        return None

    def parse_qoj_contest_category(self, soup):
        alert_div = soup.find('div', class_='alert')
        if alert_div:
            return [a.get_text(strip=True) for a in alert_div.find_all('a')][1:]
        print("Contest category not found")
        return None

    def parse_qoj_problems_table(self, soup):
        table = soup.find('table', class_='table-bordered')
        if not table:
            print("Problems table not found")
            return None
            
        problems = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 2:
                url = cols[1].find('a')['href'] if cols[1].find('a') else None
                if url and url.startswith('/'):
                    url = f"https://qoj.ac{url}"
                problems.append({
                    "letter": cols[0].get_text(strip=True),
                    "title": cols[1].get_text(strip=True),
                    "url": url
                })
        return problems
    
    def parse_qoj_category_table(self, soup):
        table = soup.find('table', class_='table table-hover table-striped')
        if not table:
            print("Category table not found")
            return None
        
        contests = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            link_cell = cols[0].find('a')
            if link_cell and 'href' in link_cell.attrs:
                link = link_cell['href']
                if link.startswith('/'):
                    link = f"https://qoj.ac{link}"
                contests.append(link)
        print(contests)
        return contests

    def parse_qoj_pdf_links(self, filepath, soup):
        pdf_set = {}
        attachments_section = soup.find('h4', string=lambda text: text and text.strip() == 'Attachments')
        if not attachments_section:
            return pdf_set
            
        for a in attachments_section.find_next('div').find_all('a', class_='list-group-item list-group-item-action'):
            pdf_url = a['href']
            display_text = a.get_text(strip=True)
            
            if pdf_url.startswith('/'):
                pdf_url = f"https://qoj.ac{pdf_url}"
            
            print(f"Found link: [{display_text}]({pdf_url})")
            
            try:
                response = self.scraper.get(pdf_url, stream=True)
                response.raise_for_status()  # Raise HTTPError for bad responses

                # Verify content type is PDF
                content_type = response.headers.get('Content-Type', '').lower()
                if 'pdf' not in content_type:
                    print(f"Error: Expected PDF but got {content_type}")
                    continue

                # Use the same scraper session for PDF downloads
                response = self.scraper.get(pdf_url, stream=True)
                response.raise_for_status()
                
                pdf_name = f"qoj-{display_text.replace(' ', '-')}"
                if not pdf_name.endswith('.pdf'):
                    pdf_name += '.pdf'
                
                path = Path(filepath) / pdf_name
                path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                pdf_set[pdf_name] = pdf_url
                print(f"Downloaded: {pdf_name}")
                
            except Exception as e:
                print(f"Failed to download {pdf_url}: {e}")
        
        return pdf_set

    def crawl_qoj_contest(self, contest_url, pdfpath, tableidx=[]):
        print(f"Crawling QOJ contest: {contest_url}")
        self.url = contest_url
        self.html = self.fetch_qoj_page(contest_url)
        
        if not self.html:
            print("Failed to fetch the page")
            return None, None, None, None
        
        self.soup = BeautifulSoup(self.html, 'html.parser')

        contest_name = self.parse_qoj_contest_name(self.soup)
        contest_category = self.parse_qoj_contest_category(self.soup)
        problems = self.parse_qoj_problems_table(self.soup)
        pdf_set = self.parse_qoj_pdf_links(pdfpath, self.soup)
        
        # Display results
        if contest_name:
            print(f"\nContest name: {contest_name}")
        if contest_category:
            print(f"Contest category: {contest_category}")
        if problems:
            print(f"Found {len(problems)} problems:")
            print(pd.DataFrame(problems))
        if pdf_set:
            print(f"Found {len(pdf_set)} PDF attachments")
        
        return contest_name, contest_category, problems, pdf_set
    
    def crawl_qoj_category(self, category_url, pdfpath):
        print(f"Crawling QOJ category: {category_url}")
        self.url = category_url
        self.html = self.fetch_qoj_page(category_url)
        
        if not self.html:
            print("Failed to fetch the page")
            return None, None, None
        
        self.soup = BeautifulSoup(self.html, 'html.parser')
        
        category_table = self.parse_qoj_category_table(self.soup)
        problems = []
        pdf_set = {}
        contest_category = []
        contest_name = ""

        for idx, contest_url in enumerate(category_table):
            _contest_name, _contest_category, _problems, _pdf_set = self.crawl_qoj_contest(contest_url, pdfpath)
            if _contest_name and _contest_name.endswith(f"Day {_contest_name.split()[-1]}") and _contest_name.split()[-1].isdigit():
                _contest_name = ' '.join(_contest_name.split()[:-2])
            if contest_name == "":
                contest_name = _contest_name
            else:
                contest_name = ''.join([contest_name[i] for i in range(min(len(contest_name), len(_contest_name))) if contest_name[i] == _contest_name[i]])
            contest_category = _contest_category
            if _problems:
                for problem in _problems:
                    problem["letter"] = f"{idx+1}{problem['letter']}"
                problems.extend(_problems)
            if _pdf_set:
                pdf_set.update(_pdf_set)
        
        # Display results
        if contest_name:
            print(f"\nContest name: {contest_name}")
        if contest_category:
            print(f"Contest category: {contest_category}")
        if problems:
            print(f"Found {len(problems)} problems:")
            print(pd.DataFrame(problems))
        if pdf_set:
            print(f"Found {len(pdf_set)} PDF attachments")
        
        return contest_name, contest_category, problems, pdf_set

# qojCrawler = QOJCrawler('arnold518', 'password')
# crawl_qoj_contest = qojCrawler.crawl_qoj_category("https://qoj.ac/category/369", "./test/")