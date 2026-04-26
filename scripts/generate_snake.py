#!/usr/bin/env python3
"""Generate a growing-snake contribution SVG.

The snake traverses the contribution grid column-by-column (boustrophedon).
Each cell lights up permanently when the snake head passes over it,
creating a visually growing snake. At the end of each 20-second cycle
all cells reset and the snake starts over.
"""

import os
import sys
import json
import requests

USERNAME = "Anandha-scraper"
CYCLE = 20          # animation cycle in seconds
CELL = 11           # cell size px
GAP = 2             # gap between cells px
STEP = CELL + GAP   # 13 px per cell slot

CONTRIB_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
LIT_EMPTY = "#1e3a28"   # faint green for zero-contribution cells the snake eats


def get_base_color(count: int) -> str:
    if count == 0:  return CONTRIB_COLORS[0]
    if count < 4:   return CONTRIB_COLORS[1]
    if count < 7:   return CONTRIB_COLORS[2]
    if count < 10:  return CONTRIB_COLORS[3]
    return CONTRIB_COLORS[4]


def get_lit_color(count: int) -> str:
    if count == 0:
        return LIT_EMPTY
    return get_base_color(count)


def fetch_contributions() -> list[list[int]]:
    """Return grid[col][row] with contribution counts via GitHub GraphQL."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN env var not set")

    query = """
    {
      user(login: "%s") {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
              }
            }
          }
        }
      }
    }
    """ % USERNAME

    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": query},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]

    grid = []
    for week in weeks:
        col = [day["contributionCount"] for day in week["contributionDays"]]
        while len(col) < 7:
            col.append(0)
        grid.append(col)
    return grid


def build_path(grid: list[list[int]]) -> list[tuple[int, int, int]]:
    """Boustrophedon path: col 0 top→bottom, col 1 bottom→top, …"""
    path = []
    for col_idx, col in enumerate(grid):
        rows = range(7) if col_idx % 2 == 0 else range(6, -1, -1)
        for row in rows:
            path.append((col_idx, row, col[row]))
    return path


def cell_center(col: int, row: int, margin_left: int, margin_top: int) -> tuple[float, float]:
    x = margin_left + col * STEP + CELL / 2
    y = margin_top + row * STEP + CELL / 2
    return x, y


def generate_svg(grid: list[list[int]], path: list[tuple[int, int, int]]) -> str:
    cols = len(grid)
    margin_left = 30
    margin_top = 22
    margin_right = 12
    margin_bottom = 28

    width = margin_left + cols * STEP + margin_right
    height = margin_top + 7 * STEP + margin_bottom
    total = len(path)

    # Build animateMotion path through all cell centers
    pts = []
    for col, row, _ in path:
        x, y = cell_center(col, row, margin_left, margin_top)
        pts.append(f"{x:.1f},{y:.1f}")
    motion_d = "M " + " L ".join(pts)

    # Build path-index map  (col, row) → index in path
    path_idx: dict[tuple[int, int], int] = {}
    for i, (col, row, _) in enumerate(path):
        path_idx[(col, row)] = i

    # ── CSS @keyframes for each cell ──────────────────────────────────────
    kf_lines: list[str] = []
    for i, (col, row, count) in enumerate(path):
        base = get_base_color(count)
        lit  = get_lit_color(count)
        pct  = i / total * 100           # % when head arrives
        pct2 = min(pct + 0.18, 100)      # snap point (stays lit)

        if i == 0:
            kf_lines.append(
                f"@keyframes c0{{0%{{fill:{lit};}}100%{{fill:{lit};}}}}"
            )
        else:
            kf_lines.append(
                f"@keyframes c{i}{{"
                f"0%,{pct:.3f}%{{fill:{base};}}"
                f"{pct2:.3f}%,100%{{fill:{lit};}}}}"
            )

    css_block = "\n      ".join(kf_lines)

    # ── Cell <rect> elements ───────────────────────────────────────────────
    cell_rects: list[str] = []
    for ci, col in enumerate(grid):
        for ri in range(7):
            count = col[ri]
            x = margin_left + ci * STEP
            y = margin_top  + ri * STEP
            i = path_idx.get((ci, ri), 0)
            base = get_base_color(count)
            cell_rects.append(
                f'<rect style="animation:c{i} {CYCLE}s linear infinite;" '
                f'x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{base}"/>'
            )

    # ── Day labels ────────────────────────────────────────────────────────
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_labels = []
    for i, day in enumerate(days):
        if i % 2 == 1:
            y = margin_top + i * STEP + CELL
            day_labels.append(
                f'<text x="{margin_left - 5}" y="{y}" text-anchor="end" '
                f'font-size="8" fill="#8b949e" font-family="monospace">{day}</text>'
            )

    # ── Month labels (every ~4 weeks) ─────────────────────────────────────
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    month_labels = []
    prev_month = -1
    for ci in range(0, cols, 4):
        if ci < cols:
            month_idx = ci // 4 % 12
            if month_idx != prev_month:
                x = margin_left + ci * STEP
                month_labels.append(
                    f'<text x="{x}" y="{margin_top - 6}" '
                    f'font-size="8" fill="#8b949e" font-family="monospace">{months[month_idx]}</text>'
                )
                prev_month = month_idx

    # ── Legend ────────────────────────────────────────────────────────────
    leg_y = height - 14
    leg_x = width - 128
    legend_parts = [
        f'<text x="{leg_x - 3}" y="{leg_y + 9}" font-size="8" fill="#8b949e" font-family="monospace">Less</text>'
    ]
    for j, color in enumerate(CONTRIB_COLORS):
        lx = leg_x + 22 + j * 14
        legend_parts.append(f'<rect x="{lx}" y="{leg_y}" width="11" height="11" rx="2" fill="{color}"/>')
    legend_parts.append(
        f'<text x="{leg_x + 22 + 5 * 14 + 3}" y="{leg_y + 9}" '
        f'font-size="8" fill="#8b949e" font-family="monospace">More</text>'
    )

    title = (
        f'<text x="{margin_left}" y="{leg_y + 9}" '
        f'font-size="9" fill="#8b949e" font-family="monospace">'
        f'@{USERNAME} · growing snake</text>'
    )

    # ── Assemble SVG ──────────────────────────────────────────────────────
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%">
  <defs>
    <filter id="hglow" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="b1"/>
      <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="b2"/>
      <feMerge><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <style>
      {css_block}
    </style>
  </defs>

  <!-- Background -->
  <rect width="{width}" height="{height}" fill="#0d1117"/>

  <!-- Day labels -->
  {''.join(day_labels)}

  <!-- Month labels -->
  {''.join(month_labels)}

  <!-- Contribution cells -->
  {''.join(cell_rects)}

  <!-- Hidden motion path -->
  <path id="sp" d="{motion_d}" fill="none" stroke="none"/>

  <!-- Snake body trail (head glow creates "eaten" feel) -->

  <!-- Snake head group: body + eyes -->
  <g filter="url(#hglow)">
    <circle r="7.5" fill="#00FF41">
      <animateMotion dur="{CYCLE}s" repeatCount="indefinite" rotate="auto">
        <mpath href="#sp"/>
      </animateMotion>
    </circle>
  </g>

  <!-- Eyes (no glow, on top) -->
  <g>
    <circle r="2.2" fill="white">
      <animateMotion dur="{CYCLE}s" repeatCount="indefinite" rotate="auto">
        <mpath href="#sp"/>
      </animateMotion>
    </circle>
  </g>
  <g>
    <circle r="1" fill="#0d1117">
      <animateMotion dur="{CYCLE}s" repeatCount="indefinite" rotate="auto">
        <mpath href="#sp"/>
      </animateMotion>
    </circle>
  </g>

  <!-- Legend & title -->
  {title}
  {''.join(legend_parts)}
</svg>"""
    return svg


def main() -> None:
    os.makedirs("dist", exist_ok=True)

    try:
        print(f"Fetching contributions for @{USERNAME} …")
        grid = fetch_contributions()
        print(f"  Got {len(grid)} weeks")
    except Exception as exc:
        print(f"Warning: could not fetch contributions ({exc}). Using empty grid.")
        grid = [[0] * 7 for _ in range(52)]

    path = build_path(grid)
    print(f"  Path: {len(path)} cells")

    svg = generate_svg(grid, path)
    out = "dist/growing-snake.svg"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"Written {out} ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
