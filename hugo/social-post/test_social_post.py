#!/usr/bin/env python3
"""Tests for social_post.py. Run: python3 test_social_post.py"""

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import os  # noqa: E402
os.environ.setdefault("SITE_URL", "https://example.com")
os.environ.setdefault("DEFAULT_UTC_OFFSET", "-5")
import social_post as sp  # noqa: E402

NOW = dt.datetime(2026, 11, 24, 14, 0, tzinfo=dt.timezone.utc)  # 9 AM EST
URL = "https://example.com/posts/2026/11/slug/"

PROMO = f'''
[promo]
bluesky = """Teaser.

{URL}"""
linkedin = """Hook.

Body (with #Tags) and a_b.

#Git #macOS"""
'''


def write_post(root: Path, date: str, draft=False, promo=PROMO, slug="slug") -> Path:
    d = root / "posts" / "2026" / "11" / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.md"
    p.write_text(f'+++\ntitle = "T"\ndate = {date}\ndraft = {"true" if draft else "false"}\n{promo}+++\n\nBody\n')
    return p


class FindDue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def due(self):
        return [p["url"] for p in sp.find_due(self.root, NOW)]

    def test_live_post_with_promo_is_due(self):
        write_post(self.root, '"2026-11-24T08:00:00-05:00"')
        self.assertEqual(self.due(), [URL])

    def test_bare_date_is_due(self):
        write_post(self.root, "2026-11-24")
        self.assertEqual(self.due(), [URL])

    def test_future_post_is_not_due(self):
        write_post(self.root, '"2026-11-24T10:00:00-05:00"')
        self.assertEqual(self.due(), [])

    def test_draft_is_not_due(self):
        write_post(self.root, '"2026-11-24T08:00:00-05:00"', draft=True)
        self.assertEqual(self.due(), [])

    def test_old_post_is_not_due(self):
        write_post(self.root, '"2026-11-20T08:00:00-05:00"')
        self.assertEqual(self.due(), [])

    def test_post_without_promo_is_ignored(self):
        write_post(self.root, '"2026-11-24T08:00:00-05:00"', promo="")
        self.assertEqual(self.due(), [])


class Validate(unittest.TestCase):
    def test_good_promo(self):
        self.assertEqual(sp.validate({"bluesky": f"x\n\n{URL}", "linkedin": "y"}, URL), [])

    def test_bluesky_too_long(self):
        errs = sp.validate({"bluesky": "x" * 300 + URL}, URL)
        self.assertTrue(any("limit 300" in e for e in errs))

    def test_bluesky_needs_url(self):
        self.assertTrue(sp.validate({"bluesky": "no link"}, URL))

    def test_linkedin_body_link_rejected(self):
        self.assertTrue(sp.validate({"linkedin": f"see {URL}"}, URL))

    def test_first_comment_mention_rejected(self):
        self.assertTrue(sp.validate({"linkedin": "Link in the first comment."}, URL))

    def test_linkedin_comment_key_rejected(self):
        self.assertTrue(sp.validate({"linkedin_comment": f"Read it: {URL}"}, URL))

    def test_unknown_key_rejected(self):
        self.assertTrue(sp.validate({"blusky": "typo"}, URL))

    def test_grapheme_count_ignores_combining_and_zwj(self):
        self.assertEqual(sp.graphemes("é"), 1)
        self.assertEqual(sp.graphemes("\U0001F469‍\U0001F4BB"), 1)


class Facets(unittest.TestCase):
    def test_byte_offsets_after_multibyte_text(self):
        text = f"café — {URL}"
        (f,) = sp.link_facets(text)
        b = text.encode()
        self.assertEqual(b[f["index"]["byteStart"]:f["index"]["byteEnd"]].decode(), URL)
        self.assertEqual(f["features"][0]["uri"], URL)

    def test_trailing_punctuation_not_in_link(self):
        (f,) = sp.link_facets(f"see {URL}.")
        self.assertEqual(f["features"][0]["uri"], URL)


