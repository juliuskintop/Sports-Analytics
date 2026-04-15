"""
player_ranked.py
----------------
All-time top NBA players by starter points across 4 Sleeper fantasy seasons
(2022-2025).  Produces a ranked horizontal stacked-bar chart saved as
player_ranked.png in the same directory as this script.

Run with:
    uv run --with requests --with matplotlib python3 player_ranked.py
"""

# ── Standard library ──────────────────────────────────────────────────────────
import os
import sys
from collections import defaultdict
from datetime import date

# ── Third-party (injected by uv) ──────────────────────────────────────────────
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "https://api.sleeper.app/v1"

# League IDs and the number of weeks played each season.
# Sleeper's last_scored_leg can differ from the true final week when the API
# hasn't been closed out, so we pass explicit max_weeks as a safety cap.
LEAGUES = [
    {"id": "819248226988314624",  "season": "2022", "max_weeks": 25},
    {"id": "981579242393636864",  "season": "2023", "max_weeks": 25},
    {"id": "1145596058320506880", "season": "2024", "max_weeks": 24},
    {"id": "1219479299124371456", "season": "2025", "max_weeks": 24},
]

# Reference date used to compute player ages from birth_date.
TODAY = date(2026, 4, 15)

# Number of players to include in the chart.
TOP_N = 35

# Per-manager colour (morgannakonechny and JeremyW share roster-7 across
# seasons and therefore share the same colour).
TEAM_COLORS = {
    "Ju1ius":           "#E63946",
    "ISTOLL21":         "#2196F3",
    "MattBlake":        "#FF9800",
    "joshstoll9":       "#9C27B0",
    "blockadamd00":     "#4CAF50",
    "fastillo15":       "#00BCD4",
    "morgannakonechny": "#F06292",
    "JeremyW":          "#F06292",   # same slot, different seasons
    "ryrythejedi":      "#8BC34A",
    "Hamiltontp":       "#FF5722",
    "Larz00":           "#607D8B",
}

TEAM_NAMES = {
    "Ju1ius":           "Ball Cancer",
    "ISTOLL21":         "The Meat-Off",
    "MattBlake":        "BallSiak",
    "joshstoll9":       "Wembys 4 for 4",
    "blockadamd00":     "Redraft Next Year?",
    "fastillo15":       "Curious Mike",
    "morgannakonechny": "big purr",
    "JeremyW":          "JeremyW",
    "ryrythejedi":      "27 days, 27 nights",
    "Hamiltontp":       "Halibussy",
    "Larz00":           "Gid(didd)ey's Kiddies",
}

# Chart colours
BG_COLOR     = "#0f1117"
PANEL_COLOR  = "#1a1d26"
GRID_COLOR   = "#2e3140"

# =============================================================================
# STEP 1 — Fetch matchup data and accumulate starter points
# =============================================================================
# Structure: pts_by_player[player_id][username] = total_starter_points
pts_by_player: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

for league in LEAGUES:
    league_id = league["id"]
    season    = league["season"]
    max_weeks = league["max_weeks"]

    print(f"[{season}] Fetching league metadata…")
    league_meta = requests.get(f"{BASE_URL}/league/{league_id}").json()

    # Use the lesser of last_scored_leg (from the API) and max_weeks so we
    # never request weeks that have no data.
    last_scored = league_meta["settings"].get("last_scored_leg", max_weeks)
    weeks_to_fetch = min(last_scored, max_weeks)
    print(f"[{season}] Fetching {weeks_to_fetch} weeks…")

    # Build owner_id → display_name map from the /users endpoint.
    users = requests.get(f"{BASE_URL}/league/{league_id}/users").json()
    owner_to_username: dict[str, str] = {
        u["user_id"]: u["display_name"] for u in users
    }

    # Build roster_id → username map via the /rosters endpoint.
    rosters = requests.get(f"{BASE_URL}/league/{league_id}/rosters").json()
    roster_to_username: dict[int, str] = {
        r["roster_id"]: owner_to_username.get(r["owner_id"], "unknown")
        for r in rosters
    }

    # Iterate every week and every team in each matchup.
    for week in range(1, weeks_to_fetch + 1):
        matchups = requests.get(
            f"{BASE_URL}/league/{league_id}/matchups/{week}"
        ).json()

        for team in matchups:
            username       = roster_to_username.get(team["roster_id"], "unknown")
            players_points = team.get("players_points", {})

            # Only credit a player when they were a starter that week.
            for pid in team.get("starters", []):
                pts = players_points.get(pid, 0.0)
                if pts > 0:                        # skip 0-pt / empty slots
                    pts_by_player[pid][username] += pts

