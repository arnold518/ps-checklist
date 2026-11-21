"""Fetch inputs, response shapes, and safe errors shared by all source adapters."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from urllib.parse import parse_qsl, unquote, urlsplit


ROUTES = {
    "/fetch/cf/contest": ("cf", "contest"),
    "/fetch/cf/problem": ("cf", "problem"),
    "/fetch/atcoder/contest": ("atcoder", "contest"),
    "/fetch/atcoder/problem": ("atcoder", "problem"),
    "/fetch/qoj/category": ("qoj", "category"),
    "/fetch/qoj/contest": ("qoj", "contest"),
    "/fetch/qoj/problem": ("qoj", "problem"),
    "/fetch/ojuz/category": ("ojuz", "category"),
    "/fetch/ojuz/contest": ("ojuz", "contest"),
    "/fetch/ojuz/problem": ("ojuz", "problem"),
    "/fetch/boj/category": ("boj", "category"),
    "/fetch/boj/contest": ("boj", "contest"),
    "/fetch/boj/problem": ("boj", "problem"),
    "/fetch/solvedac/difficulty": ("solvedac", "difficulty"),
}
HOSTS = {"cf": "codeforces.com", "atcoder": "atcoder.jp", "qoj": "qoj.ac", "ojuz": "oj.uz",
         "boj": "acmicpc.net", "solvedac": "solved.ac"}
LANGUAGES = {"cf": {"en"}, "atcoder": {"en", "ja"},
             "qoj": {"en", "ja", "zh-CN", "default"}, "ojuz": {"default"}, "boj": {"default"}}
BOJ_HOSTS = {"acmicpc.net", "www.acmicpc.net"}
NATIVE_ID = r"[1-9][0-9]{0,14}"
BOJ_PATHS = {"category": rf"/category(?:/({NATIVE_ID}))?",
             "contest": rf"/category/detail/({NATIVE_ID})", "problem": rf"/problem/({NATIVE_ID})"}
OPERATOR_ROUTES = frozenset(route for route, (source, _) in ROUTES.items() if source in ("boj", "solvedac"))


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class FetchError(Exception):
    def __init__(self, code, message, status=502, retryable=False, retry_after=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after

    def response(self):
        return {"schemaVersion": 1, "ok": False, "error": {
            "code": self.code, "message": str(self), "retryable": self.retryable,
        }}


def invalid(message="Unsupported or invalid request parameters."):
    return FetchError("INVALID_PARAMETER", message, 400)


def parse_bool(value):
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise invalid("Use true or false for includeExternalMaterials.")


@dataclass(frozen=True)
class FetchRequest:
    source: str
    entity: str
    url: str
    native_id: int | str
    category: str = "contest"
    index: str | None = None
    contest_id: int | str | None = None
    lang: str = "en"
    external: bool = False

    @classmethod
    def parse(cls, route, parameters):
        if route not in ROUTES:
            raise FetchError("NOT_FOUND", "Unknown API route.", 404)
        source, entity = ROUTES[route]
        if route in OPERATOR_ROUTES:
            return cls.parse_boj_or_solvedac(source, entity, parameters)
        allowed = {"url", "lang"}
        if source == "atcoder":
            allowed.add("includeExternalMaterials")
        if (source, entity) == ("qoj", "problem"):
            allowed.add("contestId")
        if (source, entity) == ("ojuz", "problem"):
            allowed.add("sourceId")
        if not isinstance(parameters, dict) or set(parameters) - allowed:
            raise invalid()
        value = parameters.get("url")
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise FetchError("INVALID_URL", "Provide a supported source resource URL.", 400)
        try:
            parts = urlsplit(value.strip())
            valid = (parts.scheme in {"http", "https"} and parts.hostname == HOSTS[source]
                     and parts.port in (None, 443 if parts.scheme == "https" else 80) and parts.username is None
                     and parts.password is None and not parts.fragment
                     and set(dict(parse_qsl(parts.query))) <= {"lang", "locale"})
        except ValueError:
            valid = False
        if not valid:
            raise FetchError("INVALID_URL", "Use a supported judge URL without credentials or fragments.", 400)
        path = unquote(parts.path).rstrip("/")
        lang = parameters.get("lang", "default" if source == "ojuz" else "en")
        if not isinstance(lang, str) or lang not in LANGUAGES[source]:
            raise invalid("Unsupported content language for this source.")
        external = parse_bool(parameters.get("includeExternalMaterials", False))
        category, index, contest_id = "contest", None, None
        if source == "cf":
            if entity == "contest":
                match = re.fullmatch(r"/(contest|gym)/([1-9]\d*)", path)
                if match:
                    category, native_id = match[1], int(match[2])
            else:
                match = re.fullmatch(r"/(contest|gym)/([1-9]\d*)/problem/([A-Za-z0-9_]+)", path)
                if match:
                    category, native_id, index = match[1], int(match[2]), match[3]
                else:
                    match = re.fullmatch(r"/problemset/problem/([1-9]\d*)/([A-Za-z0-9_]+)", path)
                    if match:
                        native_id, index = int(match[1]), match[2]
            normalized = f"/{category}/{native_id}" + (f"/problem/{index}" if index else "") if match else None
        elif source == "atcoder":
            slug = r"[A-Za-z0-9][A-Za-z0-9_-]*"
            pattern = rf"/contests/({slug})" + (rf"/tasks/({slug})" if entity == "problem" else "")
            match = re.fullmatch(pattern, path)
            if match:
                native_id = match[1]
                index = match[2] if entity == "problem" else None
            normalized = path if match else None
        elif source == "ojuz":
            slug = r"[A-Za-z0-9][A-Za-z0-9_-]*"
            pattern = rf"/problem/view/({slug})" if entity == "problem" else rf"/problems/source/({slug})"
            match = re.fullmatch(pattern, path)
            if entity == "category" and path == "/problems/source":
                native_id, normalized = "root", path
            else:
                native_id, normalized = (match[1], path) if match else (None, None)
            category = "source"
            if entity == "problem" and parameters.get("sourceId") is not None:
                supplied = parameters["sourceId"]
                if not isinstance(supplied, str) or not re.fullmatch(slug, supplied) or len(supplied) > 100:
                    raise invalid("sourceId must be an oj.uz source slug.")
                contest_id = supplied
        else:
            if entity == "category" and path == "/category":
                path = "/category/1"
            if entity == "problem":
                match = re.fullmatch(r"/problem/([1-9]\d*)", path)
                if match:
                    native_id = int(match[1])
                else:
                    match = re.fullmatch(r"/contest/([1-9]\d*)/problem/([1-9]\d*)", path)
                    if match:
                        contest_id, native_id = int(match[1]), int(match[2])
                supplied = parameters.get("contestId")
                if supplied is not None:
                    if isinstance(supplied, bool) or not re.fullmatch(r"[1-9]\d*", str(supplied)):
                        raise invalid("contestId must be a positive integer.")
                    supplied = int(supplied)
                    if contest_id is not None and supplied != contest_id:
                        raise invalid("contestId conflicts with the contest-scoped URL.")
                    contest_id = supplied
                normalized = f"/problem/{native_id}" if match else None
            else:
                match = re.fullmatch(rf"/{entity}/([1-9]\d*)", path)
                if match:
                    native_id = int(match[1])
                normalized = path if match else None
        if normalized is None:
            raise FetchError("INVALID_URL", "The URL does not identify the requested resource type.", 400)
        if len(str(native_id)) > 100 or (index and len(index) > 100):
            raise FetchError("INVALID_URL", "Source identifier is too long.", 400)
        return cls(source, entity, f"https://{HOSTS[source]}{normalized}", native_id,
                   category, index, contest_id, lang, external)

    @classmethod
    def parse_boj_or_solvedac(cls, source, entity, parameters):
        allowed = {"url"}
        if (source, entity) == ("boj", "problem"):
            allowed |= {"sourceId", "lang"}
        if source == "solvedac":
            allowed.add("sub")
        if not isinstance(parameters, dict) or set(parameters) - allowed:
            raise invalid()
        value = parameters.get("url")
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise FetchError("INVALID_URL", "Provide a supported source resource URL.", 400)
        try:
            parts = urlsplit(value.strip())
            valid = (parts.scheme == "https" and parts.port in (None, 443)
                     and parts.username is None and parts.password is None
                     and not parts.query and not parts.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise FetchError("INVALID_URL", "Use a supported HTTPS source URL.", 400)
        path = parts.path.rstrip("/")
        if parts.hostname in BOJ_HOSTS:
            match = re.fullmatch(BOJ_PATHS[entity if source == "boj" else "problem"], path)
            if match:
                if parameters.get("lang", "default") != "default":
                    raise invalid("BOJ supports the default statement version.")
                supplied = parameters.get("sourceId")
                if "sourceId" in parameters and (type(supplied) not in (str, int)
                                                or not re.fullmatch(NATIVE_ID, str(supplied))):
                    raise invalid("sourceId must be a positive BOJ source detail ID.")
                if "sub" in parameters:
                    raise invalid("Use sub only with a solved.ac problem URL.")
                return cls(source, entity, "https://acmicpc.net" + path,
                           int(match[1]) if match[1] else "root",
                           category="boj" if source == "solvedac" else "source",
                           contest_id=int(supplied) if supplied is not None else None, lang="default")
        if source == "solvedac" and parts.hostname == "solved.ac":
            match = re.fullmatch(rf"/(?:(?:ko|en|ja)/)?p/({NATIVE_ID})([a-z]{{1,16}})?", path)
            if match:
                suffix = match[2] or ""
                sub = parameters.get("sub", suffix)
                if (not isinstance(sub, str) or not re.fullmatch(r"[a-z]{0,16}", sub)
                        or suffix and suffix != sub):
                    raise invalid("Use a consistent solved.ac subproblem selector.")
                return cls(source, entity, f"https://solved.ac/p/{match[1]}{sub}",
                           int(match[1]), category="problem", index=sub or None, lang="default")
        raise FetchError("INVALID_URL", "The URL does not identify the requested resource type.", 400)

    def payload(self):
        return dict(self.__dict__)

    @property
    def request_key(self):
        value = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()


class FetchContext:
    def __init__(self, timeout=90):
        self.deadline = time.monotonic() + timeout
        self.fetched_at = utc_now()
        self.sources = []
        self.warnings = []
        self.partial = False

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("UPSTREAM_TIMEOUT", "The source collection deadline was exceeded.", 504, True)
        return remaining

    def source(self, url, fetched_at=None):
        if url not in self.sources:
            self.sources.append(url)
        if fetched_at and fetched_at < self.fetched_at:
            self.fetched_at = fetched_at

    def warn(self, code, field, message, *, partial=True):
        warning = {"code": code, "field": field, "message": message}
        if warning not in self.warnings:
            self.warnings.append(warning)
        self.partial |= partial

    def result(self, data):
        validate_data(data)
        return {"schemaVersion": 1, "ok": True, "data": data, "meta": {
            "status": "partial" if self.partial else "complete", "fetchedAt": self.fetched_at,
            "sources": self.sources, "warnings": self.warnings,
        }}


def summary(key, name, url, index=None, task_id=None):
    return {"key": key, "taskId": task_id, "index": index, "name": name, "url": url,
            "type": None, "points": None, "rating": None, "tags": None, "limits": None}


def contest(key, source, native_id, name, url, category="contest"):
    return {"key": key, "source": source, "contestId": native_id, "category": category,
            "name": name, "url": url, "scoringType": None, "phase": None, "frozen": None,
            "startTime": None, "endTime": None, "durationSeconds": None, "details": {},
            "problemCount": None, "problems": None, "materials": None}


def contest_ref(data):
    return {field: data[field] for field in ("key", "contestId", "category", "name", "url")}


def full_problem(item, source):
    return {**item, "source": source, "contest": None, "taskMode": None, "interactive": None,
            "io": {"input": {"type": None, "fileName": None},
                   "output": {"type": None, "fileName": None}},
            "submission": None, "scoring": None, "statement": None, "samples": None,
            "materials": None}


def validate_data(data):
    if isinstance(data, dict) and data.get("source") == "solvedac":
        from .sources.solvedac import validate_difficulty
        validate_difficulty(data)
        return
    if (not isinstance(data, dict) or not data.get("key") or not data.get("name")
            or not data.get("url") or data.get("source") not in HOSTS):
        raise FetchError("UPSTREAM_PARSE_ERROR", "The source did not produce a valid entity.")
    if "problems" in data:
        problems = data["problems"]
        if problems is None:
            valid = data["problemCount"] is None
        else:
            valid = (data["problemCount"] == len(problems)
                     and len({p["key"] for p in problems}) == len(problems)
                     and all(p.get("url") and p.get("name") for p in problems))
        if not valid:
            raise FetchError("UPSTREAM_PARSE_ERROR", "The source problem list is inconsistent.")
    statement = data.get("statement")
    if statement:
        keys = {m["key"] for m in data.get("materials") or []}
        if not set(statement["documentMaterialKeys"]) <= keys:
            raise FetchError("UPSTREAM_PARSE_ERROR", "A statement document reference is missing.")
        if statement["format"] == "html":
            from bs4 import BeautifulSoup
            html = statement["html"] or ""
            if not BeautifulSoup(html, "html.parser").get_text(strip=True) and not statement["assets"]:
                raise FetchError("UPSTREAM_PARSE_ERROR", "The HTML statement is empty.")
        if statement["format"] == "document" and not statement["documentMaterialKeys"]:
            raise FetchError("UPSTREAM_PARSE_ERROR", "The document statement has no supported source link.")


def validate_response(response):
    if (not isinstance(response, dict) or response.get("ok") is not True
            or response.get("schemaVersion") != 1):
        raise FetchError("UPSTREAM_PARSE_ERROR", "The collector did not return a valid fetch response.")
    meta = response.get("meta")
    if (not isinstance(meta, dict) or meta.get("status") not in {"complete", "partial"}
            or not meta.get("fetchedAt") or not isinstance(meta.get("sources"), list)
            or not isinstance(meta.get("warnings"), list)
            or (meta["status"] == "partial" and not meta["warnings"])):
        raise FetchError("UPSTREAM_PARSE_ERROR", "The fetch response lacks valid collection metadata.")
    validate_data(response.get("data"))
