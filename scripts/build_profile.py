"""Builds dark_mode.svg and light_mode.svg: a gold pixel-art portrait logo
(in the style of the Hermes Agent wordmark) plus a neofetch-style info panel
with live GitHub stats.

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
LOGO_X, LOGO_Y = 12, 12
LOGO_W, LOGO_H = 384, 516            # portrait area in px
PIXEL = 6                            # px per logo pixel
LOGO_COLS, LOGO_ROWS = LOGO_W // PIXEL, LOGO_H // PIXEL
TONE_CUTS = (0.18, 0.43, 0.74)       # brightness thresholds -> tones 0..3
TONE_SHADE = (0.2, 0.42, 0.72, 1.0)  # band colour multiplier per tone
BAND_STARTS = (0.0, 0.58, 0.76)      # top/middle/bottom colour bands, as row fractions
SHADOW_OFFSETS = (10, 6)             # offset outlines behind the logo, outer first
INFO_X, INFO_Y, INFO_LINE_H = 410, 30, 20
INFO_WIDTH = 59                      # chars per info line, for dot padding

THEMES = {
    "dark": {"bg": "#141414", "border": "#2a2416", "text": "#e6e6e6", "title": "#ffd700",
             "key": "#ffb800", "value": "#e6edf3", "cc": "#5a5650",
             "bands": ("#ffd700", "#ffb800", "#d68030"), "shadows": ("#96641a", "#dca028")},
    "light": {"bg": "#fbf8f1", "border": "#e8dcc0", "text": "#2b2105", "title": "#a86400",
              "key": "#a86400", "value": "#1f2328", "cc": "#c9bfa8",
              "bands": ("#e0a800", "#d08a00", "#b5651d"), "shadows": ("#c99a4a", "#b07a20")},
}


# ── Pixel-art portrait ───────────────────────────────────────────────────────
def portrait(path):
    """Returns a LOGO_ROWS x LOGO_COLS grid of tones 0-3, or None for background."""
    im = Image.open(path).convert("RGB")
    left, right, top = 140, 714, 255
    im = im.crop((left, top, right, top + int((right - left) * LOGO_H / LOGO_W)))

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

    # Tone the head and the sweater separately so the face keeps its contrast.
    gray = ImageOps.grayscale(im).filter(ImageFilter.UnsharpMask(radius=10, percent=170, threshold=0))
    split = int(gray.height * 0.70)
    full = mask.resize(gray.size)
    head, body = full.copy(), full.copy()
    head.paste(0, (0, split, head.width, head.height))
    body.paste(0, (0, 0, body.width, split))
    toned = ImageOps.equalize(gray, mask=head)
    toned.paste(ImageOps.autocontrast(gray, cutoff=1, mask=body).crop((0, split, gray.width, gray.height)), (0, split))
    toned = toned.resize((LOGO_COLS, LOGO_ROWS), Image.BOX)
    mask = mask.resize((LOGO_COLS, LOGO_ROWS), Image.BOX)

    return [
        [None if mask.getpixel((x, y)) < 128 else sum(toned.getpixel((x, y)) / 255 >= c for c in TONE_CUTS)
         for x in range(LOGO_COLS)]
        for y in range(LOGO_ROWS)
    ]


def shade(hex_color, factor):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def logo_svg(grid, c):
    """Pixel runs coloured by band and tone, over offset silhouette outlines."""
    edges = []
    for y, row in enumerate(grid):
        for x, tone in enumerate(row):
            if tone is None:
                continue
            for dx, dy, seg in ((0, -1, "h"), (0, 1, "h"), (-1, 0, "v"), (1, 0, "v")):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < LOGO_COLS and 0 <= ny < LOGO_ROWS) or grid[ny][nx] is None:
                    edges.append(f"M{(x + (dx == 1)) * PIXEL} {(y + (dy == 1)) * PIXEL}{seg}{PIXEL}")
    outline = "".join(edges)
    parts = [
        f'<path transform="translate({offset} {offset})" d="{outline}" stroke="{color}" stroke-width="1.2" fill="none"/>'
        for offset, color in zip(SHADOW_OFFSETS, c["shadows"])
    ]

    for y, row in enumerate(grid):
        band = c["bands"][sum(y / LOGO_ROWS >= start for start in BAND_STARTS) - 1]
        x = 0
        while x < LOGO_COLS:
            tone = row[x]
            run = 1
            while x + run < LOGO_COLS and row[x + run] == tone:
                run += 1
            if tone is not None:
                parts.append(f'<rect x="{x * PIXEL}" y="{y * PIXEL}" width="{run * PIXEL}" '
                             f'height="{PIXEL}" fill="{shade(band, TONE_SHADE[tone])}"/>')
            x += run
    body = "\n".join(parts)
    return f'<g transform="translate({LOGO_X} {LOGO_Y})" shape-rendering="crispEdges">\n{body}\n</g>'


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
        stats_line(("Repos", s["repos"]), ("Contributed", s["contributed"]), ("Stars", s["stars"])),
        stats_line(("Commits", s["commits"]), ("Followers", s["followers"])),
    ]


def stats_line(*pairs):
    cells = []
    for key, value in pairs:
        cells.append(f'<tspan class="key">{key}</tspan>: <tspan class="value">{value:,}</tspan>')
    return '<tspan class="cc">. </tspan>' + '<tspan class="cc"> | </tspan>'.join(cells)


# ── SVG ──────────────────────────────────────────────────────────────────────
def render(theme, grid, info):
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
<rect x="0.5" y="0.5" width="{WIDTH - 1}px" height="{HEIGHT - 1}px" fill="{c['bg']}" stroke="{c['border']}" rx="15"/>
{logo_svg(grid, c)}
<text x="{INFO_X}" y="{INFO_Y}" fill="{c['text']}">
{info_svg}
</text>
</svg>
"""


def main():
    grid = portrait(os.path.join(ROOT, "assets", "profile.jpg"))
    info = info_lines(fetch_stats())
    for theme in THEMES:
        with open(os.path.join(ROOT, f"{theme}_mode.svg"), "w", encoding="utf-8") as f:
            f.write(render(theme, grid, info))
    print("Built dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
