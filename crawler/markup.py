"""Source markup helpers: safe statement HTML, limits, samples, and materials."""

from copy import deepcopy
import re
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Comment


def clean(value):
    if value is None:
        return ""
    if hasattr(value, "get_text"):
        value = value.get_text(" ", strip=True)
    return " ".join(str(value).split())


def number(value):
    match = re.fullmatch(r"\s*([\d,]+(?:\.\d+)?)\s*", str(value))
    if not match:
        return None
    value = float(match[1].replace(",", ""))
    return int(value) if value.is_integer() else value


def absolute(href, base):
    if not href:
        return None
    value = urljoin(base, href)
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or parts.username or parts.password:
        return None
    return value


def limits(raw_time=None, raw_memory=None):
    if not raw_time and not raw_memory:
        return None
    time_ms, memory = None, None
    if raw_time:
        match = re.search(r"([\d.]+)\s*(milliseconds?|ms|seconds?|secs?|s)\b", raw_time, re.I)
        if match:
            time_ms = float(match[1]) * (1 if match[2].lower() in {"ms", "millisecond", "milliseconds"} else 1000)
            if time_ms.is_integer():
                time_ms = int(time_ms)
    if raw_memory:
        match = re.search(r"([\d.]+)\s*(MiB|MB|KiB|KB|GiB|GB|megabytes?|kilobytes?)\b", raw_memory, re.I)
        if match:
            units = {"mib": "MiB", "mb": "MB", "kib": "KiB", "kb": "KB", "gib": "GiB", "gb": "GB",
                     "megabytes": "MB", "megabyte": "MB", "kilobyte": "KB", "kilobytes": "KB"}
            memory = {"value": number(match[1]), "unit": units[match[2].lower()]}
    return {"timeMs": time_ms, "memory": memory, "rawTime": raw_time, "rawMemory": raw_memory}


def language(label):
    label = clean(label).lower()
    for code, names in [("en", ["english", "(en)"]), ("ja", ["日本語", "japanese", "(ja)", "(jp)"]),
                        ("zh-CN", ["简体中文", "简体", "zh_cn", "(zh-cn)"]), ("ru", ["(ru)", "russian"])]:
        if any(name in label for name in names):
            return code
    return None


def material_role(label):
    text = clean(label).lower()
    for role, markers in [
        ("editorial", ["editorial", "tutorial", "analysis", "solution", "解説", "题解", "разбор"]),
        ("announcement", ["announcement", "анонс"]),
        ("statement", ["statement", "problemset", "problems for printing", "tasks for printing", "услов"]),
        ("test_data", ["test data", "testdata", "テストデータ"]),
        ("sample_code", ["sample code", "サンプルコード"]),
        ("grader", ["grader", "distributed files", "配布ファイル"]),
    ]:
        if any(marker in text for marker in markers):
            return role
    return "other"


def material(url, title, *, base=None, role=None, lang=None, kind=None, scope="contest",
             problem_key=None, key=None, official=None, author=None, posted_by=None):
    original = absolute(url, base or url)
    if original is None:
        return None
    parts = urlsplit(original)
    canonical = urlunsplit((parts.scheme, parts.netloc, parts.path,
                           urlencode(sorted(parse_qsl(parts.query))), ""))
    suffix = unquote(parts.path).lower()
    if kind is None:
        kind = "pdf" if suffix.endswith(".pdf") else "zip" if suffix.endswith(".zip") else "unknown"
    filename = unquote(parts.path.rsplit("/", 1)[-1]) if suffix.endswith((".pdf", ".zip")) else None
    value = {"key": key or "url:" + canonical, "role": role or material_role(title),
             "title": clean(title), "language": lang if lang is not None else language(title),
             "type": kind, "scope": scope, "problemKey": problem_key, "url": canonical,
             "originalUrl": original, "fileName": filename, "official": official, "author": author}
    if posted_by is not None:
        value["postedBy"] = posted_by
    return value


def unique_materials(items):
    result, seen = [], set()
    for item in items:
        if item and item["key"] not in seen:
            seen.add(item["key"])
            result.append(item)
    return result


ALLOWED_TAGS = {
    "article", "section", "div", "span", "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "ul", "ol", "li", "dl", "dt", "dd", "table", "caption", "thead", "tbody", "tfoot",
    "tr", "th", "td", "pre", "code", "samp", "kbd", "var", "blockquote", "strong", "em", "b", "i",
    "u", "s", "small", "sub", "sup", "del", "ins", "details", "summary", "figure", "figcaption",
}
DROP_TAGS = {"script", "style", "form", "input", "button", "select", "textarea", "iframe", "object",
             "embed", "link", "meta", "base", "noscript"}
SAFE_ATTRIBUTES = {"class", "id", "title", "alt", "width", "height", "colspan", "rowspan",
                   "start", "value", "open", "scope", "dir", "lang"}


def sanitize(node, base):
    fragment = BeautifulSoup(str(node), "html.parser")
    assets = []
    for comment in fragment.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in list(fragment.find_all(True)):
        if tag.name is None:
            continue
        if tag.name in DROP_TAGS:
            tag.decompose()
            continue
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        attrs = {key: value for key, value in tag.attrs.items() if key in SAFE_ATTRIBUTES}
        if tag.name == "a":
            href = tag.get("href", "")
            resolved = href if href.startswith("#") else absolute(href, base)
            if resolved:
                attrs.update({"href": resolved, "rel": "noopener noreferrer"})
        if tag.name == "img":
            original = tag.get("src")
            resolved = absolute(original, base)
            if not resolved:
                tag.decompose()
                continue
            attrs["src"] = resolved
            asset = {"type": "image", "url": resolved, "originalUrl": original, "alt": tag.get("alt")}
            if asset not in assets:
                assets.append(asset)
        tag.attrs = attrs
    return str(fragment), assets