print(f"Accumulated data for {len(pts_by_player):,} player IDs.")

# =============================================================================
# STEP 2 — Fetch NBA player names and birth dates
# =============================================================================
print("Fetching NBA player data…")
nba_players: dict[str, dict] = requests.get(f"{BASE_URL}/players/nba").json()

def player_display_name(p: dict) -> str:
    """Return full_name, or assemble from first/last if missing."""
    return (
        p.get("full_name")
        or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        or "Unknown"
    )

def player_age(p: dict) -> int | None:
    """Return player age (years) relative to TODAY, or None if unknown."""
    birth_str = p.get("birth_date")  # expected format: "YYYY-MM-DD"
    if not birth_str:
        return None
    try:
        y, m, d = (int(x) for x in birth_str.split("-"))
        bday = date(y, m, d)
        age  = (TODAY - bday).days // 365
        return age
    except Exception:
        return None

player_name: dict[str, str]      = {}
player_age_map: dict[str, int | None] = {}

for pid, p in nba_players.items():
    player_name[pid]    = player_display_name(p)
    player_age_map[pid] = player_age(p)

# =============================================================================
# STEP 3 — Rank top-N players by total all-time starter points
# =============================================================================
# Compute total pts across all managers for each player_id.
total_pts: dict[str, float] = {
    pid: sum(mgr_pts.values())
    for pid, mgr_pts in pts_by_player.items()
}

# Sort descending and take the top-N.
ranked_pids: list[str] = sorted(
    total_pts, key=lambda pid: total_pts[pid], reverse=True
)[:TOP_N]

print(f"Top {TOP_N} players selected.")

# =============================================================================
# STEP 4 — Build chart data: per-player list of (username, pts) sorted by pts
# =============================================================================
# chart_rows[i] = list of (username, pts) for ranked_pids[i], sorted desc.
chart_rows: list[list[tuple[str, float]]] = []
for pid in ranked_pids:
    segments = sorted(
        pts_by_player[pid].items(), key=lambda kv: kv[1], reverse=True
    )
    chart_rows.append(segments)

# Collect every username that actually appears in the top-N rows (for legend).
legend_users: list[str] = []
seen: set[str] = set()
for segments in chart_rows:
    for username, _ in segments:
        if username not in seen:
            legend_users.append(username)
            seen.add(username)

# =============================================================================
# STEP 5 — Draw the chart
# =============================================================================
fig_height = TOP_N * 0.54 + 2.5
fig, ax = plt.subplots(figsize=(18, fig_height))
fig.patch.set_facecolor(BG_COLOR)
ax.set_facecolor(PANEL_COLOR)

# We'll place bars at y = 0, 1, 2, … (top of list = y=0 after invert).
y_positions = list(range(TOP_N))
bar_height  = 0.68

