"""Codeforces API metadata with separate contest/problem HTML extraction."""

from copy import deepcopy
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from ..contracts import FetchError, contest, contest_ref, full_problem, summary
from ..markup import (absolute, clean, document_statement, infer_task, limits, material,
                      samples, statement, unique_materials)


def problem_key(category, contest_id, index):
    return f"cf:{category}:{contest_id}:{index}"


def api_result(page):
    value = page.json()
    if not isinstance(value, dict) or value.get("status") not in {"OK", "FAILED"}:
        raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces API returned unexpected metadata.")
    if value["status"] == "FAILED":
        comment = value.get("comment", "")
        if re.search(r"contest.*not found|contest.*does not exist", comment, re.I):
            raise FetchError("CONTEST_NOT_FOUND", "Codeforces confirms that the contest is absent.", 404)
        if re.search(r"authenticat|logged in|access denied", comment, re.I):
            raise FetchError("UPSTREAM_AUTH_REQUIRED", "Codeforces requires authorized API access.", 403)
        raise FetchError("UPSTREAM_UNAVAILABLE", "Codeforces API could not provide the requested metadata.", 503, True)
    return value.get("result")


def parse_api_contest(native, category):
    if not isinstance(native, dict) or not native.get("name") or not isinstance(native.get("id"), int):
        raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces contest metadata is incomplete.")
    native_id = native["id"]
    data = contest(f"cf:{category}:{native_id}", "cf", native_id, native["name"],
                   f"https://codeforces.com/{category}/{native_id}", category)
    data.update(scoringType=native.get("type"), phase=native.get("phase"), frozen=native.get("frozen"),
                durationSeconds=native.get("durationSeconds"))
    if isinstance(native.get("startTimeSeconds"), (int, float)):
        start = native["startTimeSeconds"]
        data["startTime"] = datetime.fromtimestamp(start, timezone.utc).isoformat().replace("+00:00", "Z")
        if data["durationSeconds"] is not None:
            data["endTime"] = datetime.fromtimestamp(start + data["durationSeconds"], timezone.utc).isoformat().replace("+00:00", "Z")
    data["details"] = {name: native.get(name) for name in [
        "preparedBy", "websiteUrl", "descriptionHtml", "difficulty", "kind", "icpcRegion",
        "country", "city", "season", "freezeDurationSeconds"]}
    if data["details"]["descriptionHtml"]:
        from bs4 import BeautifulSoup
        from ..markup import sanitize
        data["details"]["descriptionHtml"] = sanitize(BeautifulSoup(data["details"]["descriptionHtml"], "html.parser"), data["url"])[0]
    return data


def api_problem(native, category, contest_id):
    if (not isinstance(native, dict) or not native.get("index") or not native.get("name")
            or native.get("contestId", contest_id) != contest_id):
        raise FetchError("UPSTREAM_PARSE_ERROR", "A Codeforces problem identity is invalid.")
    index = native["index"]
    value = summary(problem_key(category, contest_id, index), native["name"],
                    f"https://codeforces.com/{category}/{contest_id}/problem/{index}", index)
    value.update(type=native.get("type"), points=native.get("points"), rating=native.get("rating"),
                 tags=native.get("tags"))
    return value


def parse_html_contest(page, category, contest_id):
    soup = page.soup()
    table = soup.select_one("table.problems")
    if table is None:
        raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces' complete problem table is unavailable.")
    problems = []
    for row in table.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        links = []
        if len(cells) < 2:
            raise FetchError("UPSTREAM_PARSE_ERROR", "A Codeforces problem row is unrecognized.")
        for link in cells[1].find_all("a", href=True):
            href = absolute(link["href"], page.url)
            match = re.fullmatch(rf"/{category}/{contest_id}/problem/([^/]+)", urlsplit(href or "").path)
            if match:
                links.append((link, match[1]))
        if not links:
            raise FetchError("UPSTREAM_PARSE_ERROR", "A Codeforces problem row is unrecognized.")
        link, index = links[-1]
        problems.append(summary(problem_key(category, contest_id, index), clean(link),
                                f"https://codeforces.com/{category}/{contest_id}/problem/{index}", index))
    if not problems:
        raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces' problems are empty or unreleased.")
    return problems


