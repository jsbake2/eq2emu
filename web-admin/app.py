"""EQ2Emu private-server admin dashboard.

Single-file FastAPI app that wraps the existing scripts in scripts/ and
the docker compose stack. Single-password auth (scrypt hash in
secrets.json). Binds 127.0.0.1:8890 — never exposed publicly per the
project's safety rules (CLAUDE.md).

Tabs:
  * Server      — docker compose status, Start/Stop/Restart, log tail
  * Characters  — search by name; race/gender, resources, gear-up,
                  character template, bank-items spawn (each has a
                  --dry-run preview before write)
  * Items       — embed of the existing mastercrafted handouts catalog

Scripts are subprocessed (not imported) so they keep their own
argument parsing and error handling. Each script that mutates the DB
supports --dry-run; the UI runs dry-run first, shows output, and
requires an explicit confirm before running for real.
"""

import asyncio
import hashlib
import json
import os
import secrets
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymysql
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
REPO = HERE.parent
SCRIPTS = REPO / "scripts"
DOCS = REPO / "docs"
DOCKER_DIR = REPO / "docker"
DOTENV = DOCKER_DIR / ".env"
PYTHON = REPO / ".venv" / "bin" / "python"
STATIC = HERE / "static"
SECRETS_PATH = HERE / "secrets.json"

# Docker container names (matching the existing scripts' defaults).
MYSQL_CONTAINER = os.environ.get("EQ2EMU_MYSQL_CONTAINER", "docker-mysql-1")
SERVER_CONTAINER = os.environ.get("EQ2EMU_SERVER_CONTAINER", "docker-eq2emu-server-1")

# Logs from this container are what the operator usually wants to see.
LOG_CONTAINER = SERVER_CONTAINER

# DB credentials parsed from docker/.env. Kept process-local; never echoed.
def _parse_dotenv() -> dict[str, str]:
    if not DOTENV.exists():
        raise RuntimeError(f"missing {DOTENV} — admin app cannot reach the DB")
    out: dict[str, str] = {}
    for raw in DOTENV.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_ENV = _parse_dotenv()
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASS = _ENV.get("MARIADB_ROOT_PASSWORD", "")
DB_NAME = _ENV.get("MARIADB_DATABASE", "eq2emu")


def db_conn():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        raise RuntimeError(
            f"missing {SECRETS_PATH} — run set_password.py to bootstrap"
        )
    return json.loads(SECRETS_PATH.read_text())


def verify_password(password: str, encoded: str) -> bool:
    """scrypt$1$n$r$p$salt_hex$hash_hex — same format as set_password.py."""
    try:
        scheme, _ver, n, r, p, salt_hex, hash_hex = encoded.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    derived = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt_hex),
        n=int(n), r=int(r), p=int(p),
        dklen=len(hash_hex) // 2,
    )
    return secrets.compare_digest(derived.hex(), hash_hex)


_SECRETS = _load_secrets()
PASSWORD_HASH = _SECRETS["dashboard_password_hash"]
VALID_TOKENS: set[str] = set()


def check_auth(request: Request) -> bool:
    return request.cookies.get("eq2_token") in VALID_TOKENS


# ---------------------------------------------------------------------------
# FastAPI app + middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="EQ2Emu Admin")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/api/login") or path.startswith("/static"):
        return await call_next(request)
    if not check_auth(request):
        if path.startswith("/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login")
    return await call_next(request)


# ---------------------------------------------------------------------------
# Routes — root, login, logout
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/login")
async def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.post("/api/login")
async def do_login(request: Request):
    body = await request.json()
    if not verify_password(body.get("password") or "", PASSWORD_HASH):
        return JSONResponse({"error": "wrong password"}, status_code=401)
    token = secrets.token_hex(32)
    VALID_TOKENS.add(token)
    response = JSONResponse({"ok": True})
    response.set_cookie("eq2_token", token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


@app.post("/api/logout")
async def do_logout(request: Request):
    VALID_TOKENS.discard(request.cookies.get("eq2_token"))
    response = RedirectResponse("/login")
    response.delete_cookie("eq2_token")
    return response


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------
def run_cmd(argv: list[str], cwd: Path = REPO, timeout: int = 60) -> dict:
    """Run a shell command, capture stdout+stderr. Always returns a dict
    with keys: ok, returncode, stdout, stderr, command (echo'd)."""
    cmd_str = " ".join(shlex.quote(a) for a in argv)
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": (e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
            "stderr": f"TIMEOUT after {timeout}s",
            "command": cmd_str,
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-4000:],
        "command": cmd_str,
    }


