#!/usr/bin/env python3
"""Post approved social text for blog posts once they're live.

A post opts in with a `[promo]` table at the end of its TOML front matter.
The text in it is the approved, final text; this script posts it verbatim.

    [promo]
    bluesky = \"\"\"Teaser text.

    https://example.com/posts/2026/11/slug/\"\"\"
    linkedin = \"\"\"Hook line.

    Body. Link in the first comment.

    #Tag #Tag\"\"\"
    linkedin_comment = "What's at the link: https://example.com/posts/2026/11/slug/"

A post is due when it is not a draft, its date has passed, it was dated within
the last MAX_AGE_DAYS days, and its URL returns 200. Each channel is posted at
most once per URL: successes are recorded in the ledger file straight away, so
a re-run (or a failure on the other channel) never posts twice.

SITE_URL (e.g. https://example.com) builds each post's URL from its bundle path.
Credentials come from the environment; a channel without them is skipped:
  BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
  LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN (urn:li:person:...)

Usage: social_post.py [--dry-run] [--content content] [--ledger .github/social-posted.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import html.parser
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = (os.environ.get("SITE_URL") or "https://example.com").rstrip("/")
DEFAULT_UTC_OFFSET = float(os.environ.get("DEFAULT_UTC_OFFSET") or "0")  # hours, for dates without a zone
MAX_AGE_DAYS = 3
BLUESKY_LIMIT = 300
LINKEDIN_LIMIT = 3000
LINKEDIN_VERSION = os.environ.get("LINKEDIN_VERSION", "202608")
USER_AGENT = "hugo-social-post/1.0"


# ---------- finding due posts ----------


def read_front_matter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\+\+\+\n(.*?)\n\+\+\+\n", text, re.S)
    if not m:
        return None
    return tomllib.loads(m.group(1))


def post_url(path: Path, content: Path) -> str:
    rel = path.parent.relative_to(content)
    return f"{SITE}/{rel.as_posix()}/"


def parse_date(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        d = value
    elif isinstance(value, dt.date):
        d = dt.datetime(value.year, value.month, value.day)
    else:
        d = dt.datetime.fromisoformat(str(value))
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=DEFAULT_UTC_OFFSET)))
    return d


def find_due(content: Path, now: dt.datetime) -> list[dict]:
    due = []
    for path in sorted(content.glob("posts/**/index.md")):
        fm = read_front_matter(path)
        if not fm or "promo" not in fm or fm.get("draft", False):
            continue
        date = parse_date(fm["date"])
        if date > now or now - date > dt.timedelta(days=MAX_AGE_DAYS):
            continue
        due.append({"path": path, "url": post_url(path, content), "promo": fm["promo"], "title": fm.get("title", "")})
    return due


def validate(promo: dict, url: str) -> list[str]:
    errors = []
    bs = promo.get("bluesky")
    if bs is not None:
        if graphemes(bs) > BLUESKY_LIMIT:
            errors.append(f"bluesky text is {graphemes(bs)} characters (limit {BLUESKY_LIMIT})")
        if url not in bs:
            errors.append("bluesky text must include the post URL")
    li = promo.get("linkedin")
    if li is not None:
        if len(li) > LINKEDIN_LIMIT:
            errors.append(f"linkedin text is {len(li)} characters (limit {LINKEDIN_LIMIT})")
        if "http://" in li or "https://" in li:
            errors.append("linkedin body must not contain a link; put it in linkedin_comment")
    unknown = set(promo) - {"bluesky", "linkedin", "linkedin_comment"}
    if unknown:
        errors.append(f"unknown promo keys: {sorted(unknown)}")
    return errors


def graphemes(s: str) -> int:
    # Close enough for the 300 limit: combining marks and ZWJ joiners don't add a grapheme.
    import unicodedata

    n = 0
    prev_zwj = False
    for ch in s:
        if unicodedata.combining(ch) or ch in "‍️" or prev_zwj:
            prev_zwj = ch == "‍"
            continue
        n += 1
    return n


# ---------- HTTP ----------


def request(method: str, url: str, *, headers=None, body=None, raw=False):
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    data = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read()
            return r.status, dict(r.headers), payload if raw else (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from None


def wait_live(url: str, tries: int = 10, delay: float = 30) -> bool:
    for i in range(tries):
        try:
            status, _, _ = request("GET", url, raw=True)
            if status == 200:
                return True
        except RuntimeError:
            pass
        if i < tries - 1:
            time.sleep(delay)
    return False


class OGParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = dict(attrs)
        key = a.get("property") or a.get("name")
        if key and "content" in a and key not in self.meta:
            self.meta[key] = a["content"]


def page_meta(url: str) -> dict[str, str]:
    _, _, body = request("GET", url, raw=True)
    p = OGParser()
    p.feed(body.decode("utf-8", errors="replace"))
    return p.meta


# ---------- Bluesky ----------


def link_facets(text: str) -> list[dict]:
    facets = []
    for m in re.finditer(r"https?://[^\s]+", text):
        link = m.group(0).rstrip(".,;:!?)")
        start = len(text[: m.start()].encode())
        end = start + len(link.encode())
        facets.append({
            "index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
        })
    return facets


def post_bluesky(text: str, url: str, handle: str, password: str) -> str:
    api = "https://bsky.social/xrpc"
    _, _, session = request("POST", f"{api}/com.atproto.server.createSession",
                            body={"identifier": handle, "password": password})
    auth = {"Authorization": f"Bearer {session['accessJwt']}"}

    meta = page_meta(url)
    external = {
        "uri": url,
        "title": meta.get("og:title", ""),
        "description": meta.get("og:description", ""),
    }
    image = meta.get("og:image")
    if image:
        try:
            _, headers, img = request("GET", urllib.parse.urljoin(url, image), raw=True)
            ctype = headers.get("Content-Type", "image/jpeg").split(";")[0]
            if len(img) < 1_000_000:
                _, _, blob = request("POST", f"{api}/com.atproto.repo.uploadBlob",
                                     headers={**auth, "Content-Type": ctype}, body=img)
                external["thumb"] = blob["blob"]
        except RuntimeError as e:
            print(f"  bluesky: no thumbnail ({e})")

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "langs": ["en"],
        "facets": link_facets(text),
        "embed": {"$type": "app.bsky.embed.external", "external": external},
    }
    _, _, out = request("POST", f"{api}/com.atproto.repo.createRecord", headers=auth,
                        body={"repo": session["did"], "collection": "app.bsky.feed.post", "record": record})
    rkey = out["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


# ---------- LinkedIn ----------

LITTLE_TEXT_RESERVED = set("\\|{}@[]()<>#*_~")


def little_text(text: str) -> str:
    """Escape LinkedIn's "little text" reserved characters; turn #Tags into hashtags."""
    out = []
    i = 0
    while i < len(text):
        m = re.match(r"#(\w+)", text[i:])
        if m and (i == 0 or text[i - 1].isspace()):
            out.append("{hashtag|\\#|" + m.group(1) + "}")
            i += len(m.group(0))
            continue
        ch = text[i]
        out.append("\\" + ch if ch in LITTLE_TEXT_RESERVED else ch)
        i += 1
    return "".join(out)