def parse_materials(page):
    soup, items = page.soup(), []
    parent = re.match(r"^/(contest|gym)/([1-9]\d*)(?:/|$)", urlsplit(page.url).path)
    if parent:
        category, contest_id = parent.groups()
        print_path = f"/{category}/{contest_id}/problems"
        for link in soup.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            parts = urlsplit(href or "")
            if parts.hostname == "codeforces.com" and parts.path.rstrip("/") == print_path:
                items.append(material(href, "Problem statements", role="statement", kind="html",
                                      key=f"cf:print:{category}:{contest_id}", official=True))
    for text in soup.find_all(string=re.compile(r"Contest materials", re.I)):
        panel = text.find_parent(class_="roundbox") or text.parent.parent
        for link in panel.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            if not href:
                continue
            path = urlsplit(href).path
            blog = re.fullmatch(r"/blog/entry/(\d+)", path)
            title = clean(link) or link.get("title") or "Material"
            if blog or "/attachments/download/" in path:
                items.append(material(href, title, kind="html" if blog else None,
                                      key=f"cf:blog:{blog[1]}" if blog else None))
    for link in soup.find_all("a", href=True):
        href = absolute(link["href"], page.url)
        if href and "/attachments/download/" in urlsplit(href).path:
            items.append(material(href, clean(link) or link.get("title") or "Attachment"))
    return unique_materials(items)