for rank_idx, (pid, segments) in enumerate(zip(ranked_pids, chart_rows)):
    y       = y_positions[rank_idx]
    x_left  = 0.0        # running left edge of each stacked segment

    for username, pts in segments:
        color = TEAM_COLORS.get(username, "#888888")
        bar = ax.barh(
            y,
            pts,
            left=x_left,
            height=bar_height,
            color=color,
            edgecolor=PANEL_COLOR,
            linewidth=0.4,
            zorder=3,
        )

        # Write team name inside bar segment if wide enough.
        seg_width_pts = pts  # data units
        # Estimate how many characters fit: each char ~120 pts wide at this scale
        # We use a relative threshold instead of pixel math.
        team_label = TEAM_NAMES.get(username, username)
        total_bar  = total_pts[pid]
        frac       = seg_width_pts / total_bar if total_bar else 0

        if frac > 0.08:          # segment is at least 8% of total bar
            # Truncate label to roughly fit the fraction of bar width.
            max_chars  = max(1, int(frac * 28))
            if len(team_label) > max_chars:
                team_label = team_label[: max(1, max_chars - 1)] + "."
            ax.text(
                x_left + seg_width_pts / 2,
                y,
                team_label,
                va="center",
                ha="center",
                fontsize=6.8,
                color="white",
                fontweight="bold",
                zorder=5,
                path_effects=[
                    pe.Stroke(linewidth=1.8, foreground="black"),
                    pe.Normal(),
                ],
            )

        x_left += pts

    # Total points label at the right end of the full bar.
    ax.text(
        x_left + total_pts[pid] * 0.008,
        y,
        f"{total_pts[pid]:,.0f}",
        va="center",
        ha="left",
        fontsize=8.5,
        color="#dddddd",
        zorder=5,
    )

# ── Y-axis labels: "PlayerName  (age XX)" ─────────────────────────────────────
y_labels: list[str] = []
for pid in ranked_pids:
    name = player_name.get(pid, f"ID:{pid}")
    age  = player_age_map.get(pid)
    label = f"{name}  (age {age})" if age is not None else name
    y_labels.append(label)

ax.set_yticks(y_positions)
ax.set_yticklabels(y_labels, fontsize=9, color="#e0e0e0")
ax.invert_yaxis()   # rank 1 at the top

# ── Rank badges on the left (#1, #2, …) ──────────────────────────────────────
# We draw them as FancyBboxPatch objects overlaid to the left of the axis.
ax.set_xlim(left=0)  # ensure we know where x=0 is
for rank_idx, y in enumerate(y_positions):
    badge_text = f"#{rank_idx + 1}"
    ax.text(
        -total_pts[ranked_pids[0]] * 0.025,   # slight left of x=0
        y,
        badge_text,
        va="center",
        ha="right",
        fontsize=7.5,
        color="#bbbbbb",
        fontweight="bold",
        zorder=6,
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="#2a2d3a",
            edgecolor="#444860",
            linewidth=0.8,
        ),
    )

# ── Grid, spines, ticks ───────────────────────────────────────────────────────
ax.xaxis.grid(True, color=GRID_COLOR, linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.tick_params(axis="x", colors="#666666", labelsize=8)
ax.tick_params(axis="y", length=0)
ax.xaxis.set_tick_params(labelcolor="#777777")

# ── Legend ────────────────────────────────────────────────────────────────────
legend_handles = [
    mpatches.Patch(
        color=TEAM_COLORS.get(u, "#888888"),
        label=TEAM_NAMES.get(u, u),
    )
    for u in legend_users
]
ax.legend(
    handles=legend_handles,
    loc="lower right",
    fontsize=8,
    framealpha=0.35,
    facecolor="#1a1d26",
    edgecolor="#444860",
    labelcolor="#dddddd",
    ncol=2,
    handlelength=1.2,
    handleheight=0.9,
)

# ── Title ─────────────────────────────────────────────────────────────────────
fig.suptitle(
    "In House Studs — All-Time Top Players by Starter Points (2022-2025)",
    fontsize=15,
    fontweight="bold",
    color="white",
    y=1.005,
)

# ── Save ──────────────────────────────────────────────────────────────────────
plt.tight_layout(pad=1.8)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_ranked.png")
plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
print(f"Saved → {out_path}")
plt.close()
