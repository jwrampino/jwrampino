"""
pulls my daily contribution counts (public + private) from github's graphql api,
smooths them into a 7-day rolling average, and renders that as an svg.
runs daily via .github/workflows/stress.yml, which commits the output back.
"""

import os
import datetime
import requests

USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]
WINDOW = 7  # rolling average window, in days
DAYS_SHOWN = 90  # how much history to plot

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_contributions():
    to = datetime.datetime.utcnow()
    frm = to - datetime.timedelta(days=DAYS_SHOWN + WINDOW)  # pad so the first rolling avg point isn't starved
    resp = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {TOKEN}"},
        json={
            "query": QUERY,
            "variables": {
                "login": USERNAME,
                "from": frm.isoformat() + "Z",
                "to": to.isoformat() + "Z",
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    dates = []
    counts = []
    for week in data["weeks"]:
        for day in week["contributionDays"]:
            dates.append(day["date"])  # 'YYYY-MM-DD'
            counts.append(day["contributionCount"])
    return dates, counts


def rolling_average(values, window):
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def render_svg(dates, avg_values, path="stress.svg"):
    # trim to the window
    dates = dates[-DAYS_SHOWN:]
    avg_values = avg_values[-DAYS_SHOWN:]
    w, h = 700, 260
    pad_left, pad_right, pad_top, pad_bottom = 55, 20, 20, 40

    plot_w = w - pad_left - pad_right
    plot_h = h - pad_top - pad_bottom

    max_val = max(avg_values, default=1)
    max_val = max(max_val, 1)  # avoid divide by zero on a totally quiet stretch

    def x_at(i):
        return pad_left + (i / (len(avg_values) - 1)) * plot_w

    def y_at(v):
        return pad_top + plot_h - (v / max_val) * plot_h

    avg_points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(avg_values))

    # y-axis gridlines and labels, 4 ticks
    ticks = 4
    grid_lines = []
    y_tick_labels = []
    for t in range(ticks + 1):
        val = max_val * t / ticks
        y = y_at(val)
        grid_lines.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{w - pad_right}" y2="{y:.1f}" stroke="#1a2e23" stroke-width="1"/>')
        y_tick_labels.append(f'<text x="{pad_left - 10}" y="{y:.1f}" text-anchor="end" dominant-baseline="middle" class="tick">{val:.0f}</text>')

    # x-axis date labels, spaced
    x_tick_count = 6
    x_tick_labels = []
    n = len(dates)
    for t in range(x_tick_count):
        idx = round(t * (n - 1) / (x_tick_count - 1))
        label = datetime.datetime.strptime(dates[idx], "%Y-%m-%d").strftime("%b %-d")
        x = x_at(idx)
        x_tick_labels.append(f'<text x="{x:.1f}" y="{h - pad_bottom + 18}" text-anchor="middle" class="tick">{label}</text>')

    svg = f"""<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="rolling 7 day average of daily commit count">
  <title>stress chart</title>
  <defs>
    <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#eaf3de"/>
      <stop offset="100%" stop-color="#5dcaa5"/>
    </linearGradient>
  </defs>
  <style>
    text {{ font-family: 'Courier New', monospace; font-size: 11px; fill: #7fdca4; }}
    .axis-title {{ font-size: 12px; }}
  </style>
  <rect x="0" y="0" width="{w}" height="{h}" fill="#12211a"/>
  {''.join(grid_lines)}
  <line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{h - pad_bottom}" stroke="#2c4536" stroke-width="1"/>
  <line x1="{pad_left}" y1="{h - pad_bottom}" x2="{w - pad_right}" y2="{h - pad_bottom}" stroke="#2c4536" stroke-width="1"/>
  {''.join(y_tick_labels)}
  {''.join(x_tick_labels)}
  <text x="18" y="{pad_top + plot_h / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {pad_top + plot_h / 2:.1f})" class="axis-title">stress (# of commits)</text>
  <polyline points="{avg_points}" fill="none" stroke="url(#lineGrad)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

    with open(path, "w") as f:
        f.write(svg)


if __name__ == "__main__":
    dates, daily = fetch_contributions()
    smoothed = rolling_average(daily, WINDOW)
    render_svg(dates, smoothed)