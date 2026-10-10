"""One-level QOJ categories, contest memberships, and versioned problem statements."""

from dataclasses import replace
import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from ..contracts import FetchError, contest, contest_ref, full_problem, summary
from ..markup import (absolute, clean, document_statement, infer_task, limits,
                      material, number, samples, sanitize, statement, unique_materials)


def category_ref(link, base):
    url = absolute(link.get("href"), base)
    match = re.fullmatch(r"/category(?:/([1-9]\d*))?", urlsplit(url or "").path)
    if not match:
        return None
    native_id = int(match[1] or 1)
    return {"key": f"qoj:category:{native_id}", "categoryId": native_id,
            "name": clean(link), "url": f"https://qoj.ac/category/{native_id}"}


def root_content(page, suffix):
    soup = page.soup()
    title = clean(soup.title)
    if not title.endswith(suffix):
        raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ did not return the expected resource page.")
    content = soup.select_one(".uoj-content")
    if content is None:
        raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's resource content is missing.")
    return soup, content, title[:-len(suffix)].strip()


def published_count(cell):
    text = clean(cell)
    if not text:
        return None
    # Authenticated views prepend personal solved counts. Never expose them.
    total = text.rsplit("/", 1)[-1].strip()
    return number(total)


def parse_category(page, native_id, context=None):
    soup, content, name = root_content(page, " - QOJ.ac")
    heading = content.find("h2")
    if not heading or not clean(heading).startswith("Category:"):
        raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's category identity is missing.")
    name = clean(heading).split(":", 1)[1].strip()
    breadcrumbs = []
    for row in content.select("div.row"):
        if "Location:" in clean(row):
            for link in row.find_all("a", href=True):
                if clean(link) == "Back":
                    continue
                ref = category_ref(link, page.url)
                if ref:
                    breadcrumbs.append(ref)
            break
    data = {"key": f"qoj:category:{native_id}", "source": "qoj", "categoryId": native_id,
            "name": name, "url": f"https://qoj.ac/category/{native_id}",
            "parent": breadcrumbs[-2] if len(breadcrumbs) > 1 else None,
            "breadcrumbs": breadcrumbs or None,
            "counts": dict.fromkeys(["directCategories", "directContests", "reportedProblems", "uniqueProblems"]),
            "sections": None}
    try:
        return category_listing(content, page, data)
    except FetchError as error:
        if context is None:
            raise
        context.warn("CATEGORY_ENTRIES_UNAVAILABLE", "data.sections", str(error))
        return data


def category_listing(content, page, data):
    tables = content.select("table.category-admin-table")
    if not tables:
        if re.search(r"(?:no (?:subcategories|contests|entries)|empty category)", clean(content), re.I):
            data["sections"] = []
            data["counts"] = {"directCategories": 0, "directContests": 0,
                              "reportedProblems": 0, "uniqueProblems": 0}
            return data
        raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's category listing is unrecognized.")
    sections, entries = [], []
    for table in tables:
        heading = table.find_previous("h3")
        title = clean(heading) if heading and heading in content.descendants else None
        section = {"title": title, "entries": []}
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue
            if len(cells) < 4:
                raise FetchError("UPSTREAM_PARSE_ERROR", "A QOJ category row is unrecognized.")
            link = cells[0].find("a", href=True)
            url = absolute(link["href"], page.url) if link else None
            match = re.fullmatch(r"/(category|contest)/([1-9]\d*)", urlsplit(url or "").path)
            if not match:
                raise FetchError("UPSTREAM_PARSE_ERROR", "A QOJ category child link is invalid.")
            kind, child_id = match[1], int(match[2])
            indices = [clean(badge) for badge in cells[1].select(".badge") if clean(badge)]
            refs = []
            for preview in cells[1].find_all("a", href=True):
                target = absolute(preview["href"], page.url)
                membership = re.fullmatch(r"/contest/(\d+)/problem/(\d+)", urlsplit(target or "").path)
                global_problem = re.fullmatch(r"/problem/(\d+)", urlsplit(target or "").path)
                if not membership and not global_problem:
                    continue
                problem_id = int(membership[2] if membership else global_problem[1])
                contest_id = int(membership[1]) if membership else child_id if kind == "contest" else None
                ref = {"key": f"qoj:problem:{problem_id}", "problemId": problem_id,
                       "index": clean(preview), "url": f"https://qoj.ac/problem/{problem_id}",
                       "contextUrl": f"https://qoj.ac/contest/{contest_id}/problem/{problem_id}" if contest_id else None}
                if contest_id:
                    ref["membershipKey"] = f"qoj:contest:{contest_id}:{problem_id}"
                refs.append(ref)
            entry = {"type": kind, "key": f"qoj:{kind}:{child_id}",
                     "categoryId" if kind == "category" else "contestId": child_id,
                     "label": clean(link), "url": f"https://qoj.ac/{kind}/{child_id}",
                     "reportedCounts": {"contests": published_count(cells[2]), "problems": published_count(cells[3])},
                     "problemIndices": indices or None, "problemRefs": refs or None}
            section["entries"].append(entry)
            entries.append(entry)
        sections.append(section)
    data["sections"] = sections
    totals = [entry["reportedCounts"]["problems"] for entry in entries]
    all_ids = all(entry["problemRefs"] is not None and len(entry["problemRefs"]) == entry["reportedCounts"]["problems"] for entry in entries)
    data["counts"] = {"directCategories": sum(e["type"] == "category" for e in entries),
                      "directContests": sum(e["type"] == "contest" for e in entries),
                      "reportedProblems": sum(totals) if all(total is not None for total in totals) else None,
                      "uniqueProblems": len({ref["problemId"] for e in entries for ref in e["problemRefs"] or []}) if all_ids else None}
    return data


