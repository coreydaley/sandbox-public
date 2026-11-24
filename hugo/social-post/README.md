# hugo-social-post

Share each new Hugo blog post to Bluesky and LinkedIn once it's live, using
text you approved when you wrote it. A GitHub Action runs after your deploy,
posts through each network's API, and records what it sent so it doesn't post
twice.

Write-up: [My blog posts now share themselves to Bluesky and LinkedIn](https://coreydaley.dev/posts/2026/11/share-blog-posts-bluesky-linkedin-github-actions/)

| File | What it is |
|---|---|
| `social_post.py` | Finds due posts, validates the text, posts, updates the ledger. Python 3.11+, standard library only. |
| `test_social_post.py` | 23 unit tests. No network. `python3 test_social_post.py` |
| `linkedin_auth.py` | Run on your machine every ~60 days to get a LinkedIn token and store it as a repo secret. |
| `.github/workflows/social-post.yml` | The workflow. |

## How it works

A post opts in with a `[promo]` table at the end of its TOML front matter.
Adding it is the approval; the text is posted verbatim.

```toml
[promo]
bluesky = """A teaser under 300 characters.

https://example.com/posts/2026/11/some-post/"""
linkedin = """Hook line.

A few short paragraphs, no links. Link in the first comment.

#Hugo #Automation"""
linkedin_comment = "What's at the link: https://example.com/posts/2026/11/some-post/"
```

A post is shared only when it isn't a draft, its date has passed, it was
dated in the last 3 days, and its URL returns 200. Each channel is recorded in
`.github/social-posted.json` right after it posts, and the workflow commits
that file back, so re-runs skip what already went out.

It assumes posts are leaf bundles at `content/posts/**/index.md` and that a
bundle's path under `content/` is its URL path. Change `find_due` and
`post_url` if your site differs.

## Setup

1. Copy `social_post.py` (and the tests) to `scripts/` in your site repo, and
   the workflow to `.github/workflows/`. Set `workflows:` in the workflow to
   your deploy workflow's `name:`.
2. Repository variables: `SITE_URL` (e.g. `https://example.com`), and
   `DEFAULT_UTC_OFFSET` in hours if your front matter dates have no time zone.
3. **Bluesky:** create an app password (Settings → Privacy and security → App
   passwords). Set secret `BLUESKY_APP_PASSWORD` and variable `BLUESKY_HANDLE`.
4. **LinkedIn:** create an app at linkedin.com/developers (it must be linked
   to a company page). Add the products "Share on LinkedIn" and "Sign In with
   LinkedIn using OpenID Connect", and the redirect URL
   `http://localhost:8765/callback`. Then, in your site checkout:

   ```bash
   LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=... python3 linkedin_auth.py
   ```

   It sets secret `LINKEDIN_ACCESS_TOKEN` and variables `LINKEDIN_PERSON_URN`
   and `LINKEDIN_TOKEN_EXPIRES`. Tokens last 60 days; the workflow logs a
   warning in the last week.
5. Run the workflow by hand from the Actions tab. It defaults to a dry run.

A channel without credentials is skipped, so you can start with one.

## Caveats

- The LinkedIn API version (`LINKEDIN_VERSION`, default `202608`) is a
  monthly version that LinkedIn retires after about a year. Override it with
  an environment variable when it does.
- No images on LinkedIn yet; posts get the link in the first comment.
- The Bluesky link card uses the page's `og:image`.
- A re-run can post twice if LinkedIn accepts a post but returns no id, or if
  the ledger commit fails after a post. A failed first comment isn't retried.
