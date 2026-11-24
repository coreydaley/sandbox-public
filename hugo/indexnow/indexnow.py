#!/usr/bin/env python3
"""Submit new and changed pages to IndexNow after a static-site deploy.

Hashes the content of every URL in <public>/sitemap.xml, compares it with the
manifest from the previous deploy, and POSTs the URLs that are new or changed
to api.indexnow.org (shared with Bing, Yandex and others). The manifest is
written only after a successful submit, so a failed run retries next deploy.
With no manifest, every page is submitted once.

Only what a search engine would treat as the page counts: the title, the meta
description, the canonical link and <main>, minus <aside>, <section> and <nav>
blocks marked data-pagefind-ignore (sidebars, related-post lists, older/newer
links). Those change across a site whenever one post goes live, and hashing
them would resubmit pages whose content didn't change. Adjust SITE_CHROME for
your own templates.

Configuration (environment):
  INDEXNOW_HOST  your site's host, e.g. example.com
  INDEXNOW_KEY   your IndexNow key; the site must serve it at /<key>.txt

Usage: indexnow.py <public dir> <manifest file> [--dry-run]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000  # IndexNow's per-request limit
VERSION = 2

HEAD_PARTS = re.compile(
    r'<title>.*?</title>|<meta name="description"[^>]*>|<link rel="canonical"[^>]*>', re.S)
MAIN = re.compile(r"<main\b.*?</main>", re.S)
SITE_CHROME = re.compile(r"<(aside|section|nav)\b[^>]*data-pagefind-ignore[^>]*>.*?</\1>", re.S)


def content(html: str) -> str:
    main = MAIN.search(html)
    if not main:
        return html
    return "".join(HEAD_PARTS.findall(html)) + SITE_CHROME.sub("", main.group(0))


def page_hashes(public: Path) -> dict[str, str]:
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(public / "sitemap.xml").getroot()
    hashes = {}
    for loc in root.iterfind("s:url/s:loc", ns):
        url = loc.text.strip()
        path = urlparse(url).path.lstrip("/")
        html = public / path / "index.html" if not path or path.endswith("/") else public / path
        if html.is_file():
            data = html.read_bytes()
            if html.suffix == ".html":
                data = content(data.decode("utf-8", "replace")).encode()
            hashes[url] = hashlib.sha256(data).hexdigest()
    return hashes


def submit(urls: list[str], host: str, key: str) -> None:
    for i in range(0, len(urls), BATCH):
        body = json.dumps({
            "host": host,
            "key": key,
            "keyLocation": f"https://{host}/{key}.txt",
            "urlList": urls[i:i + BATCH],
        }).encode()
        req = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"IndexNow: HTTP {resp.status} for {len(urls[i:i + BATCH])} URLs")


def changed_pages(current: dict[str, str], manifest: Path) -> list[str]:
    saved = json.loads(manifest.read_text()) if manifest.is_file() else {}
    previous = saved.get("pages", {}) if saved.get("version") == VERSION else {}
    return sorted(u for u, h in current.items() if previous.get(u) != h)


def run(public: Path, manifest: Path, dry_run: bool, host: str, key: str,
        send: Callable[[list[str], str, str], None] = submit) -> int:
    current = page_hashes(public)
    changed = changed_pages(current, manifest)

    print(f"{len(current)} pages in sitemap, {len(changed)} new or changed")
    for url in changed[:50]:
        print(f"  {url}")
    if len(changed) > 50:
        print(f"  … and {len(changed) - 50} more")

    if dry_run:
        return 0
    if changed:
        send(changed, host, key)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"version": VERSION, "pages": current}, indent=0, sort_keys=True))
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    host, key = os.environ.get("INDEXNOW_HOST"), os.environ.get("INDEXNOW_KEY")
    if len(args) != 2 or not (dry_run or (host and key)):
        print(__doc__, file=sys.stderr)
        return 2
    return run(Path(args[0]), Path(args[1]), dry_run, host or "", key or "")


if __name__ == "__main__":
    sys.exit(main())
