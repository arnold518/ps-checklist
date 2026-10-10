# Minimal QOJ access

The beta branch now has an internal Python client for authenticated QOJ HTML
retrieval. It uses Python 3.9+ and the standard library; no package installation
is required for the standalone client/CLI. The new HTTP APIs use this client;
their dependencies and commands are in [fetch-api.md](fetch-api.md).

## Credentials

Fill the existing local file `crawler/credential.json`:

```json
{
    "QOJ_USERNAME": "your_qoj_id",
    "QOJ_PASSWORD": "your_plaintext_password"
}
```

The file is ignored by Git. `crawler/credential.example.json` is the shareable
template. The client reads this new file; it does not read the prototype's
`python-crawler/credential.json` or the deployed worker's secrets.

## Fetch a page

From the repository root:

```bash
python3 -m crawler.qoj https://qoj.ac/contest/2522 --output crawler/output/2522.html
```

On success, the command saves the source HTML and prints its page title. The
output directory is ignored by Git. An unsuccessful fetch exits with status 1;
login and challenge pages are not saved as successful results.

Use the same client instance to reuse a session across reads:

```python
from crawler.qoj import QojClient

client = QojClient.from_credentials_file()
page = client.fetch_page("https://qoj.ac/contest/2522")
print(page.title)
another_page = client.fetch_page("https://qoj.ac/category/756")
```

Cookies are kept in memory and processed through `http.cookiejar` and
`HTTPCookieProcessor`. Updated cookies replace their prior values, and cookies
are processed on redirects. Each client serializes its reads and refreshes the
login at most once per read when redirected back to login. A new CLI invocation
starts a fresh session. Credentials, cookie headers, password hashes, and raw
login errors are not printed.

## Verification and current limits

```bash
python3 -m unittest discover -s tests -p 'test_qoj_access.py' -v
```

The tests simulate HTTPS responses through the actual urllib cookie and redirect
handlers. They require no network or real QOJ credentials.

The login flow follows the prototype's observed CSRF and MD5 submission protocol.
After the user filled the new credentials file, a live CLI fetch of contest 2522
succeeded. It retrieved **The 2025 ICPC World Finals Baku**, including the twelve
problems A–L and English statements/tutorials attachment links. The raw HTML is
saved locally in the Git-ignored `crawler/output/2522.html`. A subsequent live
review fetched categories 701/756, global problem 14601, its contest-scoped page,
and problem 17704 with one login for all five reads. Statement-version pages
were also inspected: some QOJ versions contain HTML while others embed documents.
Live session expiry recovery and protected binary GET delivery remain unverified.
HEAD requests for a statement and both contest attachments returned 403 HTML;
this does not establish whether their authenticated GET requests will succeed.
`UPSTREAM_BLOCKED` means the environment encountered a source challenge;
credentials alone cannot resolve it. `LOGIN_FAILED` means the login response was
not accepted, and `AUTH_REQUIRED` means the requested resource still led to login
after one refresh. A successful login does not grant access to private contests.

The client fetches HTML only. The HTTP service now parses categories, contests,
and problems through it and uses one persistent session for queued QOJ work.
Document downloading remains a separate planned step. The fetch contracts and
seven full response examples are recorded in
[API decisions](api-decisions.md) and [API response examples](api-response-examples.md).