def membership(problem_id, contest_id, name, index):
    item = summary(f"qoj:problem:{problem_id}", name, f"https://qoj.ac/problem/{problem_id}", index)
    item.update(problemId=problem_id, membershipKey=f"qoj:contest:{contest_id}:{problem_id}",
                contextUrl=f"https://qoj.ac/contest/{contest_id}/problem/{problem_id}")
    return item


def parse_contest(page, native_id, context):
    soup, content, name = root_content(page, " - Dashboard - Contest - QOJ.ac")
    data = contest(f"qoj:contest:{native_id}", "qoj", native_id, name,
                   f"https://qoj.ac/contest/{native_id}")
    breadcrumbs = []
    for panel in content.select(".alert-secondary"):
        for link in panel.find_all("a", href=True):
            ref = category_ref(link, page.url)
            if ref:
                breadcrumbs.append(ref)
    data["details"] = {"breadcrumbs": breadcrumbs or None, "parentCategory": breadcrumbs[-1] if breadcrumbs else None,
                       "descriptionHtml": None, "rules": None}
    for header in content.select(".card-header"):
        label = clean(header)
        if label == "Contest Ended":
            data["phase"] = "FINISHED"
        elif label in {"Contest In Progress", "Contest in Progress"}:
            data["phase"] = "CODING"
        elif label in {"Contest Not Started", "Contest has not started"}:
            data["phase"] = "BEFORE"
    rules_heading = next((h for h in content.find_all("h4") if clean(h).startswith("Ruleset:")), None)
    if rules_heading:
        raw = clean(rules_heading).split(":", 1)[1].strip()
        rules_text = clean(rules_heading.parent)
        penalty = re.search(r"(?:penalty(?: time)?\s*[:：]?\s*)(\d+)\s*(?:minutes?|mins?|minute\(s\))", rules_text, re.I)
        submission = re.search(r"(?:submission[^.]*?limit[^\d]*)(\d+)", rules_text, re.I)
        freeze = re.search(r"(?:frozen|freeze)[^.]*?(?:after|at)\s*(\d+(?:\.\d+)?)\s*(hours?|minutes?)", rules_text, re.I)
        freeze_clock = re.search(r"(?:frozen|freeze)[^.]*?(?:after|at)\s*(\d+):(\d\d):(\d\d)", rules_text, re.I)
        data["scoringType"] = raw if raw in {"ICPC", "IOI", "UOJ"} else None
        data["details"]["rules"] = {
            "rawRuleset": raw, "penaltySeconds": int(penalty[1]) * 60 if penalty else None,
            "datasetMode": "full" if re.search(r"full (?:data|dataset)", rules_text, re.I) else "pretest" if re.search(r"pretest", rules_text, re.I) else None,
            "submissionLimitPerProblem": int(submission[1]) if submission else None,
            "scoreboardAvailable": True if re.search(r"scoreboard.*(?:available|enabled)", rules_text, re.I) else None,
            "scoreboardFreezeAfterSeconds": (int(freeze_clock[1]) * 3600 + int(freeze_clock[2]) * 60 + int(freeze_clock[3])) if freeze_clock else int(float(freeze[1]) * (3600 if freeze[2].lower().startswith("hour") else 60)) if freeze else None,
        }
    for article in content.select("article.top-buffer-md"):
        if article.find_parent(class_="col-sm-9"):
            value, _ = sanitize(article, page.url)
            if clean(article):
                data["details"]["descriptionHtml"] = value
                break
    table = None
    for candidate in content.find_all("table"):
        headings = [clean(th) for th in candidate.select("th")]
        if headings[:2] == ["#", "Problem"]:
            table = candidate
            break
    try:
        if table is None:
            raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's complete contest problem table is unavailable.")
        problems = []
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue
            if len(cells) < 2:
                raise FetchError("UPSTREAM_PARSE_ERROR", "A QOJ contest problem row is unrecognized.")
            link = cells[1].find("a", href=True)
            href = absolute(link["href"], page.url) if link else None
            match = re.fullmatch(rf"/contest/{native_id}/problem/([1-9]\d*)", urlsplit(href or "").path)
            if match is None:
                raise FetchError("UPSTREAM_PARSE_ERROR", "A QOJ contest problem identity is invalid.")
            problems.append(membership(int(match[1]), native_id, clean(link), clean(cells[0])))
        if not problems:
            raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's contest problems are empty or unreleased.")
        data.update(problems=problems, problemCount=len(problems))
    except FetchError as error:
        context.warn("PROBLEMS_UNAVAILABLE", "data.problems", str(error))
    attachments = []
    for link in content.find_all("a", href=True):
        href = absolute(link["href"], page.url)
        query = parse_qs(urlsplit(href or "").query)
        if query.get("type") == ["attachments"] and query.get("id") == [str(native_id)]:
            attachments.append(material(href, clean(link)))
    data["materials"] = unique_materials(attachments)
    return data


