# Server patches

Local C++ modifications to the upstream EQ2EMu WorldServer/LoginServer source.

## Base

Patches are generated against the upstream repo at:

- URL: `https://github.com/emagi/eq2emu.git`
- Expected base commit: `6651d51071c05093933360ceaee7b99335fe3b2b` (set in `UPSTREAM_BASE`)

The base is a guideline — patches apply with `git apply --3way`, so drift is tolerated until a hunk conflicts.

## Layout

```
server-patches/
├── README.md
├── UPSTREAM_BASE                       # commit SHA the patches were cut against
└── 0001-<short-name>.patch             # ordered patch files, applied in lexical order
```

Paths inside each patch are relative to the upstream repo root (`source/WorldServer/...`).

## Applying

From the host:

```bash
scripts/apply-server-patches.sh
```

This copies the patch set into the running server container, runs `git apply --3way` against
`/eq2emu/eq2emu/source`, and reports which patches were applied / already-applied / conflicted.
Idempotent — safe to re-run.

After patches apply, rebuild:

```bash
docker exec docker-eq2emu-server-1 /eq2emu/compile_source.sh
```

Then hot-swap the binary and let Dawn auto-restart eq2world — see `docs/server-builds.md`.

## Regenerating

If you edit source inside the container, regenerate the patch from the upstream diff:

```bash
docker exec docker-eq2emu-server-1 \
  sh -c 'cd /eq2emu/eq2emu/source && git diff -- <paths>' \
  > server-patches/NNNN-<name>.patch
```

## Current patches

- `0001-default-spell-grant-tier.patch` — adds `R_Spells/DefaultSpellGrantTier` rule (default 4 = Expert)
  and uses it in `Client::AddSendNewSpells` so level-up spell awards grant the higher tier when
  available, falling back to tier 1.
