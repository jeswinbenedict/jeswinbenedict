"""Builds dark_mode.svg and light_mode.svg: a two-tone ink portrait (traced
from assets/illustration.jpg by make_portrait.py) plus a neofetch-style info panel
with live GitHub stats.

Run locally:  GITHUB_TOKEN=... python scripts/build_profile.py
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from html import escape

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERNAME = os.environ.get("GITHUB_USERNAME", "jeswinbenedict")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── Layout ───────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1000, 545
PORTRAIT_X, PORTRAIT_W = 12, 384     # portrait sits on the card's bottom edge
STICKER = 2                          # px of extra paper border around the sticker
INFO_X, INFO_Y, INFO_LINE_H = 410, 30, 20
INFO_WIDTH = 59                      # chars per info line, for dot padding

THEMES = {
    "dark": {"bg": "#111111", "border": "#2a2a2a", "text": "#e6e6e6", "title": "#ff4d5e",
             "key": "#f4f1ea", "value": "#a9a9a9", "cc": "#3d3d3d",
             "paper": "#f4f1ea", "ink": "#111111", "rim": "#3a3a3a"},
    "light": {"bg": "#ffffff", "border": "#e5e5e5", "text": "#111111", "title": "#d62839",
              "key": "#111111", "value": "#555555", "cc": "#cfcfcf",
              "paper": "#ffffff", "ink": "#111111", "rim": "#d0d0d0"},
}


# ── Ink portrait ─────────────────────────────────────────────────────────────
def portrait_svg(p, c):
    """Paper silhouette with a sticker border, ink on top, anchored to the card bottom."""
    scale = PORTRAIT_W / p["width"]
    y = HEIGHT - p["height"] * scale
    return f"""<g clip-path="url(#card)">