class CodeforcesSource:
    def __init__(self, transport):
        self.transport = transport

    def metadata(self, request, context):
        metadata_error = None
        if request.category == "contest":
            try:
                # Public regular contests accept exactly contestId, without pagination/auth.
                page = self.transport.get(f"https://codeforces.com/api/contest.standings?contestId={request.native_id}", context)
                value = api_result(page)
                native = value.get("contest") if isinstance(value, dict) else None
                if not native or native.get("id") != request.native_id:
                    raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces returned a different contest.")
                data = parse_api_contest(native, request.category)
                native_problems = value.get("problems")
                if isinstance(native_problems, list) and native_problems:
                    data["problems"] = [api_problem(p, request.category, request.native_id) for p in native_problems]
                    data["problemCount"] = len(data["problems"])
                return data
            except FetchError as error:
                if error.status == 404:
                    raise
                metadata_error = error
        catalog = "https://codeforces.com/api/contest.list?gym=" + ("true" if request.category == "gym" else "false")
        native_list = api_result(self.transport.get(catalog, context))
        if not isinstance(native_list, list):
            raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces' contest catalogue is invalid.")
        native = next((entry for entry in native_list if entry.get("id") == request.native_id), None)
        if native is None:
            if metadata_error:
                raise metadata_error
            raise FetchError("UPSTREAM_AUTH_REQUIRED", "The contest is unavailable in Codeforces' public catalogue.", 403)
        return parse_api_contest(native, request.category)

    def contest(self, request, context):
        try:
            data = self.metadata(request, context)
        except FetchError as error:
            # Gym contest.list can stall even while the public gym page and its
            # complete task table are reachable. Recover the task list from the
            # page, while retaining a warning about missing API metadata.
            if request.category != 'gym' or error.code not in {
                    'UPSTREAM_TIMEOUT', 'UPSTREAM_UNAVAILABLE', 'UPSTREAM_AUTH_REQUIRED'}:
                raise
            page = self.transport.get(request.url + '?locale=en', context)
            title = page.soup().title
            match = re.fullmatch(r'(?:Dashboard|Problems) - (.+) - Codeforces',
                                 clean(title) if title else '')
            if not match:
                raise error
            data = contest(f'cf:gym:{request.native_id}', 'cf', request.native_id,
                           match[1], request.url, 'gym')
            data['problems'] = parse_html_contest(page, 'gym', request.native_id)
            data['problemCount'] = len(data['problems'])
            data['materials'] = parse_materials(page)
            context.warn('CONTEST_METADATA_UNAVAILABLE', 'cf',
                         'Codeforces API metadata was unavailable; the complete gym task table was read from HTML.')
            return data
        page = None
        try:
            page = self.transport.get(data["url"] + "?locale=en", context)
            if data["problems"] is None:
                data["problems"] = parse_html_contest(page, request.category, request.native_id)
                data["problemCount"] = len(data["problems"])
            data["materials"] = parse_materials(page)
        except FetchError as error:
            context.warn("MATERIALS_UNAVAILABLE", "data.materials", str(error))
        if data["problems"] is None:
            context.warn("PROBLEMS_UNAVAILABLE", "data.problems", "The complete Codeforces problem list is unavailable.")
        if request.category == "gym" and page is not None:
            try:
                attachments = self.transport.get(data["url"] + "/attachments?locale=en", context)
                data["materials"] = unique_materials((data["materials"] or []) + parse_materials(attachments))
            except FetchError as error:
                context.warn("MATERIALS_UNAVAILABLE", "data.materials", str(error))
        return data

    def problem(self, request, context):
        parent = self.metadata(request, context)
        item = next((p for p in parent["problems"] or [] if p["index"] == request.index), None)
        if parent["problems"] is not None and item is None:
            raise FetchError("PROBLEM_NOT_FOUND", "Codeforces confirms that this problem is absent from the contest.", 404)
        page, error = None, None
        urls = [request.url + "?locale=en"]
        if request.category == "contest":
            urls.append(f"https://codeforces.com/problemset/problem/{request.native_id}/{request.index}?locale=en")
        for url in urls:
            try:
                page = self.transport.get(url, context)
                if urlsplit(page.url).path != urlsplit(url).path:
                    raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces redirected to a different problem.")
                if page.text.startswith("%PDF-"):
                    break
                if page.soup().select_one(".problem-statement") is None:
                    raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces' problem statement is missing.")
                break
            except FetchError as caught:
                page, error = None, caught
        if page is None:
            if item is None:
                raise error or FetchError("UPSTREAM_PARSE_ERROR", "Codeforces problem metadata is unavailable.")
            data = full_problem(deepcopy(item), "cf")
            data["contest"] = contest_ref(parent)
            context.warn("STATEMENT_UNAVAILABLE", "data.statement", str(error))
            context.warn("MATERIALS_UNAVAILABLE", "data.materials", "Codeforces' material links could not be examined.")
            return data
        if page.text.startswith("%PDF-"):
            if item is None:
                raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces' PDF task is absent from its contest list.")
            data = full_problem(deepcopy(item), "cf")
            data["contest"] = contest_ref(parent)
            descriptor = material(request.url, "Problem statement", role="statement", kind="pdf",
                                  scope="problem", problem_key=data["key"], official=True)
            data["materials"] = [descriptor]
            data["statement"] = document_statement([descriptor["key"]], "en")
            return data
        soup = page.soup()
        block = soup.select_one(".problem-statement")
        title = clean(block.select_one(".title"))
        expected = re.match(r"^([^.]*)\.\s*(.+)$", title)
        if expected is None or expected[1] != request.index:
            raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces returned a different problem statement.")
        if item is None:
            item = summary(problem_key(request.category, request.native_id, request.index), expected[2],
                           request.url, request.index)
        data = full_problem(deepcopy(item), "cf")
        data["contest"] = contest_ref(parent)
        raw_time, raw_memory = None, None
        for css, target in [(".time-limit", "time"), (".memory-limit", "memory")]:
            element = block.select_one(css)
            if element:
                clone = deepcopy(element)
                for label in clone.select(".property-title"):
                    label.decompose()
                if target == "time":
                    raw_time = clean(clone)
                else:
                    raw_memory = clean(clone)
        data["limits"] = limits(raw_time, raw_memory)
        for side in ["input", "output"]:
            element = block.select_one("." + side + "-file")
            if element:
                clone = deepcopy(element)
                for label in clone.select(".property-title"):
                    label.decompose()
                text = clean(clone)
                data["io"][side] = {"type": "standard" if text == "standard " + side else "file",
                                    "fileName": None if text == "standard " + side else text}
        if re.search(r"This is an interactive problem|This problem is interactive", clean(block), re.I):
            data.update(taskMode="interactive", interactive=True)
        elif all(data["io"][side]["type"] == "standard" for side in ["input", "output"]):
            data.update(taskMode="batch", interactive=False)
        data["materials"] = parse_materials(page)
        frame = block.find(["iframe", "object"])
        if frame:
            href = frame.get("src") or frame.get("data")
            descriptor = material(href, "Statement document", base=page.url, role="statement",
                                  scope="problem", problem_key=data["key"])
            if descriptor:
                data["materials"].append(descriptor)
                data["statement"] = document_statement([descriptor["key"]])
        else:
            body = deepcopy(block)
            for header in body.select(".header"):
                header.decompose()
            if clean(body) or body.find("img"):
                data["statement"] = statement(body, page.url, "en")
                data["materials"].append(material(request.url, "Problem statement", role="statement",
                                                  kind="html", scope="problem",
                                                  problem_key=data["key"], official=True))
                data["samples"] = samples(block, "cf")
                infer_task(data, body, page.url, "cf")
            else:
                documents = [m for m in data["materials"] if m["role"] == "statement" and m["type"] == "pdf"]
                if documents:
                    languages = {m["language"] for m in documents}
                    data["statement"] = document_statement([m["key"] for m in documents],
                                                           next(iter(languages)) if len(languages) == 1 else None)
                    context.warn("CONTEST_STATEMENT_DOCUMENT", "data.statement",
                                 "The task body is empty; the source links a contest-wide statement document.", partial=False)
        if data["statement"] is None:
            context.warn("STATEMENT_UNAVAILABLE", "data.statement", "Codeforces' statement representation is unsupported.")
        data["materials"] = unique_materials(data["materials"])
        return data