def problem_metadata(page, problem_id):
    soup, content, name = root_content(page, " - Problem - QOJ.ac")
    data = full_problem(summary(f"qoj:problem:{problem_id}", name,
                                f"https://qoj.ac/problem/{problem_id}"), "qoj")
    raw_time, raw_memory, difficulty = None, None, None
    flags = []
    badge_row = content.select_one(".row.d-flex.justify-content-center")
    for badge in badge_row.select(".badge") if badge_row else []:
        text = clean(badge)
        if text.startswith("Time Limit:"):
            raw_time = text.split(":", 1)[1].strip()
        elif text.startswith("Memory Limit:"):
            raw_memory = text.split(":", 1)[1].strip()
        elif text.startswith("Total points:"):
            data["points"] = number(text.split(":", 1)[1].strip())
        elif text.startswith("Difficulty:"):
            raw = text.split(":", 1)[1].replace("[show]", "").strip()
            difficulty = {"value": number(raw), "raw": raw, "scale": None} if raw else None
        elif text:
            flags.append(text)
    data.update(problemId=problem_id, sourceFlags=flags if badge_row else None,
                details={"difficulty": difficulty}, limits=limits(raw_time, raw_memory),
                contests=None, membershipKey=None, contextUrl=None)
    flag_modes = {"Interactive": "interactive", "Communication": "communication", "Output Only": "output_only", "Output-only": "output_only"}
    for flag in flags:
        if flag in flag_modes:
            data["taskMode"] = flag_modes[flag]
            if flag == "Interactive":
                data["interactive"] = True
    for panel in content.select(".alert-primary"):
        if "used in the following contests" not in clean(panel):
            continue
        usages = []
        for link in panel.find_all("a", href=True):
            href = absolute(link["href"], page.url)
            match = re.fullmatch(r"/contest/([1-9]\d*)", urlsplit(href or "").path)
            if match:
                contest_id = int(match[1])
                usages.append({"key": f"qoj:contest:{contest_id}", "contestId": contest_id,
                               "name": clean(link), "url": f"https://qoj.ac/contest/{contest_id}",
                               "index": None, "membershipKey": f"qoj:contest:{contest_id}:{problem_id}",
                               "contextUrl": f"https://qoj.ac/contest/{contest_id}/problem/{problem_id}"})
        data["contests"] = usages
        break
    restriction = next((panel for panel in content.select(".alert-info") if "available in the following languages" in clean(panel)), None)
    if restriction:
        ids = []
        for script in soup.find_all("script"):
            if "source_code_form_group" not in script.get_text():
                continue
            fragment = script.get_text().split("source_code_form_group", 1)[1]
            fragment = re.split(r"</select>|<\\/select>", fragment, maxsplit=1)[0]
            fragment = fragment.replace('\\"', '"').replace("<\\/option>", "</option>")
            for option in BeautifulSoup(fragment, "html.parser").select("option[value]"):
                if option["value"] not in ids:
                    ids.append(option["value"])
            if ids:
                break
        data["submission"] = {"availableLanguages": ids or [clean(tag) for tag in restriction.find_all("b")],
                              "requiredFiles": None, "requiredHeaders": None,
                              "instructionsHtml": sanitize(restriction, page.url)[0]}
    return data, soup, content


