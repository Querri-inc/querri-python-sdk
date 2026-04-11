# Querri CLI — JSON Output Shapes

## `querri whoami`

```json
{
  "host": "http://localhost",
  "auth_type": "jwt",
  "org_id": "org_01JBETJ7PYNGXVMXV0BD3CFNA8",
  "credential": "<token>",
  "org_name": "Querri",
  "user_email": "dave@querri.com",
  "user_name": "Dave Ingram",
  "user_id": "user_01J8X2EPW1PVPPC3SJ4JFF5Q4Y"
}
```

## `querri project new` / `querri project get`

```json
{
  "id": "81f5238e-df93-4441-a858-3419bbe55d1f",
  "name": "CLI Test 2",
  "description": "Post-rebuild test",
  "status": "idle",           // idle | running | error | complete
  "step_count": 0,
  "chat_count": 0,
  "created_by": "user_01J8X2EPW1PVPPC3SJ4JFF5Q4Y",
  "created_at": "2026-04-10T02:59:35.692000",
  "updated_at": "2026-04-10T02:59:35.692000",
  "steps": null,              // populated on project get
  "chats_store": null
}
```

## `querri project list`

Array of project objects (same shape as above) plus an `"active"` boolean field.

Cursor-paginated — the SDK auto-iterates pages. Raw API returns `{"data": [...], "next": "<cursor>"}`.

## `querri file upload`

```json
{
  "id": "03ad2983-8d75-4b47-9a0f-8f8773f9d911",
  "name": "sales_test.csv",
  "size": 478,
  "content_type": null,
  "created_by": null,
  "created_at": "2026-04-10T03:00:25.905743",
  "columns": null,
  "row_count": null
}
```

## `querri file get`

Same as upload response but with `columns` and `row_count` populated after processing.

## `querri project add-source`

```json
{
  "source_id": "03ad2983-8d75-4b47-9a0f-8f8773f9d911",
  "project_id": "81f5238e-df93-4441-a858-3419bbe55d1f",
  "status": "added",
  "response": "<agent's summary text of the loaded dataset>"
}
```

## `querri chat` (non-streaming response)

```json
{
  "message_id": "948dd65a-3552-4e3d-a0a9-b66b4c8e5389",
  "text": "<AI response text>",
  "tool_calls": [
    {
      "tool_name": "Total Revenue by Region",
      "output": {
        "status": "running|success|error",
        "steps": { "<step_id>": { "name": "...", "status": "...", "tool": "duckdb_query", ... } }
      }
    }
  ],
  "files": [],
  "reasoning": "<internal reasoning trace, if --reasoning flag used>"
}
```

## `querri project run`

```json
{
  "id": "<project_id>",
  "run_id": "api_abc123def456",
  "status": "submitted"
}
```

## `querri project run-status`

```json
{
  "id": "<project_id>",
  "status": "idle|running|error|complete",
  "is_running": false
}
```

## `querri key create`

```json
{
  "id": "<key_uuid>",
  "name": "My Key",
  "key": "sk_live_...",    // only shown once at creation
  "scopes": ["admin:projects:read"],
  "created_at": "...",
  "last_used_at": null
}
```

## `querri embed create-session`

```json
{
  "token": "es_...",
  "session_id": "<uuid>",
  "user_id": "<user_id>",
  "expires_at": "...",
  "project_id": "<project_id>"
}
```
