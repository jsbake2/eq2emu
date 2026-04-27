# Setup — bringing the stack up

This walks through getting the EQ2EMu server stack running locally from a
fresh clone of this repo. It is the baseline state that Phase 1 of
[`PROJECT.md`](../PROJECT.md) produces.

## Prerequisites

- Linux host (tested on CachyOS / Arch-family; any distro with recent
  Docker Engine works)
- Docker Engine 24+ with the Compose plugin
- `git`, `gh` (GitHub CLI), `openssl`
- Ports `3306`, `9001`, `9002`, `9100`, `9101`, `2424`, and `8080` free
  on `127.0.0.1` (see the port-conflict section below if any are in use)

Check prerequisites:

```bash
docker --version
docker compose version
openssl version
ss -tln | grep -E ':(3306|9001|9002|9100|9101|2424|8080)\b'   # should print nothing
```

## 1. Clone and enter the repo

```bash
git clone git@github.com:jsbake2/eq2emu.git
cd eq2emu
```

## 2. Create the `.env`

```bash
cp docker/.env.example docker/.env
```

Open `docker/.env` and replace every `CHANGE_ME` with a generated
password. `openssl` gives you URL-safe hex strings with no shell-escape
pitfalls:

```bash
openssl rand -hex 24
```

You will need 10 unique passwords:

- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `EQ2LS_DB_PASSWORD`
- `EQ2DAWN_DB_PASSWORD`
- `WORLD_ACCOUNT_PASSWORD` — **must be ≤30 chars.** Upstream's world
  server silently truncates this to 30 chars before hashing, so a
  48-char default would mismatch the DB hash and world→login auth
  would fail ("Bad password" in `eq2world.log`). Use
  `openssl rand -hex 14` (28 chars). See `docker/.env.example` for
  the comment flagging this constraint.
- `EQ2DAWN_ADMIN_PASSWORD`
- `EQ2WORLD_WEB_PASSWORD`
- `EQ2LOGIN_WEB_PASSWORD`
- `EQ2EDITOR_DB_PASSWORD`
- `EQ2EDITOR_ADMIN_PASSWORD`

Save the `EQ2DAWN_ADMIN_PASSWORD` and `EQ2EDITOR_ADMIN_PASSWORD`
somewhere safe — you will need them to log into the Dawn admin UI and
the DB editor. The rest are internal service credentials.

`.env` is gitignored. Never commit it.

## 3. Pre-create runtime directories with correct ownership

The compose file bind-mounts `docker/data/`, `docker/certs/`, `docker/install/`,
and `docker/eq2emu-editor/` into the containers. If Docker creates these
dirs on its own during `up`, they end up owned by `root:root` and the
container processes can't write to them — mariadbd fails its healthcheck
and the eq2emu-server entrypoint gets permission errors mid-setup.

Create the dirs up front with the ownership each container expects:

```bash
mkdir -p docker/data docker/certs docker/install docker/eq2emu-editor
sudo chown 999:999   docker/data docker/certs           # mariadb user inside the image
sudo chown 1000:1000 docker/install docker/eq2emu-editor # eq2emu user inside the image
```

This is a one-time step per checkout. After the first `compose up`, these
dirs remain correctly owned.

## 4. Bring the stack up

```bash
cd docker
docker compose up -d --build
```

First run takes 10–20 minutes: it downloads the MariaDB image, builds
the eq2emu-server image (which compiles the C++ server from source),
builds the eq2emu-editor image, seeds the login and world databases,
and generates self-signed TLS certs for the Dawn admin UI.

Follow build progress with:

```bash
docker compose logs -f eq2emu-server
```

Expect to see the server finish compiling, then start world and login
processes, then open the Dawn web listener on `:2424`.

## 5. Verify services

All services should be `running (healthy)`:

```bash
docker compose ps
```

Services and host bindings:

| Service | Host binding | Purpose |
| --- | --- | --- |
| `mysql` | `127.0.0.1:3306` | MariaDB (login, world, dawn, editor DBs) |
| `eq2emu-server` | `127.0.0.1:9001/udp` | World client port |
| `eq2emu-server` | `127.0.0.1:9100/udp` | Login client port |
| `eq2emu-server` | `127.0.0.1:9002/tcp` | World web API |
| `eq2emu-server` | `127.0.0.1:9101/tcp` | Login web API |
| `eq2emu-server` | `127.0.0.1:2424/tcp` | Dawn admin UI (HTTPS) |
| `eq2emu-editor` | `127.0.0.1:8080/tcp` | EQ2EMu DB editor |