def variants(content, page_url, problem_id):
    result, seen = [], set()
    path = urlsplit(page_url).path.split("/statement/")[0]
    frame = content.select_one("#tab-statement iframe")
    article = content.select_one("#tab-statement article")
    for link in content.find_all("a", href=True):
        href = absolute(link["href"], page_url)
        if not href or "locale" in parse_qs(urlsplit(href).query):
            continue
        match = re.fullmatch(re.escape(path) + r"/statement/([A-Za-z0-9_-]+)", urlsplit(href).path)
        if not match or match[1] in seen:
            continue
        source_id = match[1]
        seen.add(source_id)
        lang = {"en": "en", "ja": "ja", "zh_cn": "zh-CN", "default": None}.get(source_id)
        result.append({"sourceId": source_id, "language": lang, "url": href,
                       "format": ("document" if frame else "html" if article else None) if source_id == "default" else None})
    return result


def problem_materials(content, page_url, problem_key):
    items = []
    for link in content.find_all("a", href=True):
        href = absolute(link["href"], page_url)
        query = parse_qs(urlsplit(href or "").query)
        if query.get("type") == ["problem"]:
            items.append(material(href, clean(link) or "Attachments", scope="problem", problem_key=problem_key))
    for table in content.find_all("table"):
        headers = [clean(item) for item in table.select("th")]
        if "Posted By" not in headers or "Title" not in headers:
            continue
        for row in table.select("tbody tr") or table.find_all("tr")[1:]:
            cells = row.find_all("td", recursive=False)
            if len(cells) != len(headers):
                continue
            values = dict(zip(headers, cells))
            title = clean(values["Title"])
            links = row.find_all("a", href=True)
            link = next((a for a in links if parse_qs(urlsplit(a["href"]).query).get("type") == ["solution"]), None)
            if link is None:
                link = next((a for a in links if re.search(r"/discussion/\d+$", urlsplit(a["href"]).path)), None)
            if link is None:
                continue
            official = title == "Official Editorial"
            kind = "html" if "/discussion/" in link["href"] else None
            items.append(material(link["href"], title or clean(link), base=page_url, role="editorial",
                                  kind=kind, scope="problem", problem_key=problem_key,
                                  official=official, posted_by=clean(values["Posted By"]) or None))
    return unique_materials(items)


