# Custom server builds

How to apply local C++ changes to the upstream EQ2EMu WorldServer/LoginServer
and ship a rebuilt `eq2world` binary without losing changes across container
recreations.

## Why patches, not a fork

Source lives inside the `docker-eq2emu-server-1` container at
`/eq2emu/eq2emu/source/` — it's a fresh `git clone` of upstream baked into the
image at install time, not a mounted volume. Editing it in place works, but
anything in that directory disappears if the container is rebuilt from the
image. Until we outgrow this setup (e.g. enough custom code to justify a full
fork + submodule), we track changes as patch files in this repo and re-apply
them to the container's source on demand.

Upstream: `https://github.com/emagi/eq2emu.git`.

## Layout

- `server-patches/` — ordered `.patch` files + README + `UPSTREAM_BASE` SHA
- `scripts/apply-server-patches.sh` — idempotent applier that copies patches
  into the container and runs `git apply`

## Making a change

1. Branch off `main` (`feature/<short-name>`).
2. Edit source inside the running container:
   ```bash
   docker exec -it docker-eq2emu-server-1 bash
   cd /eq2emu/eq2emu/source
   # edit files with vim/nano, or use docker cp to swap them in
   ```
3. Test-build:
   ```bash
   docker exec docker-eq2emu-server-1 \
     sh -c 'cd /eq2emu/eq2emu/source/WorldServer && make -j$(nproc)'
   ```
4. Capture the diff as a patch:
   ```bash
   docker exec docker-eq2emu-server-1 \
     sh -c 'cd /eq2emu/eq2emu/source && git diff -- <paths>' \
     > server-patches/NNNN-<short-name>.patch
   ```
   Use the next available 4-digit number. Update
   `server-patches/README.md`'s "Current patches" list.
5. Hot-swap the binary (see below) and smoke-test.
6. Commit the patch + any companion scripts/migrations, push the branch, open
   a PR.

## Hot-swapping the binary

`eq2world` is auto-restarted by the Dawn web admin (`EQ2DAWN_AUTORESTART_SERVER=1`),
so the sequence is:

```bash
# 1) move the running binary out of the way (rename preserves the running inode)
docker exec docker-eq2emu-server-1 \
  sh -c 'cd /eq2emu/eq2emu/server && mv eq2world eq2world.bak && \
         cp /eq2emu/eq2emu/source/WorldServer/eq2world eq2world'

# 2) kill the running process — Dawn will relaunch using the new binary
docker exec docker-eq2emu-server-1 pkill -f './eq2world'

# 3) verify the new process picked up the new path
docker exec docker-eq2emu-server-1 \
  sh -c 'sleep 10 && ls -la /proc/$(pidof eq2world)/exe && \
         tail -20 /eq2emu/eq2emu/server/logs/eq2world.log'
```

Expected: `/proc/<pid>/exe -> /eq2emu/eq2emu/server/eq2world` and the log ends
with `Starting static zones...` plus a `Connected to LoginServer` line. Players
are disconnected for ~10 seconds across the restart.

If the new binary fails to start, roll back:

```bash
docker exec docker-eq2emu-server-1 \
  sh -c 'cd /eq2emu/eq2emu/server && mv eq2world eq2world.bad && \
         mv eq2world.bak eq2world'
docker exec docker-eq2emu-server-1 pkill -f './eq2world'
```

## Re-applying patches to a fresh container

If the container is recreated (e.g. `docker compose down && up` with image
pulled fresh), the source tree is back to upstream HEAD. Run:

```bash
scripts/apply-server-patches.sh
docker exec docker-eq2emu-server-1 /eq2emu/compile_source.sh
# then hot-swap as above
```

The apply script is idempotent — it uses `git apply --reverse --check` to
detect already-applied patches and skips them.

## When a patch conflicts

`git apply --3way` isn't used by the script (yet); a conflicting patch fails
with `[fail]`. To resolve:

1. Enter the container and apply by hand with `git apply --3way`, resolving
   the conflict.
2. Regenerate the patch from the updated diff.
3. Commit the regenerated patch.

If upstream has moved significantly, it's probably time to update
`server-patches/UPSTREAM_BASE` and re-cut all patches against the new base.
