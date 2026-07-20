#!/usr/bin/env python3
"""
Test suite orchestrator — discover and run all .json test cases in a folder.

Usage:
    python run_suite.py <folder>
    python run_suite.py <folder> --report reports/my_run.csv
    python run_suite.py <folder> --config config/databases.yml --quiet
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Reuse existing pure-Python helpers from the ansible library directory.
_LIB_DIR = Path(__file__).parent / "ansible" / "library"
sys.path.insert(0, str(_LIB_DIR))

from json_comparator import match_json  # noqa: E402
from sql_executor import execute_query, get_db_connection  # noqa: E402

# ── terminal colours ──────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _c(*codes: str) -> str:
    return "".join(codes)


def colored(text: str, *codes: str) -> str:
    return _c(*codes) + str(text) + RESET


# ── nested field helper ───────────────────────────────────────────────────────

def _header_key(k: str) -> str:
    return k.lower().replace("_", "-")


def get_nested(obj: Any, path: Optional[str]) -> Any:
    """Resolve a dotted field path; header keys are case-insensitive."""
    if not path:
        return obj
    parts = path.split(".")
    for i, part in enumerate(parts):
        if not isinstance(obj, dict):
            return None
        if i > 0 and parts[0].lower() == "headers":
            norm = _header_key(part)
            key = next((k for k in obj if _header_key(k) == norm), None)
        else:
            key = part if part in obj else None
        if key is None:
            return None
        obj = obj[key]
    return obj


# ── individual task executors ─────────────────────────────────────────────────

def run_curl(config: dict) -> dict:
    url = config["url"]
    method = config.get("method", "POST").upper()
    headers = config.get("headers", {})
    body = config.get("body")

    t0 = time.time()
    resp = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=body,
        verify=False,
        timeout=30,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        resp_body = resp.json()
    except Exception:
        resp_body = resp.text

    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "cookies": resp.cookies.get_dict(),
        "body": resp_body,
        "elapsed_ms": elapsed_ms,
    }


def run_sql_query(config: dict, task_outputs: dict, config_file: str) -> Any:
    db_name = config["db_name"]
    query = config["query"]
    since_task = config.get("since_task")

    if since_task and "__SINCE_CTIME__" in query:
        prev = task_outputs.get(since_task, [])
        if isinstance(prev, list) and prev:
            first = prev[0] if isinstance(prev[0], dict) else {}
            if "max_ctime" in first:
                since_ctime = first["max_ctime"]
            else:
                ctimes = [r.get("ctime", 0) for r in prev if isinstance(r, dict)]
                since_ctime = max(ctimes) if ctimes else 0
        elif isinstance(prev, dict):
            since_ctime = prev.get("max_ctime", 0)
        else:
            since_ctime = 0
        query = query.replace("__SINCE_CTIME__", str(since_ctime))

    conn_str = get_db_connection(db_name, config_file)
    return execute_query(conn_str, query)


def run_compare_json(config: dict, task_outputs: dict) -> dict:
    source_task = config["source_task"]
    field = config.get("field")
    match_mode = config.get("match_mode", "partial")

    source_output = task_outputs.get(source_task)
    if source_output is None:
        raise ValueError(f"source_task '{source_task}' output not found")

    actual = get_nested(source_output, field)
    if actual is None and field:
        raise ValueError(f"field '{field}' not found in '{source_task}' output")

    expected_task = config.get("expected_task")
    if expected_task:
        expected_output = task_outputs.get(expected_task)
        if expected_output is None:
            raise ValueError(f"expected_task '{expected_task}' output not found")
        expected = get_nested(expected_output, field)
    else:
        expected = config.get("expected")

    match, diff = match_json(expected, actual, match_mode)
    if not match:
        raise AssertionError(diff or "mismatch")

    return {"match": True, "expected": expected, "actual": actual}


def run_wait(config: dict) -> dict:
    seconds = config.get("seconds", 1)
    time.sleep(seconds)
    return {"waited": seconds}


def run_cache(task_type: str, config: dict, config_file: str) -> dict:
    from cache_manager import cache_flush, cache_get, cache_set, get_cache_connection  # noqa: F401
    cache_cfg = get_cache_connection(config["cache_name"], config_file)
    if task_type == "cache_get":
        return cache_get(cache_cfg, config["key"])
    if task_type == "cache_set":
        return cache_set(cache_cfg, config["key"], config["value"])
    return cache_flush(cache_cfg)


# ── inject url helper ─────────────────────────────────────────────────────────

def inject_config_url(config: dict, task_outputs: dict):
    if "inject_url_from" in config and "inject_url_key" in config:
        from_task = config["inject_url_from"]
        key = config["inject_url_key"]
        if from_task in task_outputs:
            body = task_outputs[from_task].get("body", {})
            if isinstance(body, list) and len(body) > 0:
                val = body[0].get(key)
            else:
                val = body.get(key)
            if val:
                # Assuming URL might contain {key} or we just append it
                # For safety, replace {key}
                config["url"] = config["url"].replace(f"{{{key}}}", str(val))


# ── test case runner ──────────────────────────────────────────────────────────

def run_task(task_def: dict, task_outputs: dict, config_file: str, case_outputs_dir: Path) -> dict:
    task_name = task_def["name"]
    task_type = task_def["task_type"]
    cfg = task_def.get("config", {})
    t0 = time.time()
    
    # Simple dependency injection
    inject_config_url(cfg, task_outputs)
    
    if "source_auth_task" in cfg:
        auth_out = task_outputs.get(cfg["source_auth_task"], {})
        # Merge cookies from get_csrf_token and the source_auth_task
        cookies = {}
        if "get_csrf_token" in task_outputs:
            cookies.update(task_outputs["get_csrf_token"].get("cookies", {}))
        cookies.update(auth_out.get("cookies", {}))
        
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            cfg.setdefault("headers", {})["cookie"] = cookie_str
            
            if "XSRF-TOKEN" in cookies:
                import urllib.parse
                xsrf = urllib.parse.unquote(cookies["XSRF-TOKEN"])
                cfg.setdefault("headers", {})["X-XSRF-TOKEN"] = xsrf

    try:
        if task_type == "curl":
            output = run_curl(cfg)
        elif task_type == "sql_query":
            output = run_sql_query(cfg, task_outputs, config_file)
        elif task_type == "compare_json":
            output = run_compare_json(cfg, task_outputs)
        elif task_type == "wait":
            output = run_wait(cfg)
        elif task_type in ("cache_get", "cache_set", "cache_flush", "cache_flush_task"):
            output = run_cache(task_type, cfg, config_file)
        else:
            raise NotImplementedError(f"unsupported task_type: {task_type}")

        elapsed = int((time.time() - t0) * 1000)
        task_outputs[task_name] = output
        (case_outputs_dir / f"{task_name}.json").write_text(json.dumps(output, default=str))
        
        # Check expected status for curl
        if task_type == "curl" and "expected_status" in cfg:
            exp_status = cfg["expected_status"]
            actual_status = output["status_code"]
            if isinstance(exp_status, list):
                if actual_status not in exp_status:
                    raise AssertionError(f"Expected status in {exp_status}, got {actual_status}")
            else:
                if actual_status != exp_status:
                    raise AssertionError(f"Expected status {exp_status}, got {actual_status}")

        return {"name": task_name, "task_type": task_type,
                "success": True, "error": None, "elapsed_ms": elapsed}

    except Exception as exc:
        elapsed = int((time.time() - t0) * 1000)
        error_str = str(exc)
        task_outputs[task_name] = {"error": error_str}
        (case_outputs_dir / f"{task_name}.json").write_text(json.dumps({"error": error_str}))
        return {"name": task_name, "task_type": task_type,
                "success": False, "error": error_str, "elapsed_ms": elapsed}


def run_test_case(tc_path: Path, config_file: str, outputs_dir: Path) -> dict:
    with open(tc_path) as f:
        tc = json.load(f)

    case_name = tc.get("case", tc_path.stem)
    description = tc.get("description", "")
    
    # Support both old flat 'tasks' schema and new phased schema
    if "tasks" in tc and not any(k in tc for k in ["pre_conditions", "test_steps", "verifications"]):
        # Legacy support
        pre_cond = []
        steps = tc.get("tasks", [])
        verifications = []
    else:
        pre_cond = tc.get("pre_conditions", [])
        steps = tc.get("test_steps", [])
        verifications = tc.get("verifications", [])

    case_outputs_dir = outputs_dir / case_name
    case_outputs_dir.mkdir(parents=True, exist_ok=True)

    task_outputs: dict = {}
    phase_results = {
        "pre_conditions": [],
        "test_steps": [],
        "verifications": []
    }
    
    overall_success = True
    failed_tasks = []

    # Run Pre-conditions
    for t in pre_cond:
        res = run_task(t, task_outputs, config_file, case_outputs_dir)
        phase_results["pre_conditions"].append(res)
        if not res["success"]:
            overall_success = False
            failed_tasks.append(res)
            break  # Stop execution if pre-condition fails
            
    # Run Test Steps
    if overall_success:
        for t in steps:
            res = run_task(t, task_outputs, config_file, case_outputs_dir)
            phase_results["test_steps"].append(res)
            if not res["success"]:
                overall_success = False
                failed_tasks.append(res)
                break
                
    # Run Verifications
    if overall_success:
        for t in verifications:
            res = run_task(t, task_outputs, config_file, case_outputs_dir)
            phase_results["verifications"].append(res)
            if not res["success"]:
                overall_success = False
                failed_tasks.append(res)

    def phase_status(results):
        if not results: return "N/A"
        if all(r["success"] for r in results): return "PASS"
        return "FAIL"

    return {
        "case": case_name,
        "file": str(tc_path),
        "description": description,
        "success": overall_success,
        "phases": phase_results,
        "pre_cond_status": phase_status(phase_results["pre_conditions"]),
        "steps_status": phase_status(phase_results["test_steps"]),
        "verify_status": phase_status(phase_results["verifications"]),
        "failed_tasks": [{"name": ft["name"], "error": ft["error"]} for ft in failed_tasks],
    }


# ── terminal output ───────────────────────────────────────────────────────────

def print_case(result: dict, quiet: bool):
    badge = colored("PASS", GREEN, BOLD) if result["success"] else colored("FAIL", RED, BOLD)
    print(f"\n  {colored(result['case'], BOLD, CYAN)}  [{badge}]")

    if not quiet or not result["success"]:
        for phase_name in ["pre_conditions", "test_steps", "verifications"]:
            results = result["phases"][phase_name]
            if not results: continue
            
            print(f"    {colored(phase_name.upper(), BOLD)}")
            for t in results:
                tick = colored("✓", GREEN) if t["success"] else colored("✗", RED)
                name_part = t["name"]
                type_part = colored(f"[{t['task_type']}]", DIM)
                time_part = colored(f"{t['elapsed_ms']}ms", DIM) if t["task_type"] not in ("compare_json", "wait") else ""
                print(f"      {tick} {name_part} {type_part} {time_part}")
                if not t["success"] and t["error"]:
                    print(f"          {colored(t['error'][:200], RED)}")


# ── CSV report ────────────────────────────────────────────────────────────────

def write_csv_report(results: list, report_path: Path):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Case Name", "File", "Pre-conditions", "Test Steps", "Verifications", "Overall Status", "Failure Details"
        ])
        for r in results:
            fails = "; ".join(f"{ft['name']}: {ft['error']}" for ft in r["failed_tasks"])
            writer.writerow([
                r["case"],
                Path(r["file"]).name,
                r["pre_cond_status"],
                r["steps_status"],
                r["verify_status"],
                "PASS" if r["success"] else "FAIL",
                fails
            ])


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run all .json test cases in a folder and generate a report."
    )
    parser.add_argument("folder", help="Folder containing test case JSON files")
    parser.add_argument("--report", default=None,
                        help="Report output path (default: reports/<timestamp>_report.csv)")
    parser.add_argument("--config", default=None,
                        help="Path to databases.yml (default: config/databases.yml)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Only show task detail for failures")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.exists():
        sys.exit(f"Error: folder not found: {folder}")

    config_file = args.config or str(Path.cwd() / "config" / "databases.yml")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    outputs_dir = Path(f"/tmp/self_tester_outputs/{run_id}")
    report_path = Path(args.report) if args.report else (
        Path(args.folder).parent / "reports" / f"{run_id}_report.csv"
    )

    test_cases = sorted(folder.rglob("*.json"))
    if not test_cases:
        sys.exit(f"No .json files found in {folder}")

    print(f"\n{colored('Self-Tester Orchestrator', BOLD)}")
    print(f"  Folder : {folder}")
    print(f"  Cases  : {len(test_cases)}")
    print(f"  Config : {config_file}")
    print(f"  Report : {report_path}")

    all_results = []
    suite_t0 = time.time()

    for i, tc_path in enumerate(test_cases, 1):
        prefix = colored(f"[{i}/{len(test_cases)}]", DIM)
        print(f"\n{prefix} {colored(tc_path.name, DIM)}", end="", flush=True)
        result = run_test_case(tc_path, config_file, outputs_dir)
        all_results.append(result)
        print_case(result, quiet=args.quiet)

    elapsed_total = int(time.time() - suite_t0)
    total = len(all_results)
    passed = sum(1 for r in all_results if r["success"])
    failed = total - passed

    print()
    print("=" * 60)
    summary_color = GREEN if failed == 0 else RED
    print(
        colored("SUMMARY", BOLD) + ": "
        + colored(f"{passed}/{total} PASSED", summary_color, BOLD)
        + (colored(f"  {failed} FAILED", RED, BOLD) if failed else "")
        + colored(f"  ({elapsed_total}s)", DIM)
    )

    write_csv_report(all_results, report_path)
    print(f"Report : {report_path}")
    print()

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
