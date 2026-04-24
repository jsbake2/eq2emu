# Git Workflow

This document is the operating manual for changes in this repository. It
expands on the rules in [`CLAUDE.md`](../CLAUDE.md) and captures the
branch protection that is configured on GitHub for `main`.

## Branching model

| Branch prefix | Purpose | Example |
| --- | --- | --- |
| `main` | Always deployable. Only updated via merged PRs. | — |
| `feature/<name>` | New functionality | `feature/gm-boost-command` |
| `fix/<name>` | Bug fixes | `fix/lua-spawn-crash` |
| `infra/<name>` | Docker, backup, deployment, CI | `infra/mariadb-backups` |
| `content/<name>` | SQL content edits, Lua spawn/quest additions | `content/qeynos-merchants` |
| `docs/<name>` | Documentation-only changes | `docs/git-workflow` |

Keep names short and kebab-case. The prefix is the signal — it tells
reviewers what kind of review is needed (infra vs. gameplay vs. docs).

## Per-task workflow

1. `git status && git branch --show-current` — know where you are.
2. If on `main`, create a new branch. **Never commit on `main` directly.**
   The only exception was the repo's very first commit, which bootstrapped
   `CLAUDE.md`, `PROJECT.md`, and `.gitignore`.
3. Commit as work progresses. Each commit should be coherent on its own
   (see commit style below).
4. Push the branch: `git push -u origin <branch>`.
5. Open a PR (`gh pr create`) when the milestone is complete. The PR
   description must cover: what changed, why, how to test, rollback
   steps, and any linked issues or migration numbers.
6. The operator reviews and merges. Claude Code never self-merges.

## Commit style

- Conventional-commit-ish prefixes: `feat:`, `fix:`, `infra:`,
  `content:`, `docs:`, `chore:`.
- Subject under 72 characters, imperative mood
  ("feat: add /boost GM command", not "added boost command").
- Body explains *why*, not *what* — the diff shows what.
- Reference SQL migration numbers or issue IDs where relevant.

## What counts as a PR-worthy milestone

- A complete phase item from [`PROJECT.md`](../PROJECT.md)
- A self-contained feature (one command, one spawn script, one content pack)
- A bugfix with its test case or reproduction notes
- An infra change that can be deployed independently
- A documentation set that covers a discrete topic

Do **not** open a PR for: work-in-progress that doesn't run, bundles of
unrelated changes (split them), or changes that require undocumented
manual steps.

## Branch protection on `main`

The `main` branch is protected on GitHub with the following rules:

- **Require a pull request before merging.** No direct pushes to `main`.
- **Require at least 1 approving review** on the PR before merge.
- **Dismiss stale approvals** when new commits are pushed to the PR
  branch, so approvals always reflect the latest code.
- **Require conversation resolution** — open review threads block merge.
- **Block force pushes.** History on `main` is immutable.
- **Block branch deletion.** `main` cannot be deleted via the API or UI.
- **Rules apply to administrators.** The repo owner is not exempt; this
  prevents accidental force-pushes or direct commits from a local shell.

### Applying / verifying the rules

Branch protection is configured via the GitHub API. To inspect the
current rules:

```bash
gh api repos/jsbake2/eq2emu/branches/main/protection | jq
```

To reapply (idempotent) after an accidental change, use the script
checked in at `scripts/apply_branch_protection.sh` (added in a later
phase) or re-run the API call from the PR that introduced this doc.

If a rule needs to change, do it via a PR that updates this document
**and** applies the new protection — the repo state and the doc should
never drift.

## Safety rules (non-negotiable)

- Never force-push to `main`.
- Never rewrite history on a branch with an open PR.
- Never delete a branch without confirming the PR is merged or abandoned.
- Never skip hooks (`--no-verify`) or bypass signing without explicit
  operator approval.
- Never commit secrets. `.gitignore` covers `.env`, backups, DB dumps,
  logs, TLS keys, and tunnel credentials; if something feels sensitive
  and isn't covered, add the pattern before committing.

## Recovering from mistakes

- **Committed to `main` locally by accident (not yet pushed):**
  `git reset --soft HEAD~1` and start over on a feature branch. The
  branch protection on GitHub will reject the push regardless.
- **Pushed to the wrong branch:** open a PR from that branch instead,
  don't try to move the commit.
- **Accidentally merged a broken PR:** revert via a new PR
  (`git revert <merge-sha>`), don't force-push `main`.
- **Secrets committed:** rotate the secret first. Then remove from
  history via a follow-up PR; assume the secret is already compromised.
