import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import hashlib
from urllib.parse import urljoin

class QOJCrawler:
    def __init__(self, username, password):
        self.session = None
        self.successful_login(username, password)
        self.url = None
        self.html = None
        self.soup = None

        self.contest_name = None
        self.contest_category = None
        self.problems = None

    def successful_login(self, username, password):
        session = requests.Session()
        login_url = "https://qoj.ac/login"
        
        # Initial request to get CSRF token
        get_resp = session.get(login_url)
        csrf_token = re.search(r'_token\s*:\s*"([^"]+)"', get_resp.text).group(1)
        
        # Prepare login data
        login_data = {
            '_token': csrf_token,
            'login': '',
            'username': username,
            'password': hashlib.md5(password.encode()).hexdigest(),
        }
        
        # Make login request
        post_resp = session.post(login_url, data=login_data)
        
        # Verify login by testing protected access
        test_resp = session.get("https://qoj.ac/contest/450")
        if 'contest' in test_resp.text.lower():
            print("Login successful! You can now scrape protected pages.")
            self.session = session
            return session
        else:
            print("Login failed despite getting cookies")
            return None

    def fetch_qoj_page(self, url, delay=1):
        if self.session:
            time.sleep(delay)
            # Now you can make authenticated 
            
            # Check if we got a valid HTML response
            response = self.session.get(url)
            if 'text/html' not in response.headers.get('Content-Type', ''):
                print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                return None
            
            return response.text
        
    def parse_qoj_contest_name(self, soup):
        h1_tag = soup.select_one('div.text-center h1').get_text(strip=True)
        print("HIHI " + h1_tag)
        if h1_tag:
            return h1_tag
        else:
            print("Contest heading not found")
            return None

    def parse_qoj_contest_category(self, soup):
        alert_div = soup.find('div', class_='alert alert-secondary role=')
        if alert_div:
            return [a.get_text(strip=True) for a in alert_div.find_all('a')][1:]
        else:
            print("Contest category not found")
            return None

    def parse_qoj_problems_table(self, soup):
        table = soup.find('table', class_='table-bordered')
        
        if not table or len(table) == 0:
            print("Problems table not found in the HTML")
            return None
        
        problems = []
        
        if table:
            for row in table.find_all('tr')[1:]:  # Skip header row
                cols = row.find_all('td')
                if len(cols) >= 2:
                    url = cols[1].find('a')['href'] if cols[1].find('a') else None
                    if url is not None and url.startswith('/'): url = f"https://qoj.ac{url}"

                    problems.append({
                        "letter": cols[0].get_text(strip=True),
                        "title": cols[1].get_text(strip=True),
                        "url": url
                    })
        
        return problems

    def parse_qoj_pdf_links(self, filepath, soup = None):
        if soup == None : soup = self.soup
        attachments_section = soup.find('h4', string=lambda text: text and text.strip() == 'Attachments')
        if attachments_section:
            for a in attachments_section.find_next('div').find_all('a', class_='list-group-item list-group-item-action'):
                pdf_url = a['href']  # Get the href
                display_text = a.get_text(strip=True)  # Get the display text
                if pdf_url.startswith('/'): pdf_url = f"https://qoj.ac{pdf_url}"
                            
                print(f"Found link: [{display_text}]({pdf_url})")
                
                # Download the file
                try:
                    response = requests.get(pdf_url, stream=True)
                    response.raise_for_status()  # Check for HTTP errors
                    
                    download_name = display_text
                    if not download_name.endswith('.pdf'): download_name += '.pdf'

                    with open(filepath + download_name, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Downloaded: {download_name}")
                except Exception as e:
                    print(f"Failed to download {pdf_url}: {e}")

    def crawl_qoj_contest(self, contest_url, tableidx = []):
        print(f"Crawling QOJ contest: {contest_url}")
        self.url = contest_url
        
        self.html = self.fetch_qoj_page(contest_url)
        if not self.html:
            print("Failed to fetch the page")
            return
        
        self.soup = BeautifulSoup(self.html, 'html.parser')

        with open('qoj.html', 'w', encoding='utf-8') as f:
            f.write(self.html)

        self.contest_name = self.parse_qoj_contest_name(self.soup)
        self.contest_category = self.parse_qoj_contest_category(self.soup)
        self.problems = self.parse_qoj_problems_table(self.soup)
            
        # Display some basic info
        if self.contest_name is not None and self.contest_name != '':
            print(f"\nContest name: {self.contest_name}")
        if self.contest_category is not None and len(self.contest_category) != 0:
            print(f"Contest category: {self.contest_category}")
        if self.problems is not None and len(self.problems) != 0:
            print(f"Found {len(self.problems)} problems:")
            print(pd.DataFrame(self.problems))
        print()
        
        return self.contest_name, self.contest_category, self.problems

# # Example category URL (can be changed to any QOJ category)
# CATEGORY_URL = "https://qoj.ac/contest/450"

# qojCrawler = QOJCrawler('arnold518', 'jaemin518')

# # Run the crawler
# problems_data = qojCrawler.crawl_qoj_category(CATEGORY_URL)