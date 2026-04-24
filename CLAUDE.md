# CLAUDE.md

This file provides guidance to Claude Code when working on this EQ2Emu private server project.

## Project Context

This is a **private EverQuest II emulator server** built on the EQ2Emu open-source project, hosted on a local Linux homelab for a small group of friends. The primary goals are running a stable private server and customizing gameplay through database edits, Lua scripting, and occasional C++ modifications.

See `PROJECT.md` for full project details, architecture, and roadmap.

## Tech Stack

- **Server code:** C++ (login server, world server, zone server) — source at https://git.eq2emu.com/devn00b/EQ2EMu
- **Deployment:** Docker Compose stack from https://github.com/emagi/eq2emu-docker
- **Database:** MariaDB (schema includes login, world, and dawn databases)
- **Scripting:** Lua for spawns, spells, quests, and NPC behavior
- **Web admin:** Dawn admin UI (NodeJS) at `https://127.0.0.1:2424`
- **DB editor:** Web-based at `http://127.0.0.1/eq2db`
- **Client:** Official EQ2 client from Steam, configured via `eq2_default.ini` (`cl_ls_address`)
- **Host OS:** Linux (homelab)
- **Automation:** Python for bulk DB operations, content imports, backup scripts

## Repository Layout (expected as project grows)

```
.
├── CLAUDE.md                    # This file
├── PROJECT.md                   # Project overview and roadmap
├── .gitignore                   # Must cover .env, backups/, DB dumps, certs, etc.
├── docker/                      # Docker compose overrides, .env templates
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   └── .env.example
├── server-source/               # Cloned/forked EQ2EMu C++ source (if modified)
├── lua/                         # Custom Lua scripts (spawns, spells, quests)
│   ├── spawns/
│   ├── spells/
│   └── quests/
├── sql/                         # SQL migrations, content edits, seed data
│   ├── migrations/
│   └── content/
├── scripts/                     # Python automation (backups, bulk edits, reports)
├── infra/                       # Infrastructure-as-code
│   └── cloudflare/              # DNS records, tunnel configs (no secrets)
├── docs/                        # Internal notes, command references, schema notes
└── backups/                     # Database and world-state snapshots (gitignored)
```

## How Claude Should Work on This Project

### General Principles

1. **Read before editing.** This codebase is niche and large. Before modifying any C++ or Lua file, read it fully. Before writing SQL, check the actual schema — don't assume column names.
2. **Prefer the least-invasive change.** The hierarchy is: in-game GM command → SQL edit → Lua script → C++ change. Don't jump to C++ if a Lua edit works.
3. **Small, reversible changes.** Always produce migrations or scripts that can be rolled back. No destructive SQL without a backup step.
4. **Explain the blast radius.** Before running anything that touches the live DB, explicitly state what tables/rows will be affected.
5. **Test locally first.** Assume a dev/staging instance exists. Never push changes straight to the production server without testing.
6. **Work on feature branches, merge via PR.** Never commit directly to `main`. See the Git Workflow section below.

### Git Workflow (IMPORTANT)

This project uses **pull requests to mark milestones**. Claude Code should follow this workflow strictly:

**Branching model:**
- `main` — always deployable; only updated via merged PRs
- `feature/<short-name>` — for new functionality (e.g. `feature/gm-boost-command`)
- `fix/<short-name>` — for bug fixes
- `infra/<short-name>` — for Docker, backup, or deployment changes
- `content/<short-name>` — for SQL content edits, Lua spawn/quest additions
- `docs/<short-name>` — for documentation-only changes

**Per-task workflow:**
1. Confirm current branch before starting: `git status && git branch --show-current`
2. If on `main`, create a new branch for the work — never commit on `main` directly
3. Make commits as work progresses, with clear messages (see commit style below)
4. When the milestone is complete, push the branch and open a PR
5. PR description must include: what changed, why, how to test, rollback steps, and any linked issues
6. Do NOT merge the PR — the operator (Jason) reviews and merges

**Commit style:**
- Use conventional-commit-ish prefixes: `feat:`, `fix:`, `infra:`, `content:`, `docs:`, `chore:`
- Subject line under 72 chars, imperative mood (e.g. "feat: add custom /boost GM command")
- Body explains *why*, not *what* — the diff shows what
- Reference SQL migration numbers or issue IDs where relevant

**PR milestones (what constitutes a PR-worthy chunk):**
- A complete phase item from `PROJECT.md` (e.g. "Phase 2: automated MariaDB backups")
- A self-contained feature (one custom command, one new spawn script, one content pack)
- A bugfix with its test case
- An infra change that can be deployed independently
- A documentation set that covers a discrete topic

**Do NOT open a PR for:**
- Work-in-progress that doesn't run
- Multiple unrelated changes bundled together — split them
- Changes that require manual steps that aren't documented in the PR body

**Safety:**
- Never force-push to `main` under any circumstance
- Never rewrite history on a branch that has an open PR
- Never delete branches without confirming the PR was merged or explicitly abandoned
- `.gitignore` must cover: `.env`, `backups/`, `*.sql.gz`, `logs/`, `.venv/`, any DB dumps, any TLS certs or private keys

