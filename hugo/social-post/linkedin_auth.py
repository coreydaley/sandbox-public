#!/usr/bin/env python3
"""Get a LinkedIn access token for social-post.yml and store it in GitHub.

Run on your Mac every ~60 days (the workflow warns a week before expiry):

    LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=... python3 linkedin_auth.py

Run it inside your site's checkout (or set GITHUB_REPO=owner/repo).

It opens LinkedIn's consent page, catches the redirect on
http://localhost:8765/callback (add that URL to the app's Auth settings),
exchanges the code, looks up your member id, and sets in the repo:
  secret   LINKEDIN_ACCESS_TOKEN
  variable LINKEDIN_PERSON_URN, LINKEDIN_TOKEN_EXPIRES
The token never goes to stdout. Needs the app's "Share on LinkedIn" and
"Sign In with LinkedIn using OpenID Connect" products, and `gh` signed in.
"""

import datetime as dt
import http.server
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "openid profile w_member_social"


def wait_for_code(state: str) -> str:
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                result["error"] = "state mismatch"
            elif "error" in q:
                result["error"] = q.get("error_description", q["error"])[0]
            else:
                result["code"] = q.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab.")

        def log_message(self, *a):
            pass

    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as srv:
        while not result:
            srv.handle_request()
    if "error" in result:
        sys.exit(f"LinkedIn sign-in failed: {result['error']}")
    return result["code"]


def post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gh(*args: str, stdin: str | None = None) -> None:
    repo = ["--repo", os.environ["GITHUB_REPO"]] if os.environ.get("GITHUB_REPO") else []
    subprocess.run(["gh", *args, *repo], input=stdin, text=True, check=True)


def main() -> None:
    cid = os.environ.get("LINKEDIN_CLIENT_ID")
    secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    if not (cid and secret):
        sys.exit("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET (from the LinkedIn developer app).")

    state = secrets.token_urlsafe(24)
    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": REDIRECT, "state": state, "scope": SCOPES,
    })
    print("Opening LinkedIn to approve access…")
    webbrowser.open(url)
    code = wait_for_code(state)

    tok = post_form("https://www.linkedin.com/oauth/v2/accessToken", {
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": cid, "client_secret": secret,
    })
    access = tok["access_token"]
    expires = (dt.date.today() + dt.timedelta(seconds=int(tok.get("expires_in", 0)))).isoformat()

    req = urllib.request.Request("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        sub = json.load(r)["sub"]

    gh("secret", "set", "LINKEDIN_ACCESS_TOKEN", stdin=access)
    gh("variable", "set", "LINKEDIN_PERSON_URN", "--body", f"urn:li:person:{sub}")
    gh("variable", "set", "LINKEDIN_TOKEN_EXPIRES", "--body", expires)
    print(f"Stored. Token expires {expires}.")
    if tok.get("refresh_token"):
        print("LinkedIn also issued a refresh token; this script doesn't use it yet.")


if __name__ == "__main__":
    main()
