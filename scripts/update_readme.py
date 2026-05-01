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

# Repos to always feature
PINNED_REPOS = [
    "Medical-Image-Enhancement",
    "Dr_Moddel",
    "ICU-Mortality-LHS",
    "Growth-Tracker",
]

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
    token = os.environ.get("GITHUB_TOKEN", "")
    url   = f"{API_BASE}{path}"
    req   = request.Request(url, headers={
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":           f"readme-updater/{GITHUB_USERNAME}",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    try:
        # Timeout strictly set to 15 seconds to prevent hanging
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        print(f"⚠️ Error fetching {url}: {exc}")
        return {}

def relative_time(iso: str) -> str:
    if not iso: return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0: return "today"
        if days < 7: return f"{days}d ago"
        if days < 30: return f"{days // 7}w ago"
        return f"{days // 30}mo ago"
    except:
        return "—"

def replace_section(content: str, tag: str, new_body: str) -> str:
    # Aapke README mein tags <!-- REPOS-START --> format mein hain
    pattern = rf"(<!-- {tag}-START -->).*?(<!-- {tag}-END -->)"
    replacement = rf"\1\n{new_body}\n\2"
    result, n = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if n == 0:
        print(f"⚠️  Marker {tag} not found in README.")
    return result

# ── Section builders ──────────────────────────────────────────────────────────

def build_repos_section() -> str:
    all_repos = gh_get(f"/users/{GITHUB_USERNAME}/repos?per_page=100&type=public")
    if not all_repos or not isinstance(all_repos, list):
        return "_⚠️ Could not fetch repositories._"

    by_name = {r["name"]: r for r in all_repos}
    ordered = [by_name[name] for name in PINNED_REPOS if name in by_name]
    
    seen = set(PINNED_REPOS)
    rest = sorted([r for r in all_repos if r["name"] not in seen],
                  key=lambda r: r.get("pushed_at") or "", reverse=True)
    ordered.extend(rest[:6]) # Show top 6 other repos

    rows = ["| Project | Description | Language | Last Push |", "|---|---|---|---|"]
    for repo in ordered:
        name, url = repo["name"], repo["html_url"]
        desc = (repo.get("description") or "—").replace("|", "\\|")
        lang = repo.get("language") or "—"
        emoji = LANG_EMOJI.get(lang, "📁")
        pushed = relative_time(repo.get("pushed_at", ""))
        rows.append(f"| [{name}]({url}) | {desc} | {emoji} {lang} | {pushed} |")

    return "\n".join(rows)

def build_activity_section() -> str:
    events = gh_get(f"/users/{GITHUB_USERNAME}/events/public?per_page=10")
    if not events or not isinstance(events, list):
        return "_No recent activity found._"

    lines = []
    for ev in events[:8]:
        etype = ev.get("type", "")
        rname = ev.get("repo", {}).get("name", "—")
        created = relative_time(ev.get("created_at", ""))
        if etype == "PushEvent":
            lines.append(f"- 🔨 Pushed to [{rname}](https://github.com/{rname}) — _{created}_")
    return "\n".join(lines) if lines else "_No recent activity._"

def build_profile_stats_section() -> str:
    user = gh_get(f"/users/{GITHUB_USERNAME}")
    if not user or "login" not in user: return ""
    
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (f"| 📦 Repos | 👥 Followers | 🕐 Last Updated |\n"
            f"|:-:|:-:|:-:|\n"
            f"| **{user.get('public_repos', 0)}** | **{user.get('followers', 0)}** | {updated_at} |")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(README_PATH):
        print(f"❌ {README_PATH} not found")
        return

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    print("🌐 Updating README zones...")
    content = replace_section(content, "REPOS", build_repos_section())
    content = replace_section(content, "ACTIVITY", build_activity_section())
    content = replace_section(content, "PROFILE-STATS", build_profile_stats_section())

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ Done!")

if __name__ == "__main__":
    main()
