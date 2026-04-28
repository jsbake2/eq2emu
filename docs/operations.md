# Server operations runbook

How to start the EQ2Emu stack, stop it cleanly, and recover from common
failure modes — for the operator running things solo without a session
context.

## Lifecycle in one paragraph

The homelab runs the stack as a docker-compose project. Source patches
live in `server-patches/` and are re-applied to the in-container source
on every start (the container's source clone gets reset on recreation,
so patches must be re-applied each time). Two scripts wrap the full
flow: `scripts/server-up.sh` and `scripts/server-down.sh`. DB data and
the binary live in volumes that persist across restarts.

## Start

```bash
./scripts/server-up.sh
```

What happens, in order:

1. `docker compose up -d` brings up `mysql`, `eq2emu-server`, and
   `eq2emu-editor` (the dbweb editor; needs port 8081 free).
2. The script waits for MariaDB to report healthy and for eq2world to
   log "Connected to LoginServer."
3. `scripts/apply-server-patches.sh` runs every `*.patch` in
   `server-patches/` against `/eq2emu/eq2emu/source/` inside the
   container. Patches that already apply in reverse are reported as
   `[skip] (already applied)`. Patches that need 3-way merge fall back
   to that automatically.
4. The script compares mtimes — if any patched source file is newer
   than the running `eq2world` binary, it rebuilds (`make -j$(nproc)`)
   and hot-swaps the new binary. The old binary is renamed
   `eq2world.pre-up-<timestamp>` so you can roll back manually.
5. `ss -ulnp` is run to verify UDP 9001 and 9100 are listening on both
   `127.0.0.1` and `192.168.122.1`. The libvirt bridge binding is
   important if the GM-account VM (or the eventual Tailscale exit node)
   needs to reach the server through anything other than localhost.

Total time on a clean start: ~30s for compose to come up, plus 1-2 min
if a rebuild is needed.

## Stop

```bash
./scripts/server-down.sh
```

This runs `docker compose down`. Stopping is fast (~10s).

What persists across stop+start:

- **MySQL data** — character_*, accounts, ruleset_details, bots,
  bot_appearance, etc. All of it.
- **Server binary** — `/eq2emu/eq2emu/server/eq2world` lives in an
  anonymous compose volume that survives `down`.
- **Cert files** — bind-mounted from `docker/certs/`.

What gets reset:

- **Source clone** — `/eq2emu/eq2emu/source/` resets to upstream HEAD
  whenever the container is recreated by `up` after a `down`. The
  `server-up.sh` script re-applies patches to handle this.
- **In-container Python scripts** — anything you `docker cp`'d in is
  gone. Persistent helpers should live in `scripts/` and run via
  `docker exec` from the host.

## What to do when…

### …`server-up.sh` hangs at "waiting for eq2world"

eq2world failed to start. Tail the log:

```bash
docker exec docker-eq2emu-server-1 \
  tail -40 /eq2emu/eq2emu/server/logs/eq2world.log
```

Most common cause: a fresh container ran `install.sh`, which downloads
the world DB seed and imports it; this can take a couple of minutes on
the very first run. Subsequent runs reuse the existing DB.

Second most common: a build error after patch apply. Check for
`error:` in the make output or for an `eq2world.pre-up-*` file
without a fresh `eq2world` next to it.

### …game ports aren't listening on `192.168.122.1`

Check `docker/docker-compose.override.yaml` — that file declares the
dual binding on `127.0.0.1` and `192.168.122.1`. If the override file
is missing or malformed, ports collapse to whatever upstream
`docker-compose.yaml` declares (`${LISTEN_PORT_ADDRESS}` from `.env`,
which is `127.0.0.1` only).

### …a patch fails to apply

`scripts/apply-server-patches.sh` reports `[fail]` and exits non-zero.
Read the patch file at `server-patches/<name>.patch` and the source
file it targets — usually the line offsets drifted because a previous
patch in the chain inserted or removed lines. Hand-edit the hunk
header to point at the right line range, or regenerate from the
container's current state:

```bash
docker exec docker-eq2emu-server-1 \
  sh -c 'cd /eq2emu/eq2emu/source && git diff -- <paths>' \
  > server-patches/<name>.patch
```

### …something feels wrong and you want a clean reset

```bash
./scripts/server-down.sh
docker compose -f docker/docker-compose.yaml down -v   # WIPES DB AND BINARY VOLUMES
./scripts/server-up.sh
```

The `-v` flag removes named/anonymous volumes — you lose all character
data, bot rosters, ruleset overrides, and the patched binary. The
first `up` after a `-v` down will redownload and re-seed the world DB,
which takes 5-10 minutes.

Don't do this lightly. Take a `mysqldump` first if there's anything
worth saving.

### …`docker compose` complains about port 8080

The `eq2emu-editor` container wants port 8080 by default but on this
host port 8080 is held by `activepieces-app`. The committed
`docker/.env.example` already moves the editor to 8081 — make sure
your live `docker/.env` has `DBWEB_SERVER_PORT=8081`. The editor URL
is then `http://127.0.0.1:8081/eq2db`.

## Auto-start on host reboot (optional)

A systemd unit at `infra/systemd/eq2emu.service` wraps `server-up.sh`
and `server-down.sh` so the stack comes up on boot and shuts down
cleanly on poweroff. Install once:

```bash
sudo cp infra/systemd/eq2emu.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eq2emu.service
```

The unit runs as user `jbaker` (must be in the `docker` group) with
`WorkingDirectory=/home/jbaker/repos/eq2emu`. It's `Type=oneshot`
with `RemainAfterExit=yes` — once `server-up.sh` exits 0, systemd
treats the service as active and `ExecStop` triggers `server-down.sh`
on shutdown.

Useful commands:

```bash
sudo systemctl status eq2emu          # current state + last log lines
sudo journalctl -u eq2emu -f          # tail the start/stop output
sudo systemctl restart eq2emu         # full down + up cycle
sudo systemctl disable eq2emu         # stop auto-starting on boot
```

If you change the unit file in the repo, re-copy it and reload:

```bash
sudo cp infra/systemd/eq2emu.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## What's *not* automated yet

- **DB backup before destructive ops** — operator's responsibility for
  now. There's a Phase-2 task for an automated backup script;
  meanwhile, `mysqldump` from `docker exec docker-mysql-1 ...` is the
  go-to.
- **Patch series test before merging** — when adding a new patch, run
  `./scripts/apply-server-patches.sh` against a freshly-recreated
  container to confirm it applies cleanly without `--3way`. Drifty
  patches should be regenerated, not relied on for fuzz-merging.
- **Tailscale up** — if the friend-access plan kicks in,
  `sudo tailscale up` on the host is still a manual one-time step.
  See `docs/tailscale-setup.md`.
- **GM client VM lifecycle** — `virsh start eq2-gm-vm` and
  `virsh shutdown eq2-gm-vm` aren't wrapped in these scripts; they're
  independent of the server stack. See `docs/gm-client-vm.md`.

## Branch hygiene

The scripts live in `scripts/` and the doc lives in `docs/`. Any
changes to startup behavior should land via `infra/` branches and
PRs per `docs/git-workflow.md`. Don't edit `server-up.sh` on the
homelab machine and forget to commit — that's how patches got lost
last week.
