# sandbox-public

Public repo of standalone examples (scripts, GitHub Actions, small tools) that
Corey built for his own projects and usually wrote about on coreydaley.dev.
People copy them; nobody installs this repo. **It is public**: everything
committed here, including history, is visible to anyone.

Experiments and unfinished work stay private until they're worth sharing.
Claude Code config belongs in `agent-config`, not here.

## Layout

```
<area>/<example>/        one self-contained example per folder
tools/                   this repo's own tooling (hooks); not examples
.github/workflows/ci.yml CI for this repo: every example's tests + gitleaks
```

- **`<area>`** is the platform or tool the example plugs into, the thing a
  reader would search for: `hugo/`, `github/`, `macos/`, `shell/`,
  `apple-dev/`, `python/`. Create an area when its first example arrives; don't
  pre-create empty ones. If an example fits two, pick the one the reader
  starts from (a GitHub Action for a Hugo site goes in `hugo/`).
- **`<example>`** is a short kebab-case name without the area repeated
  (`hugo/social-post`, not `hugo/hugo-social-post`).
- Examples don't import from each other or from a shared lib. Copying one
  folder must be enough to use it.
- An example's own GitHub workflow lives in `<example>/.github/workflows/`
  so GitHub never runs it here; the README says where to copy it.

## What every example has

1. **`README.md`** with: one-paragraph summary, link to the write-up (if
   any), a file table, how it works, setup steps, and a **Caveats** section
   saying what's untested or known to break. Name what it was tested on
   (OS, tool versions) when that matters.
2. **Tests** as `test_*.py` (or a `test.sh`) next to the code, runnable from
   the example's folder with no network and no credentials. `make test`
   finds and runs every `test_*.py`; add other runners to the Makefile.
3. **Configuration through environment variables or arguments**, never
   hard-coded accounts, domains, repo names or paths. Use `example.com` and
   placeholders in docs.
4. A row in the root `README.md` table.

## Rules

- **No personal or private information.** No secrets, tokens, member IDs,
  account IDs, hostnames, home paths, private repo names, or details of
  unpublished/embargoed work. The pre-commit and pre-push hooks
  (`make hooks`) run gitleaks and `tools/check-personal-info.py` (generic
  patterns plus Corey's private denylist outside the repo); CI runs gitleaks
  on the whole history. A hook failure is a stop, not something to bypass.
- **Prefer the standard library.** Python 3.11+, stdlib only, unless a
  dependency is the point of the example. If one is needed, pin it and say
  so in the README.
- **Pin GitHub Actions by commit SHA** with the version in a comment, and
  give workflows the least `permissions` they need.
- **Copied from a private repo?** Strip it to the generic version: replace
  site URLs, repo names and workflow names with settings, and rerun the
  tests here. The private repo stays the one that runs in production; note
  in the README if the two may drift.
- **Honest docs.** Same standard as the blog: say what was tested and what
  wasn't; no claims the code doesn't back up.
- License is MIT for the whole repo (`LICENSE`); examples don't carry their
  own unless they include third-party code.

## Commits

Conventional Commits with the example as scope
(`feat(hugo/social-post): …`, `docs(hugo/social-post): …`, `chore(tools): …`)
and a `Co-Authored-By:` trailer. Never commit or push without an explicit
instruction.

## Commands

```bash
make hooks   # install pre-commit / pre-push hooks (needs gitleaks)
make test    # run every example's tests
```
