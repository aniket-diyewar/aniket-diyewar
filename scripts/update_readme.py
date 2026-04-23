"""
update_readme.py
----------------
Fetches live data from the GitHub REST API and rewrites
the four auto-update zones in README.md:

    <!-- REPOS-START --> … <!-- REPOS-END -->
    <!-- ACTIVITY-START --> … <!-- ACTIVITY-END -->
    <!-- PROFILE-STATS-START --> … <!-- PROFILE-STATS-END -->

Run manually:
    python scripts/update_readme.py

Or let GitHub Actions call it on a schedule (see .github/workflows/update-readme.yml).
"""

import os
import re
import sys
from datetime import datetime, timezone
from urllib import request, error
import json

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_USERNAME = "aniket-diyewar"
README_PATH     = "README.md"
API_BASE        = "https://api.github.com"

# Repos to always feature (in this order). Others get appended sorted by push date.
PINNED_REPOS = [
    "Medical-Image-Enhancement",
    "Dr_Moddel",
    "ICU-Mortality-LHS",
    "Growth-Tracker",
]

# Emoji map by primary language
LANG_EMOJI = {
    "Python":     "🐍",
    "TypeScript": "💙",
    "JavaScript": "🟨",
    "Jupyter Notebook": "📓",
    "R":          "📊",
    "Shell":      "🐚",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def gh_get(path: str) -> dict | list:
    """Call GitHub REST API. Uses GITHUB_TOKEN if set (higher rate limit)."""
    token = os.environ.get("GITHUB_TOKEN", "")
    url   = f"{API_BASE}{path}"
    req   = request.Request(url, headers={
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           f"readme-updater/{GITHUB_USERNAME}",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    try:
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        print(f"⚠️  GitHub API {exc.code} for {url}: {exc.reason}")
        return {}
    except Exception as exc:
        print(f"⚠️  Network error for {url}: {exc}")
        return {}


def relative_time(iso: str) -> str:
    """Return a human-friendly relative timestamp, e.g. '3 days ago'."""
    if not iso:
        return "—"
    dt    = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    days  = delta.days
    if days == 0:
        hours = delta.seconds // 3600
        return "today" if hours == 0 else f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        return f"{days // 7}w ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def replace_section(content: str, tag: str, new_body: str) -> str:
    """Replace content between <!-- TAG-START --> and <!-- TAG-END --> markers."""
    pattern = rf"(<!-- {tag}-START -->).*?(<!-- {tag}-END -->)"
    replacement = rf"\1\n{new_body}\n\2"
    result, n = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if n == 0:
        print(f"⚠️  Marker <!-- {tag}-START/END --> not found in README – skipping.")
    return result


# ── Section builders ──────────────────────────────────────────────────────────

def build_repos_section() -> str:
    """Fetch all public repos and build a markdown table sorted by pinned order then push date."""
    all_repos: list[dict] = gh_get(f"/users/{GITHUB_USERNAME}/repos?per_page=100&type=public")
    if not all_repos or isinstance(all_repos, dict):
        return "_⚠️ Could not fetch repositories._"

    # Index by name for quick lookup
    by_name = {r["name"]: r for r in all_repos}

    # Build ordered list: pinned first, then the rest sorted by pushed_at desc
    ordered = []
    seen    = set()
    for name in PINNED_REPOS:
        if name in by_name:
            ordered.append(by_name[name])
            seen.add(name)

    rest = sorted(
        [r for r in all_repos if r["name"] not in seen],
        key=lambda r: r.get("pushed_at") or "",
        reverse=True,
    )
    ordered.extend(rest)

    rows = [
        "| Project | Description | Language | ⭐ Stars | 🍴 Forks | Last Push |",
        "|---------|-------------|----------|---------|---------|-----------|",
    ]
    for repo in ordered:
        name      = repo["name"]
        url       = repo["html_url"]
        desc      = (repo.get("description") or "—").replace("|", "\\|")
        lang      = repo.get("language") or "—"
        emoji     = LANG_EMOJI.get(lang, "📁")
        stars     = repo.get("stargazers_count", 0)
        forks     = repo.get("forks_count", 0)
        pushed    = relative_time(repo.get("pushed_at", ""))
        rows.append(
            f"| [{name}]({url}) | {desc} | {emoji} {lang} | ⭐ {stars} | 🍴 {forks} | {pushed} |"
        )

    return "\n".join(rows)


def build_activity_section() -> str:
    """Fetch the 10 most recent public events and format them as a list."""
    events: list[dict] = gh_get(f"/users/{GITHUB_USERNAME}/events/public?per_page=10")
    if not events or isinstance(events, dict):
        return "_⚠️ Could not fetch activity._"

    TYPE_LABELS = {
        "PushEvent":              "🔨 Pushed to",
        "CreateEvent":            "✨ Created",
        "PullRequestEvent":       "🔀 Pull request in",
        "IssuesEvent":            "🐛 Opened issue in",
        "WatchEvent":             "⭐ Starred",
        "ForkEvent":              "🍴 Forked",
        "IssueCommentEvent":      "💬 Commented in",
        "PullRequestReviewEvent": "👀 Reviewed PR in",
        "ReleaseEvent":           "🚀 Released in",
        "DeleteEvent":            "🗑️ Deleted from",
    }

    lines = []
    for ev in events:
        etype   = ev.get("type", "")
        repo    = ev.get("repo", {})
        rname   = repo.get("name", "—")
        rurl    = f"https://github.com/{rname}"
        created = relative_time(ev.get("created_at", ""))
        label   = TYPE_LABELS.get(etype, f"🔔 {etype} in")

        # Extra detail for push events (branch + commit count)
        extra = ""
        if etype == "PushEvent":
            payload = ev.get("payload", {})
            ref     = payload.get("ref", "").replace("refs/heads/", "")
            commits = len(payload.get("commits", []))
            extra   = f" `{ref}` ({commits} commit{'s' if commits != 1 else ''})"

        lines.append(f"- {label} [{rname}]({rurl}){extra} — _{created}_")

    return "\n".join(lines) if lines else "_No recent public activity._"


def build_profile_stats_section() -> str:
    """Fetch user profile + aggregate star/fork counts."""
    user: dict = gh_get(f"/users/{GITHUB_USERNAME}")
    if not user or "login" not in user:
        return "_⚠️ Could not fetch profile stats._"

    repos: list[dict] = gh_get(f"/users/{GITHUB_USERNAME}/repos?per_page=100&type=public")
    total_stars = sum(r.get("stargazers_count", 0) for r in (repos if isinstance(repos, list) else []))
    total_forks = sum(r.get("forks_count",       0) for r in (repos if isinstance(repos, list) else []))
    followers   = user.get("followers", 0)
    pub_repos   = user.get("public_repos", 0)
    updated_at  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return (
        "| 📦 Public Repos | ⭐ Total Stars | 🍴 Total Forks | 👥 Followers | 🕐 Last Updated |\n"
        "|:-:|:-:|:-:|:-:|:-:|\n"
        f"| **{pub_repos}** | **{total_stars}** | **{total_forks}** | **{followers}** | {updated_at} |"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"📖  Reading {README_PATH} …")
    try:
        with open(README_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        sys.exit(f"❌  {README_PATH} not found. Run this script from the repo root.")

    print("🌐  Fetching repos …")
    repos_md = build_repos_section()

    print("🌐  Fetching activity …")
    activity_md = build_activity_section()

    print("🌐  Fetching profile stats …")
    stats_md = build_profile_stats_section()

    print("✏️   Updating README sections …")
    content = replace_section(content, "REPOS",         repos_md)
    content = replace_section(content, "ACTIVITY",      activity_md)
    content = replace_section(content, "PROFILE-STATS", stats_md)

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("✅  README updated successfully!")


if __name__ == "__main__":
    main()
