# indexnow

Tell Bing and other IndexNow search engines about new and changed pages after
each deploy of a static site, and only those pages.

The script hashes every page in your built `sitemap.xml`, compares the hashes
with the previous deploy's, and submits what's new or changed to
`api.indexnow.org`. It hashes what a search engine cares about (title, meta
description, canonical link and `<main>`), so a sidebar or "related posts"
list that changes on every page whenever one post goes live doesn't make it
resubmit the whole site.

| File | What it is |
|---|---|
| `indexnow.py` | The script. Python 3.10+, standard library only. |
| `test_indexnow.py` | 10 unit tests on a generated site. No network. `python3 test_indexnow.py` |

## How it works

- **What's hashed:** `<title>`, `<meta name="description">`,
  `<link rel="canonical">`, and `<main>` minus any `<aside>`, `<section>` or
  `<nav>` carrying `data-pagefind-ignore`. Pages without `<main>` and non-HTML
  sitemap entries are hashed whole. If your templates mark site-wide blocks
  differently, change `SITE_CHROME`.
- **The manifest** is a JSON file of URL → hash. It's written only after a
  successful submit, so a failed run submits the same pages next time. With no
  manifest, every page is submitted once.
- Submits in batches of 10,000, IndexNow's per-request limit.

## Setup

1. Generate a key (8–128 characters of `a-z`, `A-Z`, `0-9`, `-`), e.g.
   `openssl rand -hex 16`, and serve it as a text file at
   `https://<your host>/<key>.txt` containing just the key. In Hugo, put it in
   `static/<key>.txt`. The key is public by design; it proves you control the
   host.
2. Copy `indexnow.py` into your repo (e.g. `scripts/`).
3. Set `INDEXNOW_HOST` and `INDEXNOW_KEY` as repository variables.
4. Add these steps to your deploy workflow after the deploy itself. The
   Actions cache carries the manifest from one deploy to the next:

   ```yaml
   - name: Restore IndexNow manifest
     uses: actions/cache/restore@5a3ec84eff668545956fd18022155c47e93e2684 # v4.2.3
     with:
       path: .indexnow/manifest.json
       key: indexnow-${{ github.run_id }}
       restore-keys: indexnow-

   - name: Submit new and changed pages to IndexNow
     env:
       INDEXNOW_HOST: ${{ vars.INDEXNOW_HOST }}
       INDEXNOW_KEY: ${{ vars.INDEXNOW_KEY }}
     run: python3 scripts/indexnow.py public .indexnow/manifest.json

   - name: Save IndexNow manifest
     uses: actions/cache/save@5a3ec84eff668545956fd18022155c47e93e2684 # v4.2.3
     with:
       path: .indexnow/manifest.json
       key: indexnow-${{ github.run_id }}
   ```

Preview locally without submitting:

```bash
hugo --minify && INDEXNOW_HOST=example.com python3 scripts/indexnow.py public /tmp/manifest.json --dry-run
```

## Caveats

- Google doesn't use IndexNow. This covers Bing, Yandex, Seznam, Naver and
  the other participants.
- Actions caches expire after 7 days without use. If you deploy less often,
  the next deploy resubmits every page once.
- The tests cover hashing, change detection and the manifest; the real HTTP
  submit is only exercised by real deploys.
- Why bother when Cloudflare has Crawler Hints: in my case it only pinged
  IndexNow for cached files, mostly images, not the HTML pages.
