"""Exercise the running queue-backed API against real source pages.

Usage: python3 tests/live_fetch.py --base-url http://127.0.0.1:8080
Results contain public, sanitized API JSON only; credentials stay in the server.
"""

import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def call(base, path, payload=None):
    request = Request(base + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"} if payload is not None else {})
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def validate(result):
    assert result["schemaVersion"] == 1
    if not result["ok"]:
        assert result["error"]["code"] and isinstance(result["error"]["retryable"], bool)
        return
    data = result["data"]
    assert data["key"] and data["name"] and data["url"].startswith("https://")
    assert result["meta"]["status"] in {"complete", "partial"}
    if result["meta"]["status"] == "partial":
        assert result["meta"]["warnings"]
    if "problems" in data:
        if data["problems"] is None:
            assert data["problemCount"] is None
            assert result["meta"]["status"] == "partial"
        else:
            assert data["problemCount"] == len(data["problems"]) > 0
            assert len({p["key"] for p in data["problems"]}) == data["problemCount"]
            assert all(p["url"] and p["name"] and p["index"] for p in data["problems"])
    if "categoryId" in data:
        assert len(result["meta"]["sources"]) == 1
        assert data["sections"] is not None or result["meta"]["status"] == "partial"
        for section in data["sections"] or []:
            for child in section["entries"]:
                assert child["url"] and child["type"] in {"contest", "category"}
                assert "sections" not in child and "problems" not in child
    statement = data.get("statement")
    if statement:
        if statement["format"] == "document":
            assert statement["html"] is None and data["samples"] is None
            assert statement["documentMaterialKeys"]
        else:
            assert statement["html"] and "<script" not in statement["html"].lower()
            from bs4 import BeautifulSoup
            assert BeautifulSoup(statement["html"], "html.parser").get_text(strip=True) or statement["assets"]
            assert isinstance(data["samples"], list)
        keys = {m["key"] for m in data["materials"] or []}
        assert set(statement["documentMaterialKeys"]) <= keys


def run_batch(base, cases, output, results):
    pending = {}
    for label, route, params in cases:
        status, value = call(base, "/enqueue" + route, params)
        if status != 202:
            raise RuntimeError(f"{label}: enqueue returned {status}: {value}")
        pending[label] = (value["job"]["jobId"], route, params)
    deadline = time.monotonic() + 900
    while pending and time.monotonic() < deadline:
        for label, (job_id, route, params) in list(pending.items()):
            status, result = call(base, "/job/result?" + urlencode({"id": job_id}))
            if status == 202:
                continue
            validate(result)
            output.joinpath(label + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            data = result.get("data", {})
            report = {"case": label, "route": route, "request": params, "httpStatus": status,
                      "status": result.get("meta", {}).get("status", "failed"),
                      "name": data.get("name"), "problemCount": data.get("problemCount"),
                      "counts": data.get("counts"),
                      "statementFormat": (data.get("statement") or {}).get("format"),
                      "sampleCount": len(data["samples"]) if data.get("samples") is not None else None,
                      "materialCount": len(data["materials"]) if data.get("materials") is not None else None,
                      "warnings": result.get("meta", {}).get("warnings", []),
                      "error": result.get("error")}
            if label in {"atcoder-problem-joi2026final-C", "atcoder-problem-joi2026final-D"}:
                assert data["taskMode"] == "library"
                assert all(sample["kind"] == "grader" for sample in data["samples"])
                assert "grader.cpp" not in data["submission"]["requiredFiles"]
            results[label] = {"report": report, "result": result}
            print(json.dumps(report, ensure_ascii=False), flush=True)
            del pending[label]
        if pending:
            time.sleep(0.4)
    if pending:
        raise RuntimeError("Live jobs exceeded the test deadline: " + ", ".join(pending))


def run_error_cases(base, output):
    cases = [
        ("invalid-source-url", "/fetch/cf/contest", {"url": "https://qoj.ac/contest/2522"}, 400, "INVALID_URL"),
        ("missing-cf-problem", "/fetch/cf/problem", {"url": "https://codeforces.com/contest/2268/problem/ZZZ"}, 404, "PROBLEM_NOT_FOUND"),
        ("wrong-qoj-context", "/fetch/qoj/problem", {"url": "https://qoj.ac/problem/14601", "contestId": 1662}, 422, "CONTEXT_MISMATCH"),
    ]
    reports = []
    for label, route, params, expected_status, expected_code in cases:
        status, result = call(base, route + "?" + urlencode(params))
        deadline = time.monotonic() + 300
        while status == 202 and time.monotonic() < deadline:
            time.sleep(0.4)
            status, result = call(base, result["job"]["resultUrl"])
        assert status == expected_status, (label, status, result)
        assert result["ok"] is False and result["error"]["code"] == expected_code
        output.joinpath(label + ".json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        reports.append({"case": label, "httpStatus": status, "code": result["error"]["code"]})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, default=Path("crawler/output/live-api"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    for source, contest_ids in [("cf", ["contest/2268", "gym/106225", "gym/105255", "contest/1000"]),
                                ("atcoder", ["agc078", "arc230", "joi2026final", "abc300"]),
                                ("qoj", ["2522", "1662"])]:
        for native_id in contest_ids:
            prefix = "https://codeforces.com/" if source == "cf" else "https://atcoder.jp/contests/" if source == "atcoder" else "https://qoj.ac/contest/"
            cases.append((source + "-contest-" + native_id.replace("/", "-"),
                          f"/fetch/{source}/contest", {"url": prefix + native_id}))
    for category_id in [701, 756, 108, 21]:
        cases.append((f"qoj-category-{category_id}", "/fetch/qoj/category",
                      {"url": f"https://qoj.ac/category/{category_id}"}))
    results = {}
    run_batch(args.base_url, cases, args.output, results)
    problems = []
    for label, value in results.items():
        data = value["result"].get("data", {})
        tasks = data.get("problems") or []
        if not tasks:
            continue
        selected = tasks[:1]
        if data["source"] == "atcoder" and data["contestId"] == "joi2026final":
            selected = tasks[:1] + tasks[2:4]
        for task in selected:
            params = {"url": task["url"]}
            problems.append((label.replace("-contest-", "-problem-") + "-" + task["index"],
                             f"/fetch/{data['source']}/problem", params))
    problems.extend([
        ("qoj-problem-14601-default", "/fetch/qoj/problem", {"url": "https://qoj.ac/problem/14601", "lang": "default"}),
        ("qoj-problem-14601-zh", "/fetch/qoj/problem", {"url": "https://qoj.ac/problem/14601", "lang": "zh-CN"}),
        ("qoj-problem-14601-context", "/fetch/qoj/problem", {"url": "https://qoj.ac/contest/2522/problem/14601"}),
        ("qoj-problem-17704-ja", "/fetch/qoj/problem", {"url": "https://qoj.ac/problem/17704", "lang": "ja"}),
        ("qoj-problem-8674-default", "/fetch/qoj/problem", {"url": "https://qoj.ac/problem/8674", "lang": "default"}),
        ("atcoder-joi-external", "/fetch/atcoder/contest", {"url": "https://atcoder.jp/contests/joi2026final", "includeExternalMaterials": True}),
        ("atcoder-joi-ja", "/fetch/atcoder/problem", {"url": next(p["url"] for p in results["atcoder-contest-joi2026final"]["result"]["data"]["problems"]), "lang": "ja"}),
        ("atcoder-joi-problem-external", "/fetch/atcoder/problem", {"url": "https://atcoder.jp/contests/joi2026final/tasks/joi2026final_c", "includeExternalMaterials": True}),
    ])
    run_batch(args.base_url, problems, args.output, results)
    reports = [value["report"] for value in results.values()]
    summary = {"total": len(reports), "complete": sum(r["status"] == "complete" for r in reports),
               "partial": sum(r["status"] == "partial" for r in reports),
               "failed": sum(r["status"] == "failed" for r in reports), "cases": reports}
    args.output.joinpath("summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}), flush=True)
    assert summary["failed"] == 0, "Some live fetches failed; inspect summary.json."
    assert len({report["route"] for report in reports}) == 7
    summary["expectedErrors"] = run_error_cases(args.base_url, args.output)
    args.output.joinpath("summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({"expectedErrors": summary["expectedErrors"]}), flush=True)


if __name__ == "__main__":
    main()
