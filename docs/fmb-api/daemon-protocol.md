# Warm daemon — protocol & client API

Module: `desktop_harness.daemon`. Purpose: keep Python/pyobjc loaded so multi-step agent runs skip the cold start. The CLI auto-routes scripts through a running daemon.

## Security model

| Control | Behavior |
|---------|----------|
| Socket | Unix socket, **mode 0600** (owner only) after bind |
| Token | Random hex token file (**mode 0600**); every request must carry it or the daemon replies `unauthorized` |
| Single instance | PID file with liveness check; a second `start` refuses while one is alive |

The daemon is a **local privileged exec endpoint** (it runs harness scripts with Accessibility rights). Only your user account should be able to read the token/socket. Do not run it on shared multi-user machines without understanding this (see `SECURITY.md`).

## Paths

Socket, PID, and token file locations are environment-overridable — variable names in [configuration.md](./configuration.md#paths).

## Protocol (newline-delimited JSON over the Unix socket)

Every request is one JSON object terminated by `\n`; every response is one JSON object terminated by `\n`.

### `{"op": "ping", "token": "…"}`

Health probe. **Response:** `{"ok": true, "pong": true}`.

### `{"op": "exec", "code": "…", "token": "…"}`

Execute Python `code` with the full helper namespace in scope (same as a CLI script). **Response:**

```json
{"ok": true, "stdout": "…", "stderr": "…"}
```

On exception: `"ok": false` and `stderr` contains the traceback.

### `{"op": "quit", "token": "…"}`

Graceful shutdown. **Response:** `{"ok": true}`; socket and PID files are removed.

### Errors

| Condition | Response |
|-----------|----------|
| Bad/missing token | `{"ok": false, "error": "unauthorized (bad or missing token)"}` |
| Malformed JSON | `{"ok": false, "error": "<parse error>"}` |
| Unknown op | `{"ok": false, "error": "unknown op <op>"}` |
| Daemon closes connection (no bytes) | Client raises `RuntimeError` |

## Client API

### `socket_path() -> Path`
Current socket path (respects the override variable).

### `is_running() -> bool`
`True` only if the socket exists **and** a token-authenticated `ping` answers. Never raises on dead/stale sockets.

### `client_request(payload: dict, timeout: float = 60.0) -> dict`
Send one request (auto-attaches the stored token if the payload lacks one) and return the parsed response.

**Errors:** connection refused / timeout propagate as socket exceptions; empty reply → `RuntimeError("daemon closed connection")`.

### `exec_via_daemon(code: str, timeout: float = 60.0) -> dict`
Convenience wrapper for the `exec` op.

**Example:**

```python
from desktop_harness import daemon as d
if d.is_running():
    resp = d.exec_via_daemon("print(1+1)")
    assert resp["ok"] and "2" in resp["stdout"]
```

### `serve() -> None`
Run the daemon in the foreground: writes the token, binds/chmods the socket, writes the PID file, then serves requests until a `quit`. Cleans up socket + PID files on exit.

**Errors:** `SystemExit` with guidance if another daemon is already running (use `desktop-harness daemon stop`).

## Lifecycle via CLI

```bash
desktop-harness daemon start --bg   # background
desktop-harness daemon status       # ping-based check
desktop-harness daemon stop         # quit op
```

Note: `agent-workspace/agent_helpers.py` is loaded once when the daemon starts; edit it → restart the daemon to pick up changes.
