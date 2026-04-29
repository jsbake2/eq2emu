# EQ2Emu client bundle (CachyOS)

A self-contained installer package for handing the EverQuest II client to
another CachyOS / Arch user. The friend untars one file, runs `install.sh`,
and lands at a working `eq2emu` launcher that points at our server.

## Where things live

Everything is under `~/eq2emu/` (host paths):

| path                                   | role                                                      |
|----------------------------------------|-----------------------------------------------------------|
| `eq2-game/`                            | working installed client (source for the inner tarball)   |
| `wineprefix/`                          | our wine prefix — *not bundled*, recipient builds fresh   |
| `install-package/install.sh`           | bash installer that runs on the recipient's box           |
| `install-package/README.md`            | recipient-facing usage / troubleshooting                  |
| `install-package/eq2-game.tar.zst`     | compressed game payload (~3.0 GB)                         |
| `install-package/SHA256SUMS`           | checksums for the three pieces above                      |
| `eq2emu-cachyos-bundle.tar`            | outer single-file bundle (what you actually send)         |
| `README.md`                            | copy of the recipient README, exposed outside the tarball |

## What's in the inner payload

`eq2-game.tar.zst` is a zstd-compressed tar of `eq2-game/` with personal
files **excluded** so each recipient starts fresh:

- `homelab_*_uisettings.ini` — per-character UI state
- `jbaker*_characters.ini` — char list
- `eq2_recent.ini` — last-session resolution / username / etc.
- `alertlog.txt`
- `cache/*` — wine regenerates this
- `ui.log`
- `launch.sh` — the installer writes a fresh one with the recipient's paths

Everything else (binaries, paks, the AMD-fix `d3d9.dll`, the bundled
`mss32.dll`, default UI, etc.) ships as-is.

## Build commands

These run in `/home/jbaker/eq2emu/`. zstd-3 is the right compression level
here — pak files are already compressed, so higher levels just burn CPU
for ~no shrink.

### Rebuild only the inner game payload (when the client itself changes)

```sh
cd /home/jbaker/eq2emu
tar \
  --exclude='eq2-game/homelab_*_uisettings.ini' \
  --exclude='eq2-game/jbaker*_characters.ini' \
  --exclude='eq2-game/eq2_recent.ini' \
  --exclude='eq2-game/alertlog.txt' \
  --exclude='eq2-game/cache/*' \
  --exclude='eq2-game/ui.log' \
  --exclude='eq2-game/launch.sh' \
  -I 'zstd -T0 -3' \
  -cf install-package/eq2-game.tar.zst eq2-game
```

Takes ~2 min on the homelab box.

### Rebuild only `install.sh` / `README.md` (config tweaks)

The payload doesn't change. Edit the files in `install-package/`, then
just rebundle the outer tarball + checksums.

### Rebuild the outer bundle + checksums (always do this after either step above)

```sh
cd /home/jbaker/eq2emu
tar -cf eq2emu-cachyos-bundle.tar -C /home/jbaker/eq2emu \
  install-package/install.sh \
  install-package/README.md \
  install-package/eq2-game.tar.zst
cp install-package/README.md README.md
sha256sum \
  eq2emu-cachyos-bundle.tar \
  install-package/eq2-game.tar.zst \
  install-package/install.sh \
  install-package/README.md \
  > install-package/SHA256SUMS
```

## What the installer does on the recipient

`install.sh` is the only contract with the friend. In order:

1. Sanity checks: not running as root, `pacman` exists, payload present.
2. Verifies `[multilib]` is enabled (EQ2 is a 32-bit i386 PE).
3. `sudo pacman -S --needed wine wine-mono wine-gecko winetricks` (skippable with `--no-deps`).
4. Extracts the payload to `~/eq2emu/eq2-game/` (overridable via `INSTALL_DIR`).
5. `wineboot -i` with `WINEARCH=win32` against `~/eq2emu/wineprefix/`.
6. Prompts for the EQ2Emu **login server address** (or reads `SERVER_ADDR`),
   writes/updates `cl_ls_address` in `eq2_default.ini`.
7. Writes `~/eq2emu/eq2-game/launch.sh` with the recipient's paths.
   Currently uses `wine explorer /desktop=eq2,2400x1300` — bump this in
   `install.sh` when our default resolution changes.
8. Symlinks `~/.local/bin/eq2emu` → `launch.sh`.
9. Drops a `.desktop` entry at `~/.local/share/applications/eq2emu.desktop`
   (skippable with `--no-desktop`).

Non-interactive vars / flags: `INSTALL_DIR`, `SERVER_ADDR`,
`PAYLOAD` (override payload path), `--no-deps`, `--no-desktop`.

## Things to keep in sync when our setup changes

- **Wine virtual desktop size**: `eq2-game/launch.sh` (ours) and the
  here-doc inside `install-package/install.sh` (recipient's). README
  also names this size — update all three.
- **In-game resolution**: `eq2-game/eq2_default.ini` has
  `cl_screenwidth` / `cl_screenheight`. If you bump these to match a
  bigger desktop size, the inner payload has to be rebuilt.
- **Login server address**: hard-coded `127.0.0.1` in our copy of
  `eq2_default.ini`; the installer rewrites it from the prompt /
  `SERVER_ADDR`. When we go public, change the *default* in `install.sh`
  (the prompt's "leave blank to keep current value" line) so the friend
  doesn't have to type our hostname.
- **DLLs in `eq2-game/`**: the AMD-fix `d3d9.dll` is loaded via
  `WINEDLLOVERRIDES=d3d9=n,b` in the launcher. If we ever swap to DXVK
  or stock wine d3d9, update both the launcher template and the
  README's "Known issues" section.
- **Server-side patches**: anything that requires a matching client
  (currently nothing — the keymap fix is server-only) would land here.
  If we ever ship a custom DLL or replace `EQ2Module.dll`, add a step
  to install it into the prefix and document it in the README.

## Recipient's recovery / uninstall

The README documents both. Uninstall is `rm -rf ~/eq2emu/eq2-game
~/eq2emu/wineprefix` plus removing the symlink and `.desktop` entry.
Reinstall is just rerunning `install.sh` over the top (it prompts
before overwriting `eq2-game/`, leaves an existing prefix alone).

## Rough sizes

- Inner `eq2-game.tar.zst`: 3.0 GB (extracts to ~3.2 GB)
- Wine prefix on recipient after `wineboot`: ~700 MB
- Outer bundle: ~3.0 GB (compression nearly nil over the inner tar
  since it's already compressed)
