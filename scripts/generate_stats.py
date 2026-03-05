import os
import requests
import json

USERNAME = os.environ.get("GITHUB_USERNAME", "jeswinbenedict")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# ── Fetch stats via GraphQL ──────────────────────────────────────────────────
QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
    }
    followers { totalCount }
  }
}
"""

resp = requests.post(
    "https://api.github.com/graphql",
    headers=HEADERS,
    json={"query": QUERY, "variables": {"login": USERNAME}}
)
data = resp.json()["data"]["user"]

contributions = data["contributionsCollection"]
commits  = contributions["totalCommitContributions"]
prs      = contributions["totalPullRequestContributions"]
issues   = contributions["totalIssueContributions"]
repos    = contributions["totalRepositoryContributions"]
stars    = sum(r["stargazerCount"] for r in data["repositories"]["nodes"])
followers = data["followers"]["totalCount"]

# ── Aggregate top languages ──────────────────────────────────────────────────
lang_sizes: dict = {}
lang_colors: dict = {}
for repo in data["repositories"]["nodes"]:
    for edge in repo["languages"]["edges"]:
        name  = edge["node"]["name"]
        color = edge["node"]["color"] or "#858585"
        lang_sizes[name]  = lang_sizes.get(name, 0) + edge["size"]
        lang_colors[name] = color

top_langs = sorted(lang_sizes.items(), key=lambda x: x[1], reverse=True)[:5]
total_size = sum(s for _, s in top_langs) or 1

# ── SVG dimensions ───────────────────────────────────────────────────────────
W, H = 480, 220
BAR_Y      = 148
BAR_H      = 8
BAR_X      = 20
BAR_WIDTH  = W - 40

# Build language bar segments
bar_segments = []
lang_legend  = []
x_cursor = BAR_X
for i, (lang, size) in enumerate(top_langs):
    pct   = size / total_size
    seg_w = round(pct * BAR_WIDTH, 2)
    color = lang_colors[lang]
    bar_segments.append(
        f'<rect x="{x_cursor}" y="{BAR_Y}" width="{seg_w}" height="{BAR_H}" '
        f'fill="{color}" rx="2"/>'
    )
    lang_legend.append((lang, color, f"{pct*100:.1f}%"))
    x_cursor += seg_w

# Legend items (2 per row)
legend_svg = ""
for i, (lang, color, pct) in enumerate(lang_legend):
    col = i % 2
    row = i // 2
    lx  = BAR_X + col * 220
    ly  = BAR_Y + 24 + row * 20
    legend_svg += (
        f'<circle cx="{lx+6}" cy="{ly}" r="5" fill="{color}"/>'
        f'<text x="{lx+16}" y="{ly+4}" fill="#888" font-size="11" font-family="monospace">'
        f'{lang} <tspan fill="#ccc">{pct}</tspan></text>'
    )

# Stats row
stat_items = [
    ("Commits",   commits),
    ("PRs",       prs),
    ("Issues",    issues),
    ("Stars",     stars),
    ("Followers", followers),
]
stat_spacing = (W - 40) / len(stat_items)
stats_svg = ""
for i, (label, value) in enumerate(stat_items):
    sx = BAR_X + i * stat_spacing + stat_spacing / 2
    stats_svg += (
        f'<text x="{sx}" y="68" fill="#fff" font-size="18" font-weight="bold" '
        f'text-anchor="middle" font-family="monospace">{value}</text>'
        f'<text x="{sx}" y="86" fill="#666" font-size="10" '
        f'text-anchor="middle" font-family="monospace">{label}</text>'
    )

svg = f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     xmlns="http://www.w3.org/2000/svg">
  <rect width="{W}" height="{H}" rx="10" fill="#0d1117"/>

  <!-- Title -->
  <text x="20" y="36" fill="#fff" font-size="15" font-weight="bold"
        font-family="monospace">{USERNAME}'s GitHub Stats</text>
  <line x1="20" y1="46" x2="{W-20}" y2="46" stroke="#21262d" stroke-width="1"/>

  <!-- Stat numbers -->
  {stats_svg}

  <line x1="20" y1="100" x2="{W-20}" y2="100" stroke="#21262d" stroke-width="1"/>

  <!-- Language label -->
  <text x="20" y="122" fill="#888" font-size="11" font-family="monospace">
    Most Used Languages
  </text>

  <!-- Bar -->
  {''.join(bar_segments)}

  <!-- Legend -->
  {legend_svg}
</svg>"""

os.makedirs("assets", exist_ok=True)
with open("assets/github-stats.svg", "w") as f:
    f.write(svg)

print(f"✅  Stats SVG generated → assets/github-stats.svg")
print(f"   Commits:{commits}  PRs:{prs}  Stars:{stars}  Followers:{followers}")
