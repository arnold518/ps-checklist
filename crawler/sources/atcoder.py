"""AtCoder contest/task collection from published top, task, and editorial pages."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, unquote, urlsplit

from ..contracts import FetchError, contest, contest_ref, full_problem, summary
from ..markup import (absolute, clean, infer_task, language, limits, material,
                      material_role, number, samples, statement, unique_materials)


def task_key(contest_id, task_id):
    return f"atcoder:contest:{contest_id}:{task_id}"


def require_page(page, expected):
    path = urlsplit(page.url).path.rstrip("/")
    if path == "/login":
        raise FetchError("UPSTREAM_AUTH_REQUIRED", "AtCoder requires login for this resource.", 403)
    if path != expected:
        raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder redirected to a different resource.")


def schedule(soup):
    times = soup.select(".contest-duration time") or soup.select("time.fixtime-full") or soup.select("time")[:2]
    if len(times) < 2:
        return None, None
    try:
        values = [datetime.fromisoformat(clean(t)).astimezone(timezone.utc) for t in times[:2]]
        return values[0], values[1]
    except ValueError:
        return None, None


def parse_top(page, contest_id):
    require_page(page, f"/contests/{contest_id}")
    soup = page.soup()
    title = clean(soup.title)
    if not title or "AtCoder" not in title:
        raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder contest metadata is missing.")
    name = re.sub(r"\s*-\s*AtCoder$", "", title)
    data = contest(f"atcoder:contest:{contest_id}", "atcoder", contest_id, name,
                   f"https://atcoder.jp/contests/{contest_id}")
    data["scoringType"] = "ATCODER"
    start, end = schedule(soup)
    if start and end:
        data.update(startTime=start.isoformat().replace("+00:00", "Z"),
                    endTime=end.isoformat().replace("+00:00", "Z"),
                    durationSeconds=int((end - start).total_seconds()))
        now = datetime.now(timezone.utc)
        data["phase"] = "BEFORE" if now < start else "CODING" if now < end else "FINISHED"
    content = soup.select_one("#contest-statement") or soup.select_one("#main-container") or soup
    text = clean(content)
    writers = []
    for item in content.find_all("li"):
        if re.match(r"^(?:Writer|Writers|writer|問題作成者)\s*[:：]", clean(item)):
            writers.extend(clean(a) for a in item.select('a[href^="/users/"]'))
    rated = re.search(r"Rated Range\s*[:：]\s*(\d+)\s*[-–]\s*(\d+|inf)", text, re.I)
    is_rated = True if rated else False if re.search(r"(?:Rated Range\s*[:：]\s*[-－]|unrated|対象外|レーティング対象外)", text, re.I) else None
    penalty = re.search(r"(?:penalty|ペナルティ).{0,70}?(\d+)\s*(?:minutes?|分)", text, re.I)
    data["details"] = {
        "isRated": is_rated,
        "ratedRange": {"min": int(rated[1]), "max": None if rated[2].lower() == "inf" else int(rated[2])} if rated else None,
        "penaltySeconds": int(penalty[1]) * 60 if penalty else None,
        "writers": list(dict.fromkeys(writers)) or None,
    }
    scores = {}
    for table in content.find_all("table"):
        rows = table.find_all("tr")
        if rows and any(word in clean(rows[0]) for word in ["Score", "点数", "配点"]):
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) == 2 and number(clean(cells[1])) is not None:
                    scores[clean(cells[0])] = number(clean(cells[1]))
    return data, scores, soup


def parse_tasks(page, contest_id, scores=None):
    require_page(page, f"/contests/{contest_id}/tasks")
    soup = page.soup()
    result = []
    table = soup.select_one("table")
    if table is None:
        raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's complete task table is unavailable.")
    for row in table.select("tbody tr") or table.find_all("tr")[1:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 4:
            if row.find("td"):
                raise FetchError("UPSTREAM_PARSE_ERROR", "An AtCoder task row is unrecognized.")
            continue
        link = cells[1].find("a", href=True)
        if link is None:
            raise FetchError("UPSTREAM_PARSE_ERROR", "An AtCoder task link is missing.")
        path = urlsplit(absolute(link["href"], page.url) or "").path
        match = re.fullmatch(rf"/contests/{re.escape(contest_id)}/tasks/([A-Za-z0-9_-]+)", path)
        if match is None:
            raise FetchError("UPSTREAM_PARSE_ERROR", "An AtCoder task identity is invalid.")
        task_id, index = match[1], clean(cells[0])
        item = summary(task_key(contest_id, task_id), clean(link), "https://atcoder.jp" + path,
                       index=index, task_id=task_id)
        item.update(type="PROGRAMMING", points=(scores or {}).get(index),
                    limits=limits(clean(cells[2]), clean(cells[3])))
        result.append(item)
    if not result:
        raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's task list is empty or unreleased.")
    return result, soup


def parse_editorials(page, contest_id, tasks):
    require_page(page, f"/contests/{contest_id}/editorial")
    soup, result = page.soup(), []
    sections = soup.select(".editorial-section")
    if not sections and not re.search(r"(?:no editorial|解説はまだ)", clean(soup), re.I):
        raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's editorial index is unrecognized.")
    known = {task["taskId"]: task["key"] for task in tasks or []}
    for section in sections:
        heading = section.find_previous(["h2", "h3", "h4"])
        task_link = heading.find("a", href=re.compile(r"/tasks/")) if heading else None
        target = None
        if task_link:
            match = re.fullmatch(rf"/contests/{re.escape(contest_id)}/tasks/([A-Za-z0-9_-]+)",
                                 urlsplit(task_link["href"]).path)
            if match is None:
                raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's editorial task identity is invalid.")
            task_id = match[1]
            target = known.get(task_id, task_key(contest_id, task_id))
        for link in section.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            if not href:
                continue
            row = link.find_parent("li") or link.parent
            official = True if re.search(r"\bOfficial\b", clean(row)) else None
            user = row.find("a", href=re.compile(r"^/users/"))
            author = clean(user) if user else None
            entry_language = language(clean(link))
            for ancestor in [link] + list(link.parents):
                classes = ancestor.get("class", [])
                if "lang-en" in classes:
                    entry_language = "en"
                    break
                if "lang-ja" in classes:
                    entry_language = "ja"
                    break
            match = re.fullmatch(r"/contests/[^/]+/editorial/(\d+)", urlsplit(href).path)
            if match:
                result.append(material(href, clean(link), role="editorial", kind="html",
                                       scope="problem" if target else "contest", problem_key=target,
                                       key=f"atcoder:editorial:{match[1]}", lang=entry_language,
                                       official=official, author=author))
            elif urlsplit(href).path == "/jump":
                destination = parse_qs(urlsplit(href).query).get("url", [None])[0]
                if destination and urlsplit(destination).hostname == "www2.ioi-jp.org":
                    descriptor = material(destination, clean(link) or "Official material index",
                                          role="materials_index", kind="html", official=official,
                                          posted_by=author, scope="problem" if target else "contest",
                                          problem_key=target)
                    if descriptor:
                        descriptor["originalUrl"] = href
                        result.append(descriptor)
    if result:
        result.insert(0, material(page.url, "Editorial index", role="editorial", kind="html",
                                  key=f"atcoder:editorial-index:{contest_id}", official=True))
    return unique_materials(result)


def print_material(pages, contest_id):
    for soup in pages:
        link = soup.find("a", href=re.compile(rf"^/contests/{re.escape(contest_id)}/tasks_print(?:\?|$)"))
        if link:
            return material(link["href"], clean(link) or "Tasks for printing", base="https://atcoder.jp",
                            role="statement", kind="html", key=f"atcoder:print:{contest_id}", official=True)
    return None


class AtCoderSource:
    def __init__(self, transport):
        self.transport = transport

    def contest(self, request, context):
        root = f"https://atcoder.jp/contests/{request.native_id}"
        top = self.transport.get(root + "?lang=en", context)
        data, scores, top_soup = parse_top(top, request.native_id)
        pages = [top_soup]
        try:
            tasks_page = self.transport.get(root + "/tasks?lang=en", context)
            data["problems"], tasks_soup = parse_tasks(tasks_page, request.native_id, scores)
            data["problemCount"] = len(data["problems"])
            pages.append(tasks_soup)
        except FetchError as error:
            context.warn("PROBLEMS_UNAVAILABLE", "data.problems", str(error))
        try:
            page = self.transport.get(root + "/editorial?lang=" + request.lang, context)
            data["materials"] = parse_editorials(page, request.native_id, data["problems"])
        except FetchError as error:
            context.warn("MATERIALS_UNAVAILABLE", "data.materials", str(error))
        printable = print_material(pages, request.native_id)
        if printable:
            data["materials"] = unique_materials([printable] + (data["materials"] or []))
        if request.external:
            self.external_materials(data, context)
        return data

    def problem(self, request, context):
        previous_warnings = len(context.warnings)
        try:
            parent = self.contest(replace(request, entity="contest", index=None, external=False), context)
        finally:
            for warning in context.warnings[previous_warnings:]:
                if warning["field"] == "data.problems":
                    warning["field"] = "data.contest"
        task = next((p for p in parent["problems"] or [] if p["taskId"] == request.index), None)
        page = self.transport.get(request.url + "?lang=" + request.lang, context)
        require_page(page, f"/contests/{request.native_id}/tasks/{request.index}")
        soup = page.soup()
        container = soup.select_one("#task-statement")
        if container is None:
            raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's task statement is missing.")
        if task is None:
            header = soup.select_one("#main-container h3")
            title = clean(header) or clean(soup.title)
            match = re.match(r"^(.+?)\s*[-–]\s*(.+)$", title)
            if match is None:
                raise FetchError("UPSTREAM_PARSE_ERROR", "AtCoder's task identity is missing.")
            task = summary(task_key(request.native_id, request.index), match[2], request.url,
                           index=match[1], task_id=request.index)
            task["type"] = "PROGRAMMING"
        data = full_problem(deepcopy(task), "atcoder")
        data["contest"] = contest_ref(parent)
        data["materials"] = [m for m in parent["materials"] or [] if m["scope"] == "contest" or m["problemKey"] == data["key"]]
        available = [lang for lang in ["en", "ja"] if container.select_one(".lang-" + lang)]
        selected_lang = request.lang
        selected = container.select_one(".lang-" + selected_lang)
        if selected is None and available:
            selected_lang = available[0]
            selected = container.select_one(".lang-" + selected_lang)
            context.warn("LANGUAGE_FALLBACK", "data.statement.language", "The requested statement language is unavailable.")
        if selected is None:
            selected = container
            selected_lang = None
            context.warn("LANGUAGE_FALLBACK", "data.statement.language", "The source did not identify the statement language.")
        variants = [{"sourceId": lang, "language": lang, "url": request.url + "?lang=" + lang, "format": "html"} for lang in available]
        data["statement"] = statement(selected, page.url, selected_lang, available or None, variants or None)
        data["samples"] = samples(selected, "atcoder")
        score = re.search(r"(?:Score\s*[:：]|配点\s*[:：])\s*(\d+(?:\.\d+)?)", clean(selected), re.I)
        if score:
            data["points"] = number(score[1])
        page_text = clean(soup.select_one("#main-container") or soup)
        match = re.search(r"Time Limit:\s*([^/]+)\s*/\s*Memory Limit:\s*([^\n]+?)(?=Score|配点|$)", page_text)
        if match:
            raw_time = re.search(r"[\d.]+\s*(?:sec|s)", match[1])
            raw_memory = re.search(r"[\d.]+\s*(?:MiB|MB)", match[2])
            if raw_time or raw_memory:
                data["limits"] = limits(raw_time[0] if raw_time else None, raw_memory[0] if raw_memory else None)
        infer_task(data, selected, page.url, "atcoder")
        if data["taskMode"] == "library" and re.search(r"sample grader|サンプル.*採点", clean(selected), re.I):
            for example in data["samples"]:
                example["kind"] = "grader"
        for link in selected.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            if href and urlsplit(href).path.lower().endswith((".zip", ".pdf", ".cpp", ".h")):
                role = "grader" if href.lower().endswith(".zip") and data["taskMode"] == "library" else material_role(clean(link))
                descriptor = material(href, clean(link) or unquote(urlsplit(href).path.rsplit("/", 1)[-1]),
                                      scope="problem", problem_key=data["key"], role=role, official=True)
                data["materials"].append(descriptor)
        data["materials"] = unique_materials(data["materials"])
        if request.external:
            external_parent = deepcopy(parent)
            self.external_materials(external_parent, context)
            data["materials"] = unique_materials(data["materials"] + [m for m in external_parent["materials"] or []
                                               if m["scope"] == "contest" or m["problemKey"] == data["key"]])
        return data

    def external_materials(self, data, context):
        for index in list(data["materials"] or []):
            if index["role"] != "materials_index":
                continue
            try:
                page = self.transport.get(index["url"], context)
                if urlsplit(page.url).hostname != "www2.ioi-jp.org":
                    raise FetchError("UPSTREAM_PARSE_ERROR", "Unsupported external material index.")
                additions = parse_joi_index(page, data["problems"] or [])
                data["materials"] = unique_materials((data["materials"] or []) + additions)
            except FetchError as error:
                context.warn("EXTERNAL_MATERIALS_UNAVAILABLE", "data.materials", str(error))


def parse_joi_index(page, tasks):
    def normalized(text):
        return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()
    names = {}
    for task in tasks:
        names[task["key"]] = [normalized(part) for part in re.split(r"[()（）]", task["name"]) if len(normalized(part)) > 3]
    result = []
    soup = page.soup()
    for row in soup.find_all("tr"):
        text = normalized(clean(row))
        targets = [key for key, variants in names.items() if any(name in text for name in variants)]
        if len(targets) != 1:
            continue
        for link in row.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            if not href or not urlsplit(href).path.lower().endswith((".pdf", ".zip", ".cpp", ".c")):
                continue
            if "/practice/" in urlsplit(href).path:
                continue
            filename = urlsplit(href).path.rsplit("/", 1)[-1]
            label = clean(link) or filename
            lang = "en" if re.search(r"(?:-en|_en)\.pdf$", filename) or label == "English" else language(label)
            if "review" in filename.lower():
                role = "editorial"
            elif re.search(r"[-_]sample\.(?:cpp|c)$", filename, re.I):
                role = "sample_code"
            elif re.search(r"[-_]data\.zip$", filename, re.I):
                role = "test_data"
            elif re.search(r"[-_](?:dist|cms)\.zip$", filename, re.I):
                role = "grader"
            elif filename.lower().endswith(".pdf") and material_role(label) == "other":
                role = "statement"
            else:
                role = material_role(label)
            item = material(href, label or filename, scope="problem", problem_key=targets[0],
                            role=role, lang=lang, official=True)
            if filename.lower().endswith((".cpp", ".c")):
                item["type"] = "other"
                item["fileName"] = filename
            result.append(item)
    return unique_materials(result)
