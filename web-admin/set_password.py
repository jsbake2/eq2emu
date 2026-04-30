#!/usr/bin/env python3
"""Bootstrap secrets.json for the EQ2Emu admin dashboard.

Stores a scrypt hash of the dashboard password. The cleartext password
is never written to disk.

Usage:
    .venv/bin/python set_password.py            # prompts for password
    .venv/bin/python set_password.py --pw eq2123
"""

import argparse
import getpass
import hashlib
import json
import secrets
from pathlib import Path

SECRETS_PATH = Path(__file__).parent / "secrets.json"


def scrypt_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    h = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt$1${n}${r}${p}${salt.hex()}${h.hex()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pw", help="password (prompts if omitted)")
    args = ap.parse_args()
    pw = args.pw or getpass.getpass("Dashboard password: ")
    if not pw:
        raise SystemExit("Empty password rejected.")
    SECRETS_PATH.write_text(json.dumps({"dashboard_password_hash": scrypt_hash(pw)}, indent=2))
    SECRETS_PATH.chmod(0o600)
    print(f"Wrote {SECRETS_PATH}")


if __name__ == "__main__":
    main()