def run_script(script: str, *args: str, dry_run: bool = False, timeout: int = 60) -> dict:
    """Run a python or shell script in scripts/ with the given args.
    Auto-prepends --dry-run for python scripts when requested."""
    path = SCRIPTS / script
    if not path.exists():
        return {
            "ok": False,
            "returncode": -2,
            "stdout": "",
            "stderr": f"script not found: scripts/{script} (PR may not be merged yet)",
            "command": f"scripts/{script}",
        }
    if path.suffix == ".py":
        argv = [str(PYTHON), str(path), *args]
        if dry_run:
            argv.append("--dry-run")
    else:
        argv = [str(path), *args]
    return run_cmd(argv, timeout=timeout)


# ---------------------------------------------------------------------------
# Server tab
# ---------------------------------------------------------------------------
@app.get("/api/server/status")
async def server_status():
    """docker compose ps + listening port snapshot. Quick — ~1s."""
    ps = await asyncio.to_thread(
        run_cmd,
        ["docker", "compose", "ps", "--format", "json"],
        DOCKER_DIR,
        12,
    )
    containers: list[dict] = []
    if ps["ok"] and ps["stdout"].strip():
        for line in ps["stdout"].splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    # Game-relevant ports (login + world + admin UI). 'ss' is faster than
    # netstat and ships in the base CachyOS image.
    ports = await asyncio.to_thread(run_cmd, ["ss", "-tlnu"], REPO, 5)
    return {
        "containers": containers,
        "ports_snippet": ports["stdout"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/server/logs")
async def server_logs(n: int = 200):
    """Tail the eq2emu-server container log. Capped at 1000 lines."""
    n = max(20, min(n, 1000))
    raw = await asyncio.to_thread(
        run_cmd,
        ["docker", "logs", "--tail", str(n), LOG_CONTAINER],
        REPO,
        15,
    )
    lines = (raw["stdout"] + raw["stderr"]).splitlines()
    return {"lines": lines[-n:]}


@app.post("/api/server/start")
async def server_start():
    result = await asyncio.to_thread(run_script, "server-up.sh", timeout=180)
    return result


@app.post("/api/server/stop")
async def server_stop():
    result = await asyncio.to_thread(run_script, "server-down.sh", timeout=60)
    return result


@app.post("/api/server/restart")
async def server_restart():
    """down then up. Reuses the existing scripts so the restart matches the
    operator's documented manual flow exactly."""
    down = await asyncio.to_thread(run_script, "server-down.sh", timeout=60)
    if not down["ok"]:
        return {"step": "stop", **down}
    up = await asyncio.to_thread(run_script, "server-up.sh", timeout=180)
    return {"step": "start", **up, "stop_stdout": down["stdout"][-2000:]}


# ---------------------------------------------------------------------------
# Characters tab
# ---------------------------------------------------------------------------
@app.get("/api/characters/search")
async def characters_search(q: str = ""):
    """Substring match by character name. Returns up to 50 rows with
    enough info to populate the picker dropdown."""
    q = q.strip()
    if not q:
        return {"rows": []}
    sql = """
        SELECT c.id, c.name, c.race, c.gender, c.`class` AS adventure_class,
               c.tradeskill_class, c.current_zone_id, c.admin_status,
               c.level, c.tradeskill_level, cd.status_points
          FROM characters c
          LEFT JOIN character_details cd ON cd.char_id = c.id
         WHERE c.name LIKE %s AND c.deleted = 0
         ORDER BY c.name
         LIMIT 50
    """
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (f"%{q}%",))
                rows = cur.fetchall()
    except pymysql.MySQLError as e:
        return JSONResponse({"error": f"DB error: {e}"}, status_code=500)
    return {"rows": rows}


@app.get("/api/characters/{name}/info")
async def character_info(name: str):
    """Full single-character snapshot for the form pre-fill."""
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.id, c.name, c.race, c.gender,
                           c.`class` AS adventure_class, c.tradeskill_class,
                           c.level, c.tradeskill_level,
                           c.current_zone_id, c.admin_status, c.is_online,
                           cd.coin_copper, cd.coin_silver, cd.coin_gold,
                           cd.coin_plat, cd.status_points
                      FROM characters c
                      LEFT JOIN character_details cd ON cd.char_id = c.id
                     WHERE c.name = %s AND c.deleted = 0
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    return JSONResponse({"error": "not found"}, status_code=404)
                cur.execute(
                    "SELECT name, faction_id, faction_level "
                    "FROM character_factions cf "
                    "JOIN factions f ON f.id = cf.faction_id "
                    "WHERE cf.char_id = %s "
                    "ORDER BY f.name LIMIT 200",
                    (row["id"],),
                )
                factions = cur.fetchall()
    except pymysql.MySQLError as e:
        return JSONResponse({"error": f"DB error: {e}"}, status_code=500)
    return {"character": row, "factions": factions}


@app.post("/api/characters/{name}/race-gender")
async def character_race_gender(name: str, body: dict):
    args: list[str] = ["--name", name]
    if body.get("race"):
        args += ["--race", str(body["race"])]
    if body.get("gender"):
        args += ["--gender", str(body["gender"])]
    if body.get("force"):
        args.append("--force")
    return await asyncio.to_thread(
        run_script, "change-race-gender.py", *args,
        dry_run=bool(body.get("dry_run", True)),
    )


@app.post("/api/characters/{name}/give-resources")
async def character_give_resources(name: str, body: dict):
    args: list[str] = ["--name", name]
    for k in ("plat", "gold", "silver", "copper", "status"):
        v = body.get(k)
        if v not in (None, "", 0, "0"):
            args += [f"--{k}", str(v)]
    for f in body.get("factions") or []:
        # f is "Name=Amount"
        if isinstance(f, str) and "=" in f:
            args += ["--faction", f]
    if body.get("force"):
        args.append("--force")
    return await asyncio.to_thread(
        run_script, "give-resources.py", *args,
        dry_run=bool(body.get("dry_run", True)),
    )


@app.post("/api/characters/{name}/gear-up")
async def character_gear_up(name: str, body: dict):
    """gear-up.py wraps mastercrafted-only equipping. Lives on a
    separate PR branch; the script-not-found path returns a clean error."""
    args: list[str] = ["--player", name]
    if body.get("force"):
        args.append("--force")
    return await asyncio.to_thread(
        run_script, "gear-up.py", *args,
        dry_run=bool(body.get("dry_run", True)),
        timeout=120,
    )


@app.post("/api/characters/{name}/apply-template")
async def character_apply_template(name: str, body: dict):
    """apply-character-template.sh — applies macros, skillbar, keymap, UI
    settings. No --dry-run flag on this script; the form must be
    explicit about that.

    Body: {no_admin: bool}  (default false → grants admin_status=200)
    """
    args: list[str] = [name]
    if body.get("no_admin"):
        args.append("--no-admin")
    return await asyncio.to_thread(run_script, "apply-character-template.sh", *args, timeout=60)


@app.post("/api/characters/{name}/spawn-bank-items")
async def character_spawn_bank_items(name: str, body: dict):
    """spawn-bank-items.py reads a YAML spec. The web form posts the
    YAML body inline; we write it to a tempfile and pass the path."""
    yaml_text = body.get("yaml") or ""
    if not yaml_text.strip():
        return JSONResponse({"error": "empty yaml"}, status_code=400)
    args: list[str] = []
    if body.get("replace"):
        args.append("--replace")
    if body.get("force"):
        args.append("--force")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(REPO), prefix=".bank-spawn-"
    ) as tf:
        tf.write(yaml_text)
        tf_path = tf.name
    try:
        return await asyncio.to_thread(
            run_script,
            "spawn-bank-items.py",
            *args,
            tf_path,
            dry_run=bool(body.get("dry_run", True)),
            timeout=60,
        )
    finally:
        try:
            os.unlink(tf_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Items tab — embed of the existing catalog page
# ---------------------------------------------------------------------------
@app.get("/api/catalog")
async def catalog():
    """Serve docs/mastercrafted-handouts.html through the auth gate so
    the iframe in the dashboard can show it without a separate login."""
    target = DOCS / "mastercrafted-handouts.html"
    if not target.exists():
        return PlainTextResponse(
            "Catalog HTML not found. Run scripts/gen-mastercrafted-handouts.py "
            "to generate docs/mastercrafted-handouts.html.",
            status_code=404,
        )
    return FileResponse(target, media_type="text/html")


@app.post("/api/catalog/regen")
async def catalog_regen():
    return await asyncio.to_thread(
        run_script, "gen-mastercrafted-handouts.py", timeout=120
    )


# ---------------------------------------------------------------------------
# WebSocket — live status updates (polled server-side, pushed to client)
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_status(ws: WebSocket):
    if ws.cookies.get("eq2_token") not in VALID_TOKENS:
        await ws.close(code=4001, reason="unauthorized")
        return
    await ws.accept()
    try:
        while True:
            try:
                ps = await asyncio.to_thread(
                    run_cmd,
                    ["docker", "compose", "ps", "--format", "json"],
                    DOCKER_DIR,
                    8,
                )
                containers: list[dict] = []
                if ps["ok"]:
                    for line in ps["stdout"].splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            containers.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                await ws.send_json({
                    "type": "status",
                    "containers": containers,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                await ws.send_json({"type": "error", "message": str(e)})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Login HTML (single string — keeps deployment to one .py + one static dir)
# ---------------------------------------------------------------------------
LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EQ2Emu Admin — Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter',sans-serif; background:#0a0a0f; color:#e8e8f0;
       min-height:100vh; display:flex; align-items:center; justify-content:center; }
.card { background:#16161f; border:1px solid #2a2a3a; border-radius:12px;
        padding:40px; width:380px; box-shadow:0 4px 24px rgba(0,0,0,0.4); }
.logo { width:48px; height:48px; background:rgba(96,165,250,0.12); border-radius:10px;
        display:flex; align-items:center; justify-content:center; font-size:22px;
        font-weight:700; color:#60a5fa; margin:0 auto 20px; }
h1 { text-align:center; font-size:20px; margin-bottom:6px; }
.sub { text-align:center; font-size:13px; color:#8888a0; margin-bottom:28px; }
label { font-size:12px; font-weight:500; color:#8888a0; text-transform:uppercase;
        letter-spacing:.6px; }
input { width:100%; padding:12px 14px; margin:8px 0 20px; border-radius:8px;
        border:1px solid #2a2a3a; background:#1a1a26; color:#e8e8f0;
        font-family:'Inter',sans-serif; font-size:14px; outline:none; }
input:focus { border-color:#60a5fa; }
button { width:100%; padding:12px; border-radius:8px; border:1px solid #60a5fa;
         background:rgba(96,165,250,0.12); color:#60a5fa; font-family:'Inter',sans-serif;
         font-size:14px; font-weight:600; cursor:pointer; transition:.15s; }
button:hover { background:rgba(96,165,250,0.2); }
.err { color:#f87171; font-size:13px; text-align:center; margin-top:12px; display:none; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">EQ2</div>
  <h1>EQ2Emu Admin</h1>
  <div class="sub">Enter the dashboard password to continue</div>
  <form id="login-form" onsubmit="login(); return false;" autocomplete="off">
    <input type="text" name="username" value="admin" autocomplete="username"
           style="display:none" tabindex="-1" aria-hidden="true">
    <label>Password</label>
    <input type="password" id="pw" name="password" autocomplete="current-password" autofocus>
    <button type="submit">Sign In</button>
  </form>
  <div class="err" id="err">Wrong password</div>
</div>
<script>
async function login() {
  const pw = document.getElementById('pw').value;
  const r = await fetch('/api/login', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({password: pw})
  });
  if (r.ok) { window.location.href = '/'; }
  else { document.getElementById('err').style.display = 'block'; }
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8890)