### When Making Changes

**For SQL / database work:**
- Write migrations as numbered `.sql` files in `sql/migrations/` (e.g. `001_boost_starting_gold.sql`)
- Include both `-- UP` and `-- DOWN` sections where practical
- Always reference the actual table/column names from the live schema — query the DB first if unsure
- Wrap multi-statement changes in transactions
- For bulk content edits, prefer a Python script in `scripts/` over a giant SQL blob

**For Lua scripting:**
- Match the existing conventions of the EQ2Emu Lua codebase (look at existing spawn/spell/quest scripts first)
- Custom scripts go in `lua/` with a clear naming convention so they're distinguishable from upstream content
- Document any custom global functions or helpers at the top of the file

**For C++ server changes:**
- Work in a fork of the upstream repo, not in-place on the installed container
- Keep a patch set / changelog so upstream updates can be merged cleanly
- Prefer adding new commands/features over modifying existing behavior where possible
- Always rebuild and test in a dev container before touching production

**For Docker / infrastructure:**
- Use `docker-compose.override.yml` for local customization, never edit the upstream `docker-compose.yml` directly
- Keep secrets in `.env` (gitignored); maintain `.env.example` with placeholder values
- Document any port/volume/network changes in `docs/infrastructure.md`

**For Python automation:**
- Use a virtual environment (`.venv/`) in the project root
- Pin dependencies in `requirements.txt`
- Scripts that touch the DB should support a `--dry-run` flag by default
- Use `argparse` and include `--help` documentation for every script
- Log to both stdout and a file in `logs/` for anything that modifies data

### GM Commands and Player Management

Common tasks (boost characters, give gold, spawn gear) should almost always be done via **in-game GM commands** rather than code changes, once the account is flagged as admin. Before writing any code for these, ask: "Can this be done with an existing GM command?"

- Account admin status is set in the `account` table (login DB)
- GM command list should be documented in `docs/gm-commands.md` as we discover/use them

### Safety Rails

- **Never** drop tables or truncate without an explicit confirmation in the conversation
- **Never** modify the `login_accounts` or `character_*` tables in bulk without a backup first
- **Never** commit `.env` files, database dumps, or anything under `backups/`
- **Never** expose the admin UI (port 2424) or DB editor publicly without authentication hardening
- If a change could affect other players' characters, call it out explicitly before running

### When Unsure

- If the schema for a table isn't clear, query it: `SHOW CREATE TABLE <name>;`
- If a C++ function's behavior isn't obvious, read the full function and its callers before changing it
- If a Lua script uses an unfamiliar global, grep the codebase for its definition
- If something feels like it could break multiplayer state, pause and ask

## Useful Commands

```bash
# Git workflow basics
git checkout -b feature/short-name      # start new work
git status && git branch --show-current # verify before committing
git push -u origin feature/short-name   # push new branch
gh pr create --fill                     # open PR (if gh CLI installed)

# Bring the stack up
cd docker && docker compose up -d

# View server logs
docker compose logs -f eq2emu-server

# Shell into the server container
docker compose exec eq2emu-server bash

# MariaDB shell
docker compose exec mariadb mysql -u root -p

# Backup all databases
scripts/backup_db.py

# Rebuild server from source (if forked)
docker compose build eq2emu-server && docker compose up -d eq2emu-server
```

## Networking and Access (Cloudflare)

Friends connect to the server via a **Cloudflare-fronted domain**. See `PROJECT.md` for the full architecture, but key points for Claude Code:

- The game servers (login/world on UDP 9100/9001) **cannot** be proxied through Cloudflare's standard HTTP proxy — Cloudflare's free tier proxies HTTP/HTTPS only, not arbitrary UDP
- Options for the UDP game traffic are: (a) Cloudflare Spectrum (paid), (b) Cloudflare Tunnel with a client-side helper, (c) DNS-only A record pointing to the home IP (no proxy), or (d) require friends to join a WireGuard/Tailscale network
- Admin UI (port 2424) and DB editor should **never** be exposed via Cloudflare or any public route — stay localhost-bound, access via SSH tunnel or VPN
- Any Cloudflare config changes (DNS records, tunnel configs, WAF rules) belong in `infra/cloudflare/` as code (YAML/JSON) and are deployed via PR, not clicked through the dashboard
- Secrets for Cloudflare API (tokens, tunnel credentials) go in `.env`, never in the repo
- When the server eventually moves to cloud, the Cloudflare layer stays the same — DNS just points at the new origin

## External References

- EQ2Emu source: https://git.eq2emu.com/devn00b/EQ2EMu
- Docker stack: https://github.com/emagi/eq2emu-docker
- Wiki: https://wiki.eq2emu.com
- FAQ: https://wiki.eq2emu.com/en/Guides/FAQ
- Project site: https://www.eq2emu.com

## Out of Scope

- Monetization, donations, or any commercial use (project is strictly non-commercial per upstream policy)
- Exposing the server to the public internet without explicit security review
- Modifying the official EQ2 client binaries
- Any changes that would require redistributing Daybreak's copyrighted assets