class QojSource:
    def __init__(self, transport):
        self.transport = transport

    def category(self, request, context):
        return parse_category(self.transport.get(request.url, context), request.native_id, context)

    def contest(self, request, context):
        root = f"https://qoj.ac/contest/{request.native_id}"
        return parse_contest(self.transport.get(root, context), request.native_id, context)

    def problem(self, request, context):
        problem_id = request.native_id
        root = f"https://qoj.ac/problem/{problem_id}"
        global_page = self.transport.get(root, context)
        data, soup, content = problem_metadata(global_page, problem_id)
        base_page = global_page
        parent = None
        if request.contest_id:
            try:
                parent_request = replace(request, entity="contest", native_id=request.contest_id,
                                         url=f"https://qoj.ac/contest/{request.contest_id}", contest_id=None)
                previous_warnings = len(context.warnings)
                try:
                    parent = self.contest(parent_request, context)
                finally:
                    for warning in context.warnings[previous_warnings:]:
                        if warning["field"] == "data.problems":
                            warning["field"] = "data.contest"
                item = next((p for p in parent["problems"] or [] if p["problemId"] == problem_id), None)
                if parent["problems"] is not None and item is None:
                    raise FetchError("CONTEXT_MISMATCH", "The problem is not in the requested QOJ contest.", 422)
                base_page = self.transport.get(f"https://qoj.ac/contest/{request.contest_id}/problem/{problem_id}", context)
                scoped, soup, content = problem_metadata(base_page, problem_id)
                if item is None:
                    raise FetchError("UPSTREAM_PARSE_ERROR", "The requested native membership could not be verified.")
                data.update(contest=contest_ref(parent), index=item["index"],
                            membershipKey=item["membershipKey"], contextUrl=item["contextUrl"])
                for field in ("limits", "points", "sourceFlags", "details", "submission", "taskMode", "interactive"):
                    data[field] = scoped[field]
                for usage in data["contests"] or []:
                    if usage["contestId"] == request.contest_id:
                        usage.update(name=parent["name"], index=item["index"])
            except FetchError as error:
                if error.code == "CONTEXT_MISMATCH":
                    raise
                base_page = global_page
                _, soup, content = problem_metadata(global_page, problem_id)
                context.warn("CONTEST_CONTEXT_UNAVAILABLE", "data.contest", str(error))
        available_variants = variants(content, base_page.url, problem_id)
        available = list(dict.fromkeys(v["language"] for v in available_variants if v["language"]))
        selected = next((v for v in available_variants if v["language"] == request.lang), None)
        selected_id, selected_lang = "default", None
        selected_page = base_page
        if request.lang != "default" and selected:
            try:
                selected_page = self.transport.get(selected["url"], context)
                selected_id, selected_lang = selected["sourceId"], selected["language"]
            except FetchError as error:
                context.warn("LANGUAGE_FALLBACK", "data.statement.language", str(error))
        elif request.lang != "default":
            context.warn("LANGUAGE_FALLBACK", "data.statement.language", "The requested statement version is unavailable; using the default version.")
        _, selected_soup, selected_content = problem_metadata(selected_page, problem_id)
        items = problem_materials(content, base_page.url, data["key"])
        items.extend(problem_materials(selected_content, selected_page.url, data["key"]))
        if parent and data["contest"]:
            items.extend(parent["materials"] or [])
        # Preserve the default document descriptor even when an HTML translation is selected.
        base_frame = content.select_one("#tab-statement iframe#statements-pdf")
        if base_frame:
            items.append(material(base_frame.get("src"), "Default statement document", base=base_page.url,
                                  role="statement", scope="problem", problem_key=data["key"]))
        tab = selected_content.select_one("#tab-statement")
        frame = tab.select_one("iframe#statements-pdf") if tab else None
        article = tab.find("article") if tab else None
        if frame:
            descriptor = material(frame.get("src"), "Statement document", base=selected_page.url,
                                  role="statement", lang=selected_lang, scope="problem", problem_key=data["key"])
            if descriptor is None:
                raise FetchError("UPSTREAM_PARSE_ERROR", "QOJ's statement document link is unsupported.")
            items.append(descriptor)
            data["statement"] = document_statement([descriptor["key"]], selected_lang,
                                                   available or None, available_variants or None, selected_id)
        elif article:
            notice = tab.select_one(".alert-warning")
            translation = None
            if notice and "AI Translation" in clean(notice):
                translation = {"kind": "ai", "noticeHtml": sanitize(notice, selected_page.url)[0]}
                context.warn("SOURCE_AI_TRANSLATION", "data.statement.translation",
                             "QOJ marks the selected statement as an AI translation.", partial=False)
            data["statement"] = statement(tab, selected_page.url, selected_lang, available or None,
                                          available_variants or None, selected_id, translation)
            data["samples"] = samples(article, "qoj")
            infer_task(data, article, selected_page.url, "qoj")
        else:
            context.warn("STATEMENT_UNAVAILABLE", "data.statement", "QOJ's selected statement representation is unrecognized.")
        for variant in available_variants:
            if variant["sourceId"] == selected_id and data["statement"]:
                variant["format"] = data["statement"]["format"]
        data["materials"] = unique_materials(items)
        return data
