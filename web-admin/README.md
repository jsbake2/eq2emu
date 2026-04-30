# EQ2Emu Admin Dashboard

Single-password web dashboard for running the private server. Wraps the
existing `scripts/` and `docker compose` stack behind a tabbed UI so the
operator doesn't have to keep a terminal open for routine tasks.

**Localhost-only** — binds `127.0.0.1:8890`, never exposed publicly per the
project's safety rules (CLAUDE.md). Reach it from outside the host via
SSH tunnel (`ssh -L 8890:127.0.0.1:8890 …`) or your VPN.

## Tabs

- **Server** — `docker compose ps` status, Start / Stop / Restart wrapping
  `scripts/server-up.sh` / `server-down.sh`, live tail of the
  `eq2emu-server` container log.
- **Characters** — substring-match search; per-character forms for
  race/gender, coin/status/faction, mastercrafted gear-up, applying the
  canonical character template (UI / hotkeys / macros / skillbar), and
  spawning bank items from a YAML spec. Each mutating form previews via
  `--dry-run` first; the Apply button only enables once a successful
  preview has been shown.
- **Items** — embedded view of `docs/mastercrafted-handouts.html` (the
  full crafted + dropped catalog with rarity / slot / armor-type
  filters and click-to-copy commands). Includes a
  "Regenerate from DB" button that re-runs `gen-mastercrafted-handouts.py`.

## Setup

```bash
cd web-admin
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python set_password.py            # prompts for password (or --pw <pw>)
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8890
```

Open <http://127.0.0.1:8890>, sign in with the password you just set.

## Run as a systemd service

```bash
sudo cp web-admin/eq2emu-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eq2emu-admin
sudo systemctl status eq2emu-admin
```

The unit runs as `jbaker` and assumes the venv lives at
`web-admin/.venv/`. Adjust `User=` / paths in the unit file if your
setup differs.

## Files

- `app.py` — FastAPI app (auth, all endpoints, WebSocket for live status).
- `static/index.html` — single-file dashboard (HTML + CSS + JS).
- `set_password.py` — bootstrap `secrets.json` (scrypt hash).
- `secrets.json` — generated; gitignored. Holds the dashboard password
  hash. Re-run `set_password.py` to rotate.
- `requirements.txt` — Python deps for the web app.
- `eq2emu-admin.service` — systemd unit template.

## Notes

- **DB credentials** come from `docker/.env` (`MARIADB_ROOT_PASSWORD`).
  No DB password lives in this directory.
- **Scripts are subprocessed** rather than imported — keeps the existing
  CLI scripts authoritative and lets dry-run output flow straight into
  the UI.
- **Some features depend on PRs that may not be merged yet** (e.g.
  `gear-up.py` lives on its own feature branch). The admin app handles a
  missing script gracefully — the form will report
  `script not found: scripts/<name>` instead of crashing.
- **No console / arbitrary-SQL tab** by design. If you need it, run
  `docker compose exec mysql mariadb -uroot -p$MARIADB_ROOT_PASSWORD eq2emu`
  from a shell.