class LittleText(unittest.TestCase):
    def test_hashtags_become_templates(self):
        self.assertEqual(sp.little_text("#Git #macOS"), "{hashtag|\\#|Git} {hashtag|\\#|macOS}")

    def test_reserved_characters_escaped(self):
        self.assertEqual(sp.little_text("a_b (c) @d"), "a\\_b \\(c\\) \\@d")

    def test_mid_word_hash_is_escaped_not_tagged(self):
        self.assertEqual(sp.little_text("C#"), "C\\#")


class PostLinkedIn(unittest.TestCase):
    def test_article_card_with_uploaded_thumbnail(self):
        calls = []

        def fake(method, url, *, headers=None, body=None, raw=False):
            calls.append((method, url, body))
            if url == URL:
                return 200, {}, b'<meta property="og:title" content="T"><meta property="og:description" content="D"><meta property="og:image" content="/c.png">'
            if url.endswith("/c.png"):
                return 200, {}, b"png"
            if "initializeUpload" in url:
                return 200, {}, {"value": {"uploadUrl": "https://up.example/x", "image": "urn:li:image:1"}}
            if url == "https://up.example/x":
                return 201, {}, {}
            return 201, {"x-restli-id": "urn:li:share:9"}, {}

        orig, sp.request = sp.request, fake
        try:
            link = sp.post_linkedin("Hook #Tag", URL, "t", "urn:li:person:x")
        finally:
            sp.request = orig
        self.assertEqual(link, "https://www.linkedin.com/feed/update/urn:li:share:9/")
        post = [b for m, u, b in calls if u.endswith("/rest/posts")][0]
        self.assertEqual(post["content"]["article"],
                         {"source": URL, "title": "T", "description": "D", "thumbnail": "urn:li:image:1"})
        self.assertEqual(post["commentary"], "Hook {hashtag|\\#|Tag}")
        self.assertFalse(any("socialActions" in u for _, u, _ in calls))


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.content = self.root / "content"
        self.ledger = self.root / "ledger.json"
        write_post(self.content, '"2026-11-24T08:00:00-05:00"')
        self.env = {"BLUESKY_HANDLE": "h", "BLUESKY_APP_PASSWORD": "p",
                    "LINKEDIN_ACCESS_TOKEN": "t", "LINKEDIN_PERSON_URN": "urn:li:person:x"}
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def bluesky(self, text, url, handle, pw):
        self.calls.append(("bluesky", text))
        return "https://bsky.app/profile/h/post/1"

    def linkedin(self, text, url, token, person):
        self.calls.append(("linkedin", text))
        return "https://www.linkedin.com/feed/update/urn:li:share:1/"

    def go(self, **kw):
        args = dict(env=self.env, bluesky=self.bluesky, linkedin=self.linkedin, live=lambda u: True)
        args.update(kw)
        return sp.run(self.content, self.ledger, False, NOW, **args)

    def test_posts_both_and_records(self):
        self.assertEqual(self.go(), 0)
        self.assertEqual([c[0] for c in self.calls], ["bluesky", "linkedin"])
        self.assertEqual(set(json.loads(self.ledger.read_text())[URL]), {"bluesky", "linkedin"})

    def test_second_run_posts_nothing(self):
        self.go()
        self.calls.clear()
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.calls, [])

    def test_failed_channel_retried_other_not_reposted(self):
        def boom(*a):
            raise RuntimeError("down")
        self.assertEqual(self.go(linkedin=boom), 1)
        self.assertEqual(list(json.loads(self.ledger.read_text())[URL]), ["bluesky"])
        self.calls.clear()
        self.assertEqual(self.go(), 0)
        self.assertEqual([c[0] for c in self.calls], ["linkedin"])

    def test_not_live_posts_nothing(self):
        self.assertEqual(self.go(live=lambda u: False), 1)
        self.assertEqual(self.calls, [])

    def test_missing_credentials_skip_channel(self):
        self.assertEqual(self.go(env={"BLUESKY_HANDLE": "h", "BLUESKY_APP_PASSWORD": "p"}), 0)
        self.assertEqual([c[0] for c in self.calls], ["bluesky"])
        self.assertNotIn("linkedin", json.loads(self.ledger.read_text())[URL])

    def test_dry_run_posts_and_writes_nothing(self):
        self.assertEqual(sp.run(self.content, self.ledger, True, NOW, env=self.env,
                                bluesky=self.bluesky, linkedin=self.linkedin, live=lambda u: True), 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
