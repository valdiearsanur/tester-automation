# Self-Tester Automation

Ansible-based E2E test automation. Tests are JSON files; tasks run in order and share outputs for comparison.

## Quick Start (Installation)

This tool is distributed as a native Python CLI application. You can install it globally on your system using `pipx`.

```bash
# Install globally via pipx (from the project directory)
pipx install -e .

# Or from a remote git repository:
# pipx install git+https://github.com/your-org/self-tester-automation.git
```

## Usage

Once installed, the `self-tester` command is available everywhere.

```bash
# Run a single test case
self-tester path/to/test.json

# Run a suite of tests in a folder
self-tester path/to/folder/
```

## Configuration

`config/databases.yml`:

```yaml
databases:
  local_db:
    connection: "mysql+pymysql://user:password@host:port/database"
    pool_size: 5

cache:
  redis_test:
    host: "localhost"
    port: 6379
    db: 0
  seller_test:
    host: "host"
    port: 13716
    db: 0
```

## Test Case Format

```json
{
  "case": "test_name",
  "description": "Description",
  "tasks": [
    {
      "task_type": "sql_query",
      "name": "pre_setup",
      "config": { "db_name": "...", "query": "..." },
      "output_format": "json"
    }
  ]
}
```

**Naming**: `pre_*` setup, `trigger_*` main action, `post_*` verification.

## Task Types

| Type | Config | Output |
|------|--------|--------|
| **curl** | `url`, `method`, `headers`, `body` | `status_code`, `body`, `headers` |
| **sql_query** | `db_name`, `query` | SELECT→array, DML→`affected_rows` |
| **compare_json** | `source_task`, `field`, `expected`, `match_mode` | `match`, `actual`, `diff` |
| **cache_get** | `cache_name`, `key` | `value`, `exists` |
| **cache_set** | `cache_name`, `key`, `value` | `success` |
| **cache_flush** | `cache_name` | `success` |
| **local_log_search_v1** | `file_pattern`, `search_pattern`, `use_regex` | `results`, `total_matches`, `files_searched` |
| **wait** | `seconds` | `waited` |

### compare_json

- `match_mode`: `full` (exact) or `partial` (expected ⊆ actual)
- `field`: optional, e.g. `body`, `status_code`; default = entire output


### local_log_search_v1

- `file_pattern`: Glob pattern for log files (e.g. `/path/to/data.log*`)
- `search_pattern`: String or regex to match in lines (e.g. `57b260654b2c2ce3ba1f868b902a9b00`)
- `use_regex`: If true, treat `search_pattern` as regex (default: false)
- `base_url`: default Thanos query_range

## Running Tests

```bash
# Single test (from project root)
./run_test.sh test_cases/check_pending_entity.json

# From anywhere (run-test resolves project root)
./run-test /path/to/test.json

# Direct Ansible
ansible-playbook ansible/playbooks/run_test_case.yml -e "test_case_path=$(pwd)/test_cases/test.json"

# All tests
ansible-playbook ansible/playbooks/run_all_tests.yml
```

Reports: `reports/test_report.csv`

## Project Structure

```
├── ansible/
│   ├── playbooks/     # run_test_case.yml, run_all_tests.yml, execute_task.yml
│   ├── roles/         # *_task per task type
│   └── library/       # sql_executor, cache_manager, json_comparator, prometheus_query, local_log_search
├── test_cases/        # *.json
├── config/databases.yml
└── reports/
```

## Task Output Sharing

Later tasks reference earlier outputs via `source_task`:

```json
{
  "task_type": "compare_json",
  "name": "post_verify",
  "config": {
    "source_task": "trigger_api_call",
    "field": "body",
    "expected": {"error": 0},
    "match_mode": "partial"
  }
}
```