def pre_text(pre):
    copy = deepcopy(pre)
    for br in copy.find_all("br"):
        br.replace_with("\n")
    lines = copy.select(".test-example-line")
    if lines:
        return "\n".join(line.get_text() for line in lines) + "\n"
    return copy.get_text().replace("\r\n", "\n")


def samples(node, source):
    if source == "cf":
        result = []
        for block in node.select(".sample-test"):
            inputs, outputs = block.select(".input pre"), block.select(".output pre")
            for position in range(max(len(inputs), len(outputs))):
                result.append({"kind": "standard",
                               "input": pre_text(inputs[position]) if position < len(inputs) else None,
                               "output": pre_text(outputs[position]) if position < len(outputs) else None})
        return result
    found = {}
    for heading in node.find_all(["h3", "h4", "h5"]):
        text = clean(heading)
        match = re.search(r"(?:Sample\s+(Grader\s+)?(Input|Output)|入力例|出力例|Input|Output|输入格式|输出格式|样例输入|样例输出)\s*(\d+)", text, re.I)
        if not match:
            continue
        if not (text.startswith(("Sample", "入力例", "出力例", "Input", "Output", "输入", "输出", "样例"))):
            continue
        pre = heading.find_next("pre")
        if pre is None or pre not in node.descendants:
            continue
        next_heading = heading.find_next(["h3", "h4", "h5"])
        if next_heading and next_heading in heading.find_all_next() and next_heading in pre.find_all_previous():
            continue
        index = match.group(3)
        kind = "grader" if "grader" in text.lower() else "standard"
        side = "output" if any(word in text.lower() for word in ["output", "出力", "输出"]) else "input"
        item = found.setdefault(index, {"kind": kind, "input": None, "output": None})
        if kind == "grader":
            item["kind"] = kind
        item[side] = pre_text(pre)
    return list(found.values())


def statement(node, base, lang, available=None, variants=None, selected=None, translation=None):
    html, assets = sanitize(node, base)
    return {"format": "html", "language": lang, "availableLanguages": available,
            "selectedVariant": selected, "variants": variants, "translation": translation,
            "html": html, "assets": assets, "documentMaterialKeys": []}


def document_statement(material_keys, lang=None, available=None, variants=None, selected=None):
    return {"format": "document", "language": lang, "availableLanguages": available,
            "selectedVariant": selected, "variants": variants, "translation": None,
            "html": None, "assets": None, "documentMaterialKeys": material_keys}


def infer_task(data, node, base, source):
    text = clean(node)
    if re.search(r"(?:This is an interactive problem|This problem is interactive|interactive task|インタラクティブな問題)", text, re.I):
        data.update(taskMode="interactive", interactive=True)
    file_names = list(dict.fromkeys(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*\.(?:cpp|c|h|hpp))\b", text)))
    if source == "atcoder" and file_names and re.search(r"(?:implement|実装).{0,100}(?:function|関数)|(?:function|関数).{0,100}(?:implement|実装)", text, re.I):
        data["taskMode"] = "library"
        data["io"] = {"input": {"type": "function", "fileName": None},
                      "output": {"type": "function", "fileName": None}}
        data["submission"] = {
            "availableLanguages": None,
            "requiredFiles": [name for name in file_names if name.endswith((".cpp", ".c"))
                              and not name.lower().startswith("grader")] or None,
            "requiredHeaders": [name for name in file_names if name.endswith((".h", ".hpp"))] or None,
            "instructionsHtml": None,
        }
        instruction_parts = []
        for heading in node.find_all(["h2", "h3", "h4"]):
            if re.search(r"Implementation|How to Submit|Important Note|Important Notice|実装|提出方法|注意事項", clean(heading), re.I):
                part = heading.find_parent(class_="part") or heading.parent
                instruction_parts.append(sanitize(part, base)[0])
        data["submission"]["instructionsHtml"] = "\n".join(dict.fromkeys(instruction_parts)) or None
    elif source == "atcoder" and re.search(r"standard input|標準入力", text, re.I):
        data["io"]["input"]["type"] = "standard"
        if node.find(["h3", "h4"], string=re.compile(r"^(Output|出力)$")):
            data["io"]["output"]["type"] = "standard"
            if data["taskMode"] is None:
                data.update(taskMode="batch", interactive=False)
    scoring_headings = [h for h in node.find_all(["h2", "h3", "h4"])
                       if re.fullmatch(r"Subtasks|小課題|Scoring|得点|採点|Grading", clean(h), re.I)]
    if scoring_headings:
        descriptions = []
        subtasks = []
        for heading in scoring_headings:
            section = heading.find_parent(class_="part") or heading.parent
            descriptions.append(sanitize(section, base)[0])
            if not re.fullmatch(r"Subtasks|小課題", clean(heading), re.I):
                continue
            for ordered in section.find_all("ol"):
                start = number(ordered.get("start", len(subtasks) + 1)) or len(subtasks) + 1
                for index, item in enumerate(ordered.find_all("li", recursive=False), int(start)):
                    points = re.search(r"[（(]\s*([\d.]+)\s*(?:points?|点)\s*[）)]", clean(item), re.I)
                    subtasks.append({"index": str(index), "points": number(points[1]) if points else None,
                                     "descriptionHtml": sanitize(item, base)[0]})
        data["scoring"] = {"type": "subtasks" if subtasks else "custom",
                           "subtasks": subtasks or None, "descriptionHtml": "\n".join(dict.fromkeys(descriptions))}
