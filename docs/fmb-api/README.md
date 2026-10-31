# desktop-harness API / Interface Reference

Complete reference for the public surfaces of `desktop-harness` v0.4.2:

| Document | Covers |
|----------|--------|
| [cli.md](./cli.md) | `desktop-harness` CLI commands and flags |
| [helpers.md](./helpers.md) | The helper functions available inside `desktop-harness <<'PY' … PY` scripts |
| [modules.md](./modules.md) | Python module APIs (`windows`, `ax`, `capture`, `input`, `presence`, `safety`, `admin`, `selftest`, `demo`, `voice_tools`, `run`) |
| [daemon-protocol.md](./daemon-protocol.md) | Warm daemon socket protocol and client API |
| [configuration.md](./configuration.md) | Environment variables and on-disk paths |
| [scripts.md](./scripts.md) | Repo scripts (`voice_session.py`, `observe-demo.sh`, `install.sh`, dev launcher) |

## Scope and conventions

- **Primary interface** is the CLI (not MCP). Agents run `desktop-harness <<'PY' … PY` and get every helper in [helpers.md](./helpers.md) pre-imported into script scope.
- **Permissions required** (macOS): *Accessibility* (AX tree + synthetic input) and *Screen Recording* (window/display capture). `desktop-harness --doctor` verifies both.
- **Safety gates** apply at runtime: sensitive-app blocking, frontmost-mutation blocking, and the audit log. See [modules.md](./modules.md#safety) and `SECURITY.md` in the repo root.
- Helper signatures follow the public usage documented in `SKILL.md`, `README.md`, `HOW_IT_WORKS.md`, and the in-repo call sites (e.g. `selftest.py`, `demo.py`, `scripts/`). Module-level APIs are documented from source.
- No secrets, tokens, or machine-local absolute paths appear in this reference; configuration entries list **variable names only**.

## Quick example

```bash
desktop-harness <<'PY'
print(frontmost_app())
print(labels()[:15])
open_app("TextEdit")
click_text("Format")
PY
```

Every name used above (`frontmost_app`, `labels`, `open_app`, `click_text`) is documented in [helpers.md](./helpers.md).
