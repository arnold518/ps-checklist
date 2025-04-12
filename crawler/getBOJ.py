import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin
from pathlib import Path

class BOJCrawler:
    def __init__(self):
        self.url = None
        self.html = None
        self.soup = None

        self.category_name = None
        self.problems = None
        self.pdf_set = None

    def fetch_boj_page(self, url, delay=1):
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
        
    def parse_boj_category_name(self, soup):
        h1_tag = soup.find('h1', class_='pull-left')
        if h1_tag:
            return next((content for content in h1_tag.contents if isinstance(content, str)), "").strip()
        else:
            print("Category heading not found")
            return None

    def parse_boj_problems_table(self, soup, tableidx):
        tables = soup.find_all('table', {'class': 'table table-striped table-bordered clickable-table'})
        
        if not tables or len(tables) == 0:
            print("Problems table not found in the HTML")
            return None
        
        # Extract table headers for reference
        # headers = [th.get_text(strip=True) for th in table.find('thead').find_all('th')]
        
        problems = []
        base_url = "https://www.acmicpc.net"

        if len(tableidx) == 0:
            tableidx = list(range(0, len(tables)))
        
        for tidx in tableidx:
            if tidx >= len(tables): continue
            table = tables[tidx]
            for row in table.find('tbody').find_all('tr'):
                cells = row.find_all('td')
                if len(cells) != 7:  # Skip malformed rows
                    continue
                    
                # Extract data from each cell
                problem = {
                    'number': cells[0].get_text(strip=True),
                    'letter': ('' if len(tables)==1 else str(tidx+1)+'.') + cells[1].get_text(strip=True),
                    'title': cells[2].get_text(strip=True),
                    'link': urljoin(base_url, cells[2].find('a')['href']),
                    # 'tags': ', '.join([tag.get_text(strip=True) for tag in cells[3].find_all('span', class_='problem-label')]),
                    # 'solved_count': cells[4].get_text(strip=True),
                    # 'submitted_count': cells[5].get_text(strip=True),
                    # 'acceptance_rate': cells[6].get_text(strip=True),
                    # 'solved_link': urljoin(base_url, cells[4].find('a')['href']) if cells[4].find('a') else '',
                    # 'submitted_link': urljoin(base_url, cells[5].find('a')['href']) if cells[5].find('a') else ''
                }
                problems.append(problem)
        
        return problems

    def parse_boj_pdf_links(self, filepath, soup):
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

                pdf_name = 'boj-' + pdf_name.replace(' ', '-')
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

    def crawl_boj_category(self, category_url, pdfpath, tableidx = []):
        print(f"Crawling BOJ category: {category_url}")
        self.url = category_url
        
        self.html = self.fetch_boj_page(category_url)
        if not self.html:
            print("Failed to fetch the page")
            return None, None, None
        
        self.soup = BeautifulSoup(self.html, 'html.parser')

        self.category_name = self.parse_boj_category_name(self.soup)
        self.problems = self.parse_boj_problems_table(self.soup, tableidx)
        self.pdf_set = self.parse_boj_pdf_links(pdfpath, self.soup)
            
        # Display some basic info
        if self.category_name is not None and self.category_name != '':
            print(f"\nContest name: {self.category_name}")
        if self.problems is not None and len(self.problems) != 0:
            print(f"Found {len(self.problems)} problems:")
            print(pd.DataFrame(self.problems))
        if self.pdf_set is not None and len(self.pdf_set) != 0:
            print(f"Found {len(self.pdf_set)} pdf links:")
            print(self.pdf_set)
        print()
        
        return self.category_name, self.problems, self.pdf_set

# # Example category URL (can be changed to any BOJ category)
# CATEGORY_URL = "https://www.acmicpc.net/category/detail/4348"

# # Run the crawler
# problems_data = crawl_boj_category(CATEGORY_URL)