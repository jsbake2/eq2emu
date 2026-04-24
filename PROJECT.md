# PROJECT.md

## Overview

A private **EverQuest II emulator server** hosted on a personal Linux homelab, intended for a small group of friends. Built on the open-source [EQ2Emu](https://www.eq2emu.com) project (GPLv3) using the containerized [eq2emu-docker](https://github.com/emagi/eq2emu-docker) stack.

The server is non-commercial, educational, and strictly for preservation/fun. No donations, no public advertising, no monetization.

## Goals

### Primary
- **Stable private server** for a small group of friends to play classic-era EQ2 (circa 2004–2006)
- **Low-touch operations** — backups automated, updates manageable, recovery possible within an hour
- **Customization playground** — freedom to tweak rates, loot, spawns, and mechanics without breaking core stability

### Secondary
- Learn the EQ2Emu C++ and Lua codebase well enough to make targeted changes
- Build a library of custom GM commands, scripts, and SQL modifications that survive upstream updates
- Optionally contribute bug fixes or features back to upstream

### Non-Goals
- Running a large public server
- Recreating modern-era EQ2 expansions (the emulator is classic-focused)
- Monetization of any kind
- Exposure to the open internet without a well-considered security posture

## Architecture

### Components

| Component | Purpose | Tech |
|-----------|---------|------|
| Login server | Handles account auth, routes clients to world | C++ (UDP 9100) |
| World server | Global state, chat, character list | C++ (UDP 9001) |
| Zone server(s) | Per-zone gameplay logic | C++ |
| MariaDB | Login, world, and dawn databases | MariaDB in container |
| Dawn admin UI | Web-based server admin dashboard | NodeJS (HTTPS 2424, localhost-bound) |
| EQ2 DB Editor | Web-based content/schema editor | Web (HTTP, localhost-bound) |
| Cloudflare | DNS + edge for the public access point | Cloudflare (DNS, optionally Spectrum/Tunnel) |
| Client | Official EQ2 from Steam, patched config | Windows |

### Access Point (Cloudflare)

Friends connect via a Cloudflare-managed domain. The domain is already registered with Cloudflare DNS; the open question is *how* traffic reaches the home origin.

**Constraint:** Cloudflare's standard HTTP proxy does not proxy arbitrary UDP. The EQ2 game protocol is UDP on ports 9100 (login) and 9001 (world). This leaves four realistic options:

| Option | Pros | Cons |
|--------|------|------|
| **DNS-only A record** (gray cloud) | Simple, free, friends just use the domain | Exposes home IP; no DDoS protection; requires port forward |
| **Cloudflare Spectrum** | UDP proxy with DDoS protection, hides origin IP | Paid (Enterprise tier historically; pricing varies) |
| **Cloudflare Tunnel + helper** | Hides origin IP, no port forward | Requires a client-side connector for UDP; more moving parts |
| **WireGuard / Tailscale VPN** | Hides everything, strong auth, no proxy needed | Friends must install a VPN client |

**Current leaning:** Start with DNS-only A record for simplicity, move to VPN (Tailscale is the likely fit) before inviting friends, revisit Spectrum only if there's a real need. The Cloudflare domain is useful even in the VPN model — it gives friends a stable hostname that doesn't change if the home IP rotates.

**What stays on Cloudflare regardless:**
- Authoritative DNS for the domain
- (Future) HTTPS endpoint for a server status/info page, if built
- (Future) Access policies if the admin UI is ever exposed remotely

**What must never be on Cloudflare (or any public route):**
- Dawn admin UI (port 2424)
- EQ2 DB Editor
- MariaDB port
- SSH on a non-standard port with key-only auth is fine; password auth is not

### Network Topology (initial)

```
[Friends' EQ2 clients]
        │
        │ (Phase 2+: Tailscale tunnel, or DNS-only A record)
        ▼
[Cloudflare DNS] ──► server.<yourdomain> ──► [Home public IP]
                                                    │
                                                    │ UDP 9100 / 9001
                                                    ▼
                                          [Linux homelab host]
                                                    │
                                                    ▼
                                          [Docker compose stack]
                                            ├── eq2emu-server
                                            ├── mariadb
                                            ├── dawn (localhost only)
                                            └── eq2db (localhost only)
```

Admin access (Dawn UI, DB editor, container shells) happens via SSH or VPN to the homelab — never through Cloudflare.

## Phases

Each phase is intended to produce one or more **pull requests** against `main`. PRs are the milestone marker — if a phase item is done, it's in `main` via a merged PR.

### Phase 0 — Repo Setup (Day 1)
- [ ] Initialize git repo, push to origin (GitHub/GitLab — TBD)
- [ ] Add `CLAUDE.md`, `PROJECT.md`, and `.gitignore` as the first commit on `main`
- [ ] Protect `main` (require PRs, no force-push)
- [ ] Create `docs/`, `infra/cloudflare/` as empty directories with `.gitkeep`
- [ ] First PR: branch protection rules documented in `docs/git-workflow.md`

### Phase 1 — Get It Running (Week 1)
- [ ] Clone `eq2emu-docker` into `docker/` (or as a submodule — decide)
- [ ] Configure `.env` with strong passwords for admin UI, DB editor, MariaDB root
- [ ] Bring the stack up, verify all containers healthy
- [ ] Connect one EQ2 client locally, create a test account, enter world
- [ ] Document the baseline in `docs/setup.md`
- [ ] **PR:** "Phase 1: initial server stack running locally"

### Phase 2 — Harden and Back Up (Week 1–2)
- [ ] Set up automated MariaDB dumps to a separate volume (daily, 7-day retention)
- [ ] Script a full-stack backup (DB + Lua + config) to local NAS
- [ ] Test restore procedure on a scratch VM
- [ ] Configure firewall rules on the Linux host — only game ports exposed
- [ ] **PR:** "Phase 2: automated backups and host hardening"

### Phase 3 — Cloudflare and Remote Access (Week 2)
- [ ] Decide access model: DNS-only, Tailscale VPN, or hybrid (see Architecture)
- [ ] Create DNS records in Cloudflare (A record for game server hostname)
- [ ] Document the record definitions in `infra/cloudflare/dns.yaml` (or similar as-code format)
- [ ] If VPN: stand up Tailscale, document friend onboarding in `docs/friend-onboarding.md`
- [ ] Verify an external client can connect through the chosen path
- [ ] **PR:** "Phase 3: Cloudflare DNS and remote access"

### Phase 4 — Admin Tooling (Week 2–3)
- [ ] Flag primary account as GM/admin in DB
- [ ] Document working GM commands in `docs/gm-commands.md`
- [ ] Write Python helper: bulk account creation for friends
- [ ] Write Python helper: character boost script (level, gold, starter gear)
- [ ] Set up a dev/staging copy of the stack on a second port range for testing changes
- [ ] **PR:** per script (keep PRs small — one tool per PR)

### Phase 5 — Customization (Ongoing)
- [ ] First Lua tweak: adjust XP rates or loot drop rates as a learning exercise
- [ ] Identify and patch any quality-of-life bugs encountered during play
- [ ] Build a personal library of custom spawn scripts and SQL content edits
- [ ] Evaluate whether a C++ fork is worth maintaining vs. living with upstream
- [ ] **PR:** per customization, labeled `content:` or `feat:` as appropriate

### Phase 6 — Cloud Migration (Future)
- [ ] Choose target (AWS EC2, Hetzner, OVH — TBD; cost and latency driven)
- [ ] Provision via Terraform or similar IaC in `infra/<provider>/`
- [ ] Replicate the docker stack on the cloud host
- [ ] Migrate DNS: Cloudflare A record points at new origin
- [ ] Migrate data: final backup on home, restore on cloud, cut over during downtime window
- [ ] Verify friends can connect; keep home stack as cold standby for 2 weeks
- [ ] Decommission home stack
- [ ] **PR series:** "Phase 6a: provision cloud infra", "Phase 6b: data migration", "Phase 6c: cutover"

### Phase 7 — Optional Extensions
- [ ] Custom GM commands for common tasks (bulk gear, teleport presets)
- [ ] Discord bot bridge for server status / chat relay
- [ ] Automated world-event scripts (scheduled spawns, holiday content)
- [ ] Contribute fixes back upstream if any are broadly useful

## Open Questions / Decisions to Make

- **Remote access model:** DNS-only A record, Tailscale VPN, Cloudflare Spectrum, or Cloudflare Tunnel? (Leaning Tailscale — free for small groups, best security posture, and simplest friend onboarding after install.)
- **Git host:** GitHub, GitLab, or self-hosted? (GitHub probably — ubiquity, free private repos, `gh` CLI works well with Claude Code.)
- **Upstream sync cadence:** pull upstream changes monthly, quarterly, or only when needed? A fork with custom patches will need a merge strategy.
- **Client version / era:** which EQ2 client build to standardize friends on? (Affects compatibility with the emulator's current support level.)
- **Staging environment:** separate host, separate compose project on the same host, or ephemeral containers spun up per-change?
- **Cloud target for Phase 6:** cost vs. latency vs. complexity. Hetzner is cheapest; AWS has best tooling; a small VPS somewhere close to friends minimizes ping.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Upstream breaking change wipes customizations | Keep custom Lua/SQL in version-controlled repo separate from upstream; test upstream updates in staging first; PRs make changes reviewable |
| AMD CPU crashes on certain clients | Document which client builds work; flag this in friend onboarding |
| Someone accidentally drops a production table | Automated daily backups + readonly DB user for exploration queries; PR review catches destructive migrations |
| Exposure of admin UI to the internet | Bind admin services to localhost; require SSH tunnel or VPN for admin access; never route through Cloudflare |
| Home IP exposed via DNS-only Cloudflare record | Move to VPN (Tailscale) or Cloudflare Spectrum before going public |
| Friends' accounts getting into weird states from experimentation | Keep a staging server for testing; avoid testing on real characters |
| Loss of the host machine (disk failure, etc.) | Off-host backups to NAS; documented restore procedure tested quarterly; Phase 6 cloud migration provides geo-redundancy |
| Force-push or bad merge corrupts `main` | Branch protection on `main`; PR-only workflow; no direct commits allowed |
| Secrets committed to git (.env, Cloudflare tokens, TLS keys) | Strict `.gitignore`; pre-commit hook to scan for obvious secrets; `.env.example` only |

## Success Criteria

- Server runs for 30 days without unplanned downtime
- At least 3 friends have accounts, have connected via the Cloudflare hostname, and have played
- Restore-from-backup procedure has been tested end-to-end at least once
- At least one meaningful customization (XP rate, loot table, or similar) has been applied and documented
- Someone other than the operator could, with the docs in this repo, stand up a fresh copy of the server
- Every meaningful change in `main` is traceable to a PR with a clear description
- No secrets have ever been committed to the repo

## References

- EQ2Emu main site: https://www.eq2emu.com
- Source: https://git.eq2emu.com/devn00b/EQ2EMu
- Docker stack: https://github.com/emagi/eq2emu-docker
- Wiki: https://wiki.eq2emu.com
- FAQ: https://wiki.eq2emu.com/en/Guides/FAQ
- EQ2Emu Discord: (linked from eq2emu.com — primary community support channel)
