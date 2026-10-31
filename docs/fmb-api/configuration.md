# Configuration reference

All configuration is via environment variables (names only — set values in your shell/session, never commit them) plus fixed on-disk paths. Nothing here is secret by default except the daemon token, which the daemon generates and manages itself.

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `DH_NO_DAEMON` | unset | When set to `1`, always run in-process even if a daemon is up |
| `DH_MOUSE_INSTANT` | unset | When set to `1`, warp the mouse with no animation |
| `DH_PRESENCE` | enabled | `1` (default): soft ring + "Agent active — hands off" pill while controlling; `0`: disable presence UI |
| `DH_SAFE` | `1` | Agent policy safe mode (default on). Set to `0`/`false`/`no` to disable |
| `DH_ALLOW_SENSITIVE` | unset | When enabled (`1`/`true`/`yes`), allows controlling/screenshotting password-manager-like apps (keep off; see `SECURITY.md`) |
| `DH_SOCKET` | default path | Override the daemon Unix socket path |
| `DH_TOKEN_PATH` | default path | Override the daemon token file path |
| `DH_AUDIT_LOG` | default path | Override the audit log file path |
| `DH_AGENT_WORKSPACE` | repo-relative default | Override the agent-workspace directory auto-loaded into script scope (referenced in the pre-release review; verify current default on your install) |
| `XAI_API_KEY` | unset | **Required** by `scripts/voice_session.py` for the Grok Voice Realtime API (a Grok Build login is *not* sufficient). Fetch from the xAI console; store in env or Keychain, never in files |
| `GROK_VOICE_MODEL` | built-in default | Override the Realtime voice model name used by `scripts/voice_session.py` |

## Paths (on disk)

| Path (default) | Purpose | Mode |
|----------------|---------|------|
| `~/.desktop-harness/audit.jsonl` | Append-only JSONL audit log of key mutations (screenshots, activations, presses). No built-in rotation — monitor size for long-running agents | user |
| `~/.desktop-harness/daemon.token` | Daemon auth token, regenerated at each `daemon start` | `0600` |
| `~/Library/Caches/desktop-harness/daemon.sock` | Daemon Unix socket | `0600` |
| `~/Library/Caches/desktop-harness/daemon.pid` | Daemon PID file (single-instance check) | `0600` |
| `<tmpdir>/desktop-harness/` | Screenshot output dir; `path=None` captures get unique per-call filenames | user |
| `~/.grok/skills/desktop-harness/SKILL.md` | Where `install.sh` / `desktop-harness skill` register the Grok Build skill (only if `~/.grok` exists) | user |

## macOS permissions (not env — grant once)

| Permission | Why |
|------------|-----|
| Accessibility | Read the AX tree + post mouse/keyboard events |
| Screen Recording | Window/display capture fallback (restart the host app after granting) |

Open the panes:

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
```

Verify with `desktop-harness --doctor`.