def post_linkedin(text: str, comment: str | None, token: str, person: str) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    body = {
        "author": person,
        "commentary": little_text(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    _, resp_headers, _ = request("POST", "https://api.linkedin.com/rest/posts", headers=headers, body=body)
    urn = resp_headers.get("x-restli-id") or resp_headers.get("X-RestLi-Id")
    if not urn:
        raise RuntimeError("LinkedIn created the post but returned no id")
    if comment:
        try:
            request("POST", f"https://api.linkedin.com/rest/socialActions/{urllib.parse.quote(urn)}/comments",
                    headers=headers, body={"actor": person, "object": urn, "message": {"text": comment}})
        except RuntimeError as e:
            print(f"::warning::LinkedIn post {urn} is up but the first comment failed: {e}")
    return f"https://www.linkedin.com/feed/update/{urn}/"


# ---------- main ----------


def load_ledger(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def run(content: Path, ledger_path: Path, dry_run: bool, now: dt.datetime, env=os.environ,
        bluesky=post_bluesky, linkedin=post_linkedin, live=wait_live) -> int:
    ledger = load_ledger(ledger_path)
    failures = 0
    for post in find_due(content, now):
        url, promo = post["url"], post["promo"]
        done = ledger.setdefault(url, {})
        todo = [c for c in ("bluesky", "linkedin") if promo.get(c) and c not in done]
        if not todo:
            continue
        errors = validate(promo, url)
        if errors:
            print(f"::error::{post['path']}: " + "; ".join(errors))
            failures += 1
            continue
        print(f"{url}: {', '.join(todo)}")
        if dry_run:
            for c in todo:
                print(f"--- {c} ---\n{promo[c]}")
            if "linkedin" in todo and promo.get("linkedin_comment"):
                print(f"--- linkedin first comment ---\n{promo['linkedin_comment']}")
            continue
        if not live(url):
            print(f"::error::{url} is not returning 200; nothing posted")
            failures += 1
            continue
        for channel in todo:
            try:
                if channel == "bluesky":
                    if not (env.get("BLUESKY_HANDLE") and env.get("BLUESKY_APP_PASSWORD")):
                        print("::notice::Bluesky credentials not set; skipping")
                        continue
                    done["bluesky"] = bluesky(promo["bluesky"], url, env["BLUESKY_HANDLE"], env["BLUESKY_APP_PASSWORD"])
                else:
                    if not (env.get("LINKEDIN_ACCESS_TOKEN") and env.get("LINKEDIN_PERSON_URN")):
                        print("::notice::LinkedIn credentials not set; skipping")
                        continue
                    done["linkedin"] = linkedin(promo["linkedin"], promo.get("linkedin_comment"),
                                                env["LINKEDIN_ACCESS_TOKEN"], env["LINKEDIN_PERSON_URN"])
                print(f"  {channel}: {done[channel]}")
                save_ledger(ledger_path, {k: v for k, v in ledger.items() if v})
            except RuntimeError as e:
                print(f"::error::{channel} failed for {url}: {e}")
                failures += 1
    if not dry_run:
        save_ledger(ledger_path, {k: v for k, v in ledger.items() if v})
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--content", default="content", type=Path)
    ap.add_argument("--ledger", default=".github/social-posted.json", type=Path)
    a = ap.parse_args()
    if not os.environ.get("SITE_URL"):
        ap.error("set SITE_URL, e.g. https://example.com")
    return run(a.content, a.ledger, a.dry_run, dt.datetime.now(dt.timezone.utc))


if __name__ == "__main__":
    sys.exit(main())
