---
name: common-test-case-patterns
description: Reference patterns for the most common self-tester test case shapes. Use when generating new test cases to pick the right skeleton and avoid reinventing structure.
---

# Common Test Case Patterns

Use these patterns as skeletons when creating new test cases. Pick the pattern that matches the user's intent, then fill in endpoint-specific details.

---

## 1. Simple Hit

**When to use:** Verify a single API endpoint returns HTTP 200 and business-level success.

**Flow:** Hit endpoint → verify status 200 → verify body `code`/`error` = 0 (OK).

**Naming convention:** `trigger_*` for the API call, `post_verify_*` for assertions.

```json
{
  "case": "<service>_<api_name>_<environment>",
  "description": "Hit <api_name> and verify 200 + success",
  "tasks": [
    {
      "task_type": "curl",
      "name": "trigger_<api_name>",
      "config": {
        "url": "https://api.example.com/v1/<service>/<api_name>?param=<environment>",
        "method": "POST",
        "headers": {
          "content-type": "application/json",
          "authorization": "Bearer <token>"
        },
        "body": { "key": "value" }
      },
      "output_format": "json"
    },
    {
      "task_type": "compare_json",
      "name": "post_verify_status",
      "config": {
        "source_task": "trigger_<api_name>",
        "field": "status_code",
        "expected": 200,
        "match_mode": "full"
      }
    },
    {
      "task_type": "compare_json",
      "name": "post_verify_body_ok",
      "config": {
        "source_task": "trigger_<api_name>",
        "field": "body",
        "expected": { "success": true, "message": "OK" },
        "match_mode": "partial"
      }
    }
  ]
}
```

---

## 2. Environment Comparison

**When to use:** Compare a new code path (Staging) against deployed/baseline code (Production) to verify parity. Commonly used for refactors or rollouts.

**Flow:** Hit Staging → Hit Production → verify both 200 → verify both have expected structure → compare `body.data` (or `body.response`) between them.

**Naming convention:** `<env>_a` / `<env>_b` for the two calls, `a_matches_b` for the comparison.

```json
{
  "case": "staging-vs-production-<api_name>",
  "description": "Comparison for <api_name>. Env A=Staging, Env B=Production",
  "tasks": [
    {
      "task_type": "curl",
      "name": "env_a_staging",
      "config": {
        "url": "https://api.staging.example.com/v1/<api_name>",
        "method": "GET",
        "headers": {
          "content-type": "application/json"
        }
      },
      "output_format": "json"
    },
    {
      "task_type": "curl",
      "name": "env_b_production",
      "config": {
        "url": "https://api.example.com/v1/<api_name>",
        "method": "GET",
        "headers": {
          "content-type": "application/json"
        }
      },
      "output_format": "json"
    },
    {
      "task_type": "compare_json",
      "name": "env_a_matches_env_b",
      "config": {
        "source_task": "env_a_staging",
        "field": "body.data",
        "expected_task": "env_b_production",
        "match_mode": "full"
      }
    }
  ]
}
```