<g transform="translate({PORTRAIT_X} {y:.1f}) scale({scale:.4f})">
<path d="{p['paper']}" fill="{c['paper']}" stroke="{c['rim']}" stroke-width="{(STICKER + 2) * 2 / scale:.1f}" stroke-linejoin="round"/>
<path d="{p['paper']}" fill="{c['paper']}" stroke="{c['paper']}" stroke-width="{STICKER * 2 / scale:.1f}" stroke-linejoin="round"/>
<path d="{p['ink']}" fill="{c['ink']}" fill-rule="evenodd"/>
</g>
</g>"""


# ── GitHub stats ─────────────────────────────────────────────────────────────
def graphql(query, variables):
    resp = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats():
    """Public numbers, matching what github.com/USERNAME shows to visitors."""
    data = graphql("""
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 100) {
          totalCount
          nodes { stargazerCount }
        }
        contributionsCollection {
          contributionYears
          totalRepositoriesWithContributedCommits
        }
      }
    }""", {"login": USERNAME})["user"]

    # Sum every year so the totals are all-time, not just the last 12 months.
    # The calendar total includes private contributions (shown on the profile
    # as a count only); commits and PRs are public ones.
    contributions = commits = prs = 0
    for year in data["contributionsCollection"]["contributionYears"]:
        year_data = graphql("""
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { totalContributions }
              totalCommitContributions
              totalPullRequestContributions
            }
          }
        }""", {"login": USERNAME, "from": f"{year}-01-01T00:00:00Z",
               "to": f"{year}-12-31T23:59:59Z"})["user"]["contributionsCollection"]
        contributions += year_data["contributionCalendar"]["totalContributions"]
        commits += year_data["totalCommitContributions"]
        prs += year_data["totalPullRequestContributions"]

    stats = {
        "created": datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00")),
        "repos": data["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in data["repositories"]["nodes"]),
        "followers": data["followers"]["totalCount"],
        "contributions": contributions,
        "commits": commits,
        "prs": prs,
        # Same figure as the profile's "Contributed to ... repositories" (last 12 months).
        "contributed": data["contributionsCollection"]["totalRepositoriesWithContributedCommits"],
    }
    print({k: v for k, v in stats.items() if k != "created"})
    return stats


def uptime(since):
    now = datetime.now(timezone.utc)
    months = (now.year - since.year) * 12 + now.month - since.month
    days = now.day - since.day
    if days < 0:
        months -= 1
        prev_month_end = now.replace(day=1).toordinal() - 1
        days += datetime.fromordinal(prev_month_end).day
    years, months = divmod(months, 12)
    parts = [(years, "year"), (months, "month"), (days, "day")]
    return ", ".join(f"{n} {unit}{'' if n == 1 else 's'}" for n, unit in parts if n or unit == "day")


# ── Info panel ───────────────────────────────────────────────────────────────
def kv(keys, value):
    """One `. Key.Sub: ..... value` line, dot-padded to INFO_WIDTH."""
    label = ".".join(keys)
    dots = max(1, INFO_WIDTH - len(label) - len(value) - 5)
    key_svg = '<tspan class="cc">.</tspan>'.join(f'<tspan class="key">{escape(k)}</tspan>' for k in keys)
    return (f'<tspan class="cc">. </tspan>{key_svg}:<tspan class="cc"> {"." * dots} </tspan>'
            f'<tspan class="value">{escape(value)}</tspan>')


def header(title):
    return f'<tspan class="title">{escape(title)}</tspan> <tspan class="cc">{"—" * (INFO_WIDTH - len(title) - 1)}</tspan>'


def info_lines(s):
    return [
        header("jeswin@benedict"),
        kv(["OS"], "Windows 11, Android, Linux"),
        kv(["Uptime"], uptime(s["created"]) + " on GitHub"),
        kv(["Host"], "VIT-AP University"),
        kv(["Kernel"], "B.Tech Computer Science Student"),
        kv(["Role"], "Full-Stack & Flutter Developer"),
        kv(["Focus"], "Safety-Tech, AI, IoT"),
        kv(["Location"], "Tamil Nadu, India"),
        "",
        kv(["Languages", "Code"], "Dart, TypeScript, Python, Java, C++"),
        kv(["Languages", "Computer"], "HTML, CSS, SQL, LaTeX, YAML"),
        kv(["Frameworks"], "Flutter, React, Spring Boot, Node.js"),
        kv(["Cloud", "Tools"], "Firebase, GCP, MongoDB, Docker, Git"),
        kv(["Projects"], "LuzHire, NOVA, AERIX, Goel-AI"),
        "",
        header("- Contact"),
        kv(["Email"], "jeswinbenedict7@gmail.com"),
        kv(["Portfolio"], "jeswinkarunyabenedict.vercel.app"),
        kv(["LinkedIn"], "in/jeswin-karunya-benedict"),
        kv(["Instagram"], "@jechu_ben"),
        "",
        header("- GitHub Stats"),
        stats_line(("Repos", s["repos"]), ("Stars", s["stars"]), ("Followers", s["followers"])),
        stats_line(("Contributions", s["contributions"]), ("Commits", s["commits"]), ("PRs", s["prs"])),
        stats_line(("Contributed to", f'{s["contributed"]} repos in the last year')),
    ]


def stats_line(*pairs):
    cells = []
    for key, value in pairs:
        text = f"{value:,}" if isinstance(value, int) else escape(value)
        cells.append(f'<tspan class="key">{key}</tspan>: <tspan class="value">{text}</tspan>')
    return '<tspan class="cc">. </tspan>' + '<tspan class="cc"> | </tspan>'.join(cells)


# ── SVG ──────────────────────────────────────────────────────────────────────
def render(theme, portrait, info):
    c = THEMES[theme]
    info_svg = "\n".join(
        f'<tspan x="{INFO_X}" y="{INFO_Y + i * INFO_LINE_H}">{line}</tspan>'
        for i, line in enumerate(info) if line
    )
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="{WIDTH}px" height="{HEIGHT}px" font-size="16px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: {c['key']};}}
.value {{fill: {c['value']};}}
.cc {{fill: {c['cc']};}}
.title {{fill: {c['title']}; font-weight: bold;}}
text, tspan {{white-space: pre;}}
</style>
<clipPath id="card"><rect width="{WIDTH}px" height="{HEIGHT}px" rx="15"/></clipPath>
<rect x="0.5" y="0.5" width="{WIDTH - 1}px" height="{HEIGHT - 1}px" fill="{c['bg']}" stroke="{c['border']}" rx="15"/>
{portrait_svg(portrait, c)}
<text x="{INFO_X}" y="{INFO_Y}" fill="{c['text']}">
{info_svg}
</text>
</svg>
"""


def main():
    with open(os.path.join(ROOT, "assets", "portrait.json"), encoding="utf-8") as f:
        portrait = json.load(f)
    info = info_lines(fetch_stats())
    svgs = {theme: render(theme, portrait, info) for theme in THEMES}
    for theme, svg in svgs.items():
        with open(os.path.join(ROOT, f"{theme}_mode.svg"), "w", encoding="utf-8") as f:
            f.write(svg)

    # Browsers and GitHub's image proxy cache the card by URL, so stamp the
    # README's image links with a content hash to make every change a new URL.
    version = hashlib.sha1("".join(svgs.values()).encode()).hexdigest()[:10]
    readme = os.path.join(ROOT, "README.md")
    with open(readme, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"(/(?:dark|light)_mode\.svg)(\?v=\w+)?", rf"\1?v={version}", text)
    with open(readme, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"Built dark_mode.svg and light_mode.svg (v={version})")


if __name__ == "__main__":
    main()