Smoke tests:

```bash
curl -ksI https://127.0.0.1:2424/ | head -1       # Dawn admin UI
curl -sI  http://127.0.0.1:8080/eq2db | head -1   # DB editor
```

Both should return `HTTP/1.1 200` (or a redirect) once the services are
up. The `-k` flag on the first one skips TLS verification because the
Dawn UI uses a self-signed cert.

## 6. Log into the web interfaces

- **Dawn admin UI:** <https://127.0.0.1:2424>
  - Accept the self-signed cert warning in your browser.
  - Password: `EQ2DAWN_ADMIN_PASSWORD` from `docker/.env`.
- **DB editor:** <http://127.0.0.1:8080/eq2db>
  - User: `admin`
  - Password: `EQ2EDITOR_ADMIN_PASSWORD` from `docker/.env`.

Neither of these is exposed beyond `127.0.0.1`. Accessing them from
another machine requires an SSH tunnel or (eventually) a VPN.

## 7. Connect the EQ2 client

The client runs on Windows (official EQ2 from Steam). It does not run on
the Linux host; point a Windows client at the server from the same LAN,
or tunnel through Tailscale / WireGuard once Phase 3 is done.

Edit `eq2_default.ini` in the client install directory and set:

```
cl_ls_address=<server-ip>
```

For a local test from the same machine (Linux host running the stack,
EQ2 client in a VM or the same host via another means), use
`127.0.0.1`. For a LAN test, substitute the host's LAN IP and update
`IP_ADDRESS` + `LISTEN_PORT_ADDRESS` in `docker/.env` before bringing
the stack up.

Create a test account via the Dawn admin UI or via the DB editor, then
log in through the client and enter the world.

## Port conflicts

If `ss -tln` shows a conflict on any required port before bringing the
stack up, decide per port:

- **80** — upstream default for the DB editor. We use **8080** instead
  to avoid clashing with an existing caddy container on this host.
  That change is pinned in `docker/.env.example` as `DBWEB_SERVER_PORT=8080`.
- **3306** — if another DB is already running, change the mapping in
  `docker/docker-compose.override.yaml` to e.g. `127.0.0.1:33306:3306`.
- **9001 / 9100** — these are the UDP ports clients connect to. If
  they conflict, the client must be reconfigured too, since EQ2 has
  hardcoded expectations. Better to stop the other process.
- **2424, 9002, 9101** — change in `docker/.env` and update docs.

## Teardown

```bash
cd docker
docker compose down          # stops containers, preserves data
docker compose down -v       # stops and deletes volumes (full wipe)
```

The named volume for MariaDB lives at `docker/data/` — nuking it is a
full reset. Back up first (once Phase 2 automates backups) before doing
a `down -v`.

## Upgrading / syncing from upstream

See [`docker/README.md`](../docker/README.md) for the vendor-sync
procedure. Don't edit vendored files outside a sync PR; use
`docker-compose.override.yaml` and `.env` for local changes.

## Known issues

- **Dir ownership on first run:** if you skip the `chown` step in
  section 3, mariadbd and the eq2emu-server entrypoint both fail with
  "Permission denied" writing into the bind-mounted host dirs. Recovery
  is: `docker compose down`, apply the `chown`s, delete
  `docker/install/dawn_install` and `docker/install/firstrun_dbeditor`
  if they were touched by the failed run, then bring the stack up
  again. The `first_install` marker can stay — DBs are safe to keep.
- **First-run certificate race:** the `cert-gen` service generates the
  MariaDB SSL certs, but if you bring the stack up before it finishes
  and `mysql` starts looking for them, you can get a boot loop.
  `docker compose down && docker compose up -d` usually sorts it.
- **Dawn UI reports login/world offline after an image update:** per
  upstream README, delete `docker/install/dawn_install` and bounce the
  stack. That regenerates the Dawn ↔ login/world auth certs.
- **Port 80 conflict on this host:** caddy is already bound to
  `127.0.0.1:80`. The DB editor uses 8080 instead to avoid this. If
  you stop caddy and want to move the editor back, change
  `DBWEB_SERVER_PORT` in `.env`.
- **Recast `-Werror=All` build failure:** fixed by our local patch in
  `docker/containers/eq2emu-server/install.sh`. See
  `docker/README.md` under "Local patches" for context. Without the
  patch, modern GCC rejects a malformed flag from premake5 and the
  `eq2world` binary fails to link.
