#!/usr/bin/env python3
"""Tests for indexnow.py. Run: python3 test_indexnow.py"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import indexnow as ix  # noqa: E402

SITE = "https://example.com"


def page(title: str, body: str, sidebar: str = "") -> str:
    return (f'<html><head><title>{title}</title><meta name="description" content="d">'
            f'<link rel="canonical" href="x"><script>v=1</script></head><body>'
            f'<header>nav</header><main><article>{body}</article>'
            f'<aside class="s" data-pagefind-ignore>{sidebar}</aside></main>'
            f'<footer>f</footer></body></html>')


class Site:
    def __init__(self, root: Path):
        self.public = root / "public"
        self.public.mkdir()
        self.pages: dict[str, str] = {}

    def put(self, path: str, html: str):
        self.pages[path] = html
        f = self.public / path.lstrip("/") / "index.html" if path.endswith("/") else self.public / path.lstrip("/")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html)
        self._sitemap()

    def _sitemap(self):
        locs = "".join(f"<url><loc>{SITE}{p}</loc></url>" for p in self.pages)
        (self.public / "sitemap.xml").write_text(
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>')


class Content(unittest.TestCase):
    def test_keeps_head_parts_and_main_only(self):
        c = ix.content(page("T", "hello", "tags"))
        self.assertIn("<title>T</title>", c)
        self.assertIn("hello", c)
        for gone in ("<script>", "<header>", "<footer>", "tags"):
            self.assertNotIn(gone, c)

    def test_page_without_main_is_hashed_whole(self):
        self.assertEqual(ix.content("<p>x</p>"), "<p>x</p>")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.site = Site(root)
        self.manifest = root / "cache" / "manifest.json"
        self.sent: list[list[str]] = []
        self.site.put("/", page("Home", "home"))
        self.site.put("/posts/a/", page("A", "a body", "1 post"))

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, urls, host, key):
        self.assertEqual((host, key), ("example.com", "k"))
        self.sent.append(urls)

    def go(self, dry_run=False, send=None):
        return ix.run(self.site.public, self.manifest, dry_run, "example.com", "k", send or self.send)

    def test_first_run_submits_everything_and_saves_manifest(self):
        self.go()
        self.assertEqual(self.sent, [[f"{SITE}/", f"{SITE}/posts/a/"]])
        self.assertEqual(json.loads(self.manifest.read_text())["version"], ix.VERSION)

    def test_unchanged_site_submits_nothing(self):
        self.go()
        self.sent.clear()
        self.go()
        self.assertEqual(self.sent, [])

    def test_sidebar_change_alone_is_not_a_change(self):
        self.go()
        self.sent.clear()
        self.site.put("/posts/a/", page("A", "a body", "2 posts"))
        self.go()
        self.assertEqual(self.sent, [])

    def test_body_change_and_new_page_are_submitted(self):
        self.go()
        self.sent.clear()
        self.site.put("/posts/a/", page("A", "edited"))
        self.site.put("/posts/b/", page("B", "new"))
        self.go()
        self.assertEqual(self.sent, [[f"{SITE}/posts/a/", f"{SITE}/posts/b/"]])

    def test_failed_submit_keeps_old_manifest(self):
        def boom(*a):
            raise OSError("down")
        with self.assertRaises(OSError):
            self.go(send=boom)
        self.assertFalse(self.manifest.exists())

    def test_dry_run_sends_and_writes_nothing(self):
        self.go(dry_run=True)
        self.assertEqual(self.sent, [])
        self.assertFalse(self.manifest.exists())

    def test_unknown_manifest_version_resubmits_everything(self):
        self.manifest.parent.mkdir()
        self.manifest.write_text(json.dumps({f"{SITE}/": "old"}))
        self.go()
        self.assertEqual(len(self.sent[0]), 2)

    def test_non_html_sitemap_entry_hashed_raw(self):
        self.site.put("/feed.xml", "<rss/>")
        self.assertIn(f"{SITE}/feed.xml", ix.page_hashes(self.site.public))


if __name__ == "__main__":
    unittest.main()
