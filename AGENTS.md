# Self-Tester Automation – AI Instructions

Use this when working with the self-tester-automation project: generating test cases, adding tasks, or debugging tests.

## Installation & Usage

This tool is a global native Python CLI app.
If an agent needs to execute tests or the user asks how to run them, use `pipx` to install:
```bash
pipx install -e .
```
Then execute tests using the `self-tester` command:
```bash
# Run single test
self-tester test_cases/test_file.json

# Run a suite
self-tester test_cases/
```

## Test Case Format

```json
{
  "case": "unique_case_name",
  "description": "Human-readable description",
  "tasks": [
    { "task_type": "...", "name": "unique_task_name", "config": {...}, "output_format": "json" }
  ]
}
```

- **Task names must be unique** within a test case.
- **Tasks run in order**; later tasks can use earlier outputs via `source_task`.
- **Naming**: `pre_*` setup, `trigger_*` main action, `post_*` verification.

## Task Types

| task_type | Required config | Notes |
|-----------|-----------------|-------|
| `curl` | `url`, `method`, `headers`, `body` | HTTP requests |
| `local_log_search_v1` | `file_pattern`, `search_pattern`, `use_regex` | Search local log files by glob + pattern |
| `wait` | `seconds` | Delay |
| `ftp_list` | `host`, `user`, `password` (or `config_name`) | List files on FTP/FTPS server |
| `ftp_download` | `host`, `user`, `password` (or `config_name`), `remote_path`, `local_path` | Download file from FTP/FTPS server |
| `grep_file` | `file_path`, `search_pattern`, `use_regex` | Grep specific file and return matching lines |

### compare_json

- `match_mode: "full"` – expected must match actual exactly.
- `match_mode: "partial"` – expected must be a subset of actual.
- `field` – optional path into output (e.g. `body`, `status_code`, `headers.X-Sp-Error`).


- `step`: default 60.

### local_log_search_v1

- `file_pattern`: Glob for log files (e.g. `/path/to/data.log*`).
- `search_pattern`: String to match in lines (plain or regex if `use_regex: true`).

## Patterns

**Setup → Trigger → Verify**
```json
[
  {"task_type": "sql_query", "name": "pre_setup", "config": {"db_name": "...", "query": "DELETE ...; INSERT ..."}},
  {"task_type": "curl", "name": "trigger_api", "config": {"url": "...", "method": "POST", "body": {...}}},
  {"task_type": "compare_json", "name": "post_verify", "config": {"source_task": "trigger_api", "field": "status_code", "expected": 200, "match_mode": "full"}}
]
```

**Cache invalidation before test**
```json
{"task_type": "cache_flush", "name": "pre_invalidate_cache", "config": {"cache_name": "seller_test"}}
```

**Log search**
```json
{"task_type": "local_log_search_v1", "name": "search_logs", "config": {"file_pattern": "/path/to/log/data.log*", "search_pattern": "57b260654b2c2ce3ba1f868b902a9b00"}}
```

## Adding a New Task Type

1. Add module in `ansible/library/<module>.py`.
2. Add role `ansible/roles/<task_type>_task/tasks/main.yml`.
3. Role calls the module and sets `task_output`.
4. `execute_task.yml` uses `{{ task_def.task_type }}_task` as role name.

## Running Tests

```bash
./run_test.sh test_cases/<file>.json
# or from anywhere:
./run-test /path/to/test.json
```

## Tips

- Use `partial` match_mode unless you need exact match.
- COUNT queries: `SELECT COUNT(*) as count` → `{"count": N}`.
- Outputs are in `task_outputs[task_name]` for `compare_json` `source_task`.

## Common Test Case Patterns

See `.rules/COMMON_CASES.md` for full skeletons of the most common patterns:

| Pattern | When to use |
|---|---|
| **Simple Hit** | Hit a endpoint, verify 200 + code 0 |
| **Local vs Deployed Comparison** | Compare local vs deployed for parity |
| **Simple CRUD** | Create/Update/Delete → verify via DB + GET endpoint |
| **Cross-Region Consistency** | Verify schema or API responses are identical across all regions |
