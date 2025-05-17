import requests
from pathlib import Path
# from getQOJ import QOJCrawler

def is_pdf_file(url):
    try:
        # Verify headers
        h = requests.head(url, allow_redirects=True, timeout=5)
        print(h.headers.get('content-type', '').lower())
        if 'pdf' in h.headers.get('content-type', '').lower():
            return True
        
        r = requests.get(url, stream=True, timeout=10)
        print(r)
        return r.content.startswith(b'%PDF-')
    except:
        return False

def download_pdf(pdf_url, pdf_name, filepath):
    try:
        response = requests.get(pdf_url, stream=True)
        response.raise_for_status()  # Check for HTTP errors

        path = Path(filepath + pdf_name)
        if not path: raise ValueError("No file path specified")
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded: {pdf_name}")
        return True
    except Exception as e:
        print(f"Failed to download {pdf_url}: {e}")
        return False

def PDFCrawler(url, pdf_name, filepath, qojCrawler):
    if url.startswith("https://qoj.ac/download.php"):
        return qojCrawler.crawl_pdf_link(url, pdf_name, filepath)
    elif is_pdf_file(url):
        return download_pdf(url, pdf_name, filepath)
    else:
        print(f"URL {url} is not downloadable pdf")
        return False

# PDFCrawler("https://qoj.ac/download.php?type=attachments&id=1886&r=0", "statement.pdf", "./test/", QOJCrawler("arnold518", "password"))