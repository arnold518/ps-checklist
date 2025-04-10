import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import requests
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd

class CFCrawler:
    def __init__(self):
        self.driver = None
        self.setup_driver()
        
        self.url = None
        self.html = None
        self.soup = None

        self.contest_name = None
        self.problems = None

    def setup_driver(self):
        """Configure undetected ChromeDriver with simplified options"""
        options = uc.ChromeOptions()
        
        # Basic options that work across versions
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        
        try:
            self.driver = uc.Chrome(
                options=options,
                version_main=None  # Let undetected_chromedriver auto-detect version
            )
            return True
        except Exception as e:
            print(f"Failed to initialize driver: {e}")
            print("\nTroubleshooting steps:")
            print("1. Make sure Google Chrome is installed")
            print("2. Run 'chrome://version/' in Chrome to check your version")
            print("3. Try updating Chrome: https://www.google.com/chrome/")
            print("4. Alternatively, try this command in cmd:")
            print("   undetected-chromedriver install")
            return False

    def scrape_contest(self, contest_url):
        """Main scraping function"""
        if not self.driver:
            return False
            
        try:
            # Initial navigation
            self.driver.get("https://codeforces.com")
            time.sleep(random.uniform(1, 3))
            
            # Go to contest page
            print(f"Accessing contest: {contest_url}")
            self.driver.get(contest_url)
            time.sleep(random.uniform(2, 4))
            
            # Check for login requirement
            if "enter" in self.driver.current_url:
                print("\nManual login required!")
                print("1. A Chrome window has opened")
                print("2. Please login to Codeforces manually")
                print("3. After login, come back here and press Enter")
                input("Press Enter to continue after login...")
                self.driver.get(contest_url)
                time.sleep(2)
            
            # Wait for problems table
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "problems"))
                )
                print("\nSuccessfully loaded problems table")
                
                # Print HTML content
                self.html = self.driver.page_source
                return True
            except:
                print("Problems table not found")
                return False
                
        except Exception as e:
            print(f"Error during scraping: {e}")
            return False

    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

    def parse_cf_problems_table(self, soup):
        # Find the problems table
        problems_table = soup.find('div', {'class': 'datatable'}, style="background-color: #E1E1E1; padding-bottom: 3px;")
        table = problems_table.find('table', {'class': 'problems'})

        # Extract problem data
        problems = []
        for row in table.find_all('tr')[1:]:  # Skip header row
            cols = row.find_all('td')
            if len(cols) >= 4:  # Ensure it's a valid problem row
                problem = {
                    'id': cols[0].get_text(strip=True),
                    'name': cols[1].find('a').get_text(strip=True),
                    'link': 'https://codeforces.com' + cols[1].find('a')['href'],
                    # 'time_limit': cols[1].find('div', {'class': 'notice'}).get_text().strip().split('  ')[-1].split(', ')[0],
                    # 'memory_limit': cols[1].find('div', {'class': 'notice'}).get_text().strip().split('  ')[-1].split(', ')[1],
                    # 'solved_count': cols[3].find('a').get_text(strip=True).replace('x', '')
                }
                problems.append(problem)
        
        return problems
    
    def parse_cf_contest_name(self, soup):
        contest_elements = soup.find('th', class_='left').find('a')
        if contest_elements:
            return contest_elements.get_text()
        else:
            print("Contest name not found")
            return None
    
    def parse_cf_pdf_links(self, filepath, soup = None):
        if soup == None : soup = self.soup
        # Find all links ending with .pdf
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
        
        for link in pdf_links:
            pdf_url = link['href']  # Get the href
            pdf_name = pdf_url.split('/')[-1]  # Extract filename
            display_text = link.get_text()  # Get the display text
            if pdf_url.startswith('/'): pdf_url = f"https://codeforces.com{pdf_url}"
            
            print(f"Found link: [{display_text}]({pdf_url})")
            
            # Download the file
            try:
                response = requests.get(pdf_url, stream=True)
                response.raise_for_status()  # Check for HTTP errors
                
                with open(filepath + pdf_name, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Downloaded: {pdf_name}")
            except Exception as e:
                print(f"Failed to download {pdf_url}: {e}")
    
    def crawl_cf_contest(self, contest_url):
        print(f"Crawling CF contest: {contest_url}")
        self.url = contest_url

        if not self.scrape_contest(self.url):
            print("Failed to fetch the page")
            return

        # with open('codeforces.html', 'r', encoding='utf-8') as f:
        #     self.html = f.read()
        
        self.soup = BeautifulSoup(self.html, 'html.parser')

        self.problems = self.parse_cf_problems_table(self.soup)
        self.contest_name = self.parse_cf_contest_name(self.soup)
        
        # Display some basic info
        if self.contest_name is not None and self.contest_name != '':
            print(f"\nContest name: {self.contest_name}")
        if self.problems is not None and len(self.problems) != 0:
            print(f"Found {len(self.problems)} problems:")
            print(pd.DataFrame(self.problems))
        print()

        return self.contest_name, self.problems

# if __name__ == "__main__":
#     # Configuration
#     CONTEST_URL = "https://codeforces.com/gym/104713"
    
#     # Run scraper
#     scraper = CFCrawler()
#     scraper.crawl_cf_contest(CONTEST_URL)
#     scraper.close()