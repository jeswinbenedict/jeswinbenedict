"""Builds dark_mode.svg and light_mode.svg: an ASCII portrait plus a
neofetch-style info panel with live GitHub stats.

Run locally:  GITHUB_TOKEN=... python scripts/build_profile.py
"""
import os
from collections import deque
from datetime import datetime, timezone
from html import escape

import requests
from PIL import Image, ImageFilter, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERNAME = os.environ.get("GITHUB_USERNAME", "jeswinbenedict")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── Layout ───────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1000, 545
ART_COLS, ART_ROWS = 64, 43          # portrait grid
ART_CHAR_W, ART_LINE_H = 6.0, 12     # px per cell at 10px Consolas (109% size-adjust)
ART_X, ART_Y = 15, 22
INFO_X, INFO_Y, INFO_LINE_H = 410, 30, 20
INFO_WIDTH = 59                      # chars per info line, for dot padding
RAMP = " .,:;!|ijlkmHM%@"

THEMES = {
    "dark": {"bg": "#161b22", "text": "#c9d1d9", "key": "#ff7b72",
             "value": "#a5d6ff", "cc": "#616e7f", "art": "#c9d1d9"},
    "light": {"bg": "#f6f8fa", "text": "#24292f", "key": "#a4062f",
              "value": "#0a3069", "cc": "#c2cfde", "art": "#24292f"},
}


# ── ASCII portrait ───────────────────────────────────────────────────────────
def portrait(path):
    im = Image.open(path).convert("RGB")
    left, right, top = 110, 744, 250
    height = int((right - left) / (ART_COLS * ART_CHAR_W) * ART_ROWS * ART_LINE_H)
    im = im.crop((left, top, right, top + height))

    # Flood-fill the flat backdrop from the edges to get a subject mask.
    small = im.resize((im.width // 4, im.height // 4)).filter(ImageFilter.GaussianBlur(1.5))
    w, h = small.size
    px = small.load()
    backdrop = (210, 206, 194)

    def is_backdrop(c):
        return sum((a - b) ** 2 for a, b in zip(c, backdrop)) < 28 ** 2

    seen = [[False] * w for _ in range(h)]
    queue = deque([(x, 0) for x in range(w)] + [(x, y) for y in range(h) for x in (0, w - 1)])
    for x, y in queue:
        seen[y][x] = True
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and is_backdrop(px[nx, ny]):
                seen[ny][nx] = True
                queue.append((nx, ny))
    mask = Image.new("L", (w, h))
    mask.putdata([0 if seen[y][x] else 255 for y in range(h) for x in range(w)])
    mask = mask.filter(ImageFilter.MinFilter(9))  # trims the white sticker outline

    gray = ImageOps.grayscale(im).filter(ImageFilter.UnsharpMask(radius=14, percent=260, threshold=0))
    gray = ImageOps.equalize(gray, mask=mask.resize(gray.size))
    gray = gray.resize((ART_COLS, ART_ROWS), Image.LANCZOS)
    mask = mask.resize((ART_COLS, ART_ROWS), Image.LANCZOS)

    lines = []
    for y in range(ART_ROWS):
        row = ""
        for x in range(ART_COLS):
            if mask.getpixel((x, y)) < 128:
                row += " "
            else:
                darkness = 1 - gray.getpixel((x, y)) / 255
                row += RAMP[min(len(RAMP) - 1, int(darkness * len(RAMP)))]
        lines.append(row.rstrip())
    return lines


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
    data = graphql("""
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
          totalCount
          nodes { stargazerCount }
        }
        repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
        contributionsCollection { contributionYears }
      }
    }""", {"login": USERNAME})["user"]

    commits = 0
    for year in data["contributionsCollection"]["contributionYears"]:
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z"
        commits += graphql("""
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
            }
          }
        }""", {"login": USERNAME, "from": start, "to": end})["user"]["contributionsCollection"]["totalCommitContributions"]

    return {
        "created": datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00")),
        "repos": data["repositories"]["totalCount"],
        "contributed": data["repositoriesContributedTo"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in data["repositories"]["nodes"]),
        "commits": commits,
        "followers": data["followers"]["totalCount"],
    }


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
    return f'{escape(title)} <tspan class="cc">{"—" * (INFO_WIDTH - len(title) - 1)}</tspan>'


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
        kv(["Languages", "Code"],"Dart, TypeScript, Python, Java, C++"),
        kv(["Languages", "Computer"], "HTML, CSS, SQL, LaTeX, YAML"),
        kv(["Frameworks"], "Flutter, React, Spring Boot, Node.js"),
        kv(["Cloud", "Tools"], "Firebase, GCP, MongoDB, Docker, Git"),
        kv(["Projects"], "LuzHire, NOVA, AERIX, Goel-AI"),
        "",
        header("- Contact"),
        kv(["Email"], "jeswinbenedict7@gmail.com"),
        kv(["Portfolio"], "jeswinbenedict.github.io/Portfolio"),
        kv(["LinkedIn"], "in/jeswin-karunya-benedict"),
        kv(["Instagram"], "@jechu_ben"),
        "",
        header("- GitHub Stats"),
        stats_line(("Repos", s["repos"]), ("Contributed", s["contributed"]), ("Stars", s["stars"])),
        stats_line(("Commits", s["commits"]), ("Followers", s["followers"])),
    ]


def stats_line(*pairs):
    cells = []
    for key, value in pairs:
        cells.append(f'<tspan class="key">{key}</tspan>: <tspan class="value">{value:,}</tspan>')
    return '<tspan class="cc">. </tspan>' + '<tspan class="cc"> | </tspan>'.join(cells)


# ── SVG ──────────────────────────────────────────────────────────────────────
def render(theme, art, info):
    c = THEMES[theme]
    art_svg = "\n".join(
        f'<tspan x="{ART_X}" y="{ART_Y + i * ART_LINE_H}">{escape(line)}</tspan>'
        for i, line in enumerate(art)
    )
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
text, tspan {{white-space: pre;}}
</style>
<rect width="{WIDTH}px" height="{HEIGHT}px" fill="{c['bg']}" rx="15"/>
<text x="{ART_X}" y="{ART_Y}" fill="{c['art']}" font-size="10px">
{art_svg}
</text>
<text x="{INFO_X}" y="{INFO_Y}" fill="{c['text']}">
{info_svg}
</text>
</svg>
"""


def main():
    art = portrait(os.path.join(ROOT, "assets", "profile.jpg"))
    info = info_lines(fetch_stats())
    for theme in THEMES:
        with open(os.path.join(ROOT, f"{theme}_mode.svg"), "w", encoding="utf-8") as f:
            f.write(render(theme, art, info))
    print("Built dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
