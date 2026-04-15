"""
draft_analysis.py
-----------------
In House Studs — Rookie Draft Picks by Player (2023–2025)

Produces a tall horizontal bar chart with one row per drafted player (all 90
picks, 30 per season across three drafts).  Each row shows two bars:
  • Solid bar  (alpha=0.9) → starter_pts (points when player was in starters list)
  • Ghost bar  (alpha=0.4) → total_pts   (all points from players_points dict)

Rows are sorted by round (R1 at top, R3 at bottom), then by total_pts
descending within each round.  Section dividers label each round and annotate
the round average.

Run with:
  uv run --with requests --with matplotlib --with pandas python3 draft_analysis.py
"""

import os
import sys
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict

# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL = "https://api.sleeper.app/v1"

# Season configurations: league_id, draft_id, number of weeks
SEASONS = {
    "2023": {
        "league_id": "981579242393636864",
        "draft_id":  "981579242393636865",
        "weeks":     25,
    },
    "2024": {
        "league_id": "1145596058320506880",
        "draft_id":  "1145596058320506881",
        "weeks":     24,
    },
    "2025": {
        "league_id": "1219479299124371456",
        "draft_id":  "1219479299132768256",
        "weeks":     24,
    },
}

# Roster ID → username mapping (consistent across all three seasons).
# Roster 7 changed display name between 2023 and 2024.
ROSTER_MAP = {
    1:  "Ju1ius",
    2:  "ISTOLL21",
    3:  "MattBlake",
    4:  "joshstoll9",
    5:  "blockadamd00",
    6:  "fastillo15",
    7:  "JeremyW",          # 2023 name; becomes morgannakonechny in 2024-25
    8:  "ryrythejedi",
    9:  "Hamiltontp",
    10: "Larz00",
}

# Username overrides per season for roster 7
ROSTER_7_BY_SEASON = {
    "2023": "JeremyW",
    "2024": "morgannakonechny",
    "2025": "morgannakonechny",
}

# Hex colour per username (JeremyW and morgannakonechny share the same colour)
TEAM_COLORS = {
    "Ju1ius":           "#E63946",
    "ISTOLL21":         "#2196F3",
    "MattBlake":        "#FF9800",
    "joshstoll9":       "#9C27B0",
    "blockadamd00":     "#4CAF50",
    "fastillo15":       "#00BCD4",
    "morgannakonechny": "#F06292",
    "JeremyW":          "#F06292",
    "ryrythejedi":      "#8BC34A",
    "Hamiltontp":       "#FF5722",
    "Larz00":           "#607D8B",
}

# Dark-theme palette
BG_COLOR    = "#0f1117"
PANEL_COLOR = "#1a1d26"
GRID_COLOR  = "#2e3140"
TEXT_COLOR  = "white"
MUTED_COLOR = "#aaaaaa"


# ── Helper ─────────────────────────────────────────────────────────────────────

def fetch(endpoint: str):
    """GET {BASE_URL}/{endpoint} and return parsed JSON."""
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ── Step 1: Accumulate starter_pts and total_pts per (season, roster_id, player_id) ──

def collect_season_points() -> dict:
    """
    Returns nested dict:
        {season: {roster_id (int): {player_id: {"starter": float, "total": float}}}}

    For every week/team:
      - total_pts  += players_points[player_id]   for every player on the roster
      - starter_pts += players_points[player_id]  only if player_id is in starters[]
    """
    season_pts = {}

    for season, cfg in SEASONS.items():
        print(f"  [{season}] Fetching matchup data ({cfg['weeks']} weeks)...")
        league_id = cfg["league_id"]

        # roster_id → {player_id → {"starter": float, "total": float}}
        roster_data: dict[int, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"starter": 0.0, "total": 0.0})
        )

        for week in range(1, cfg["weeks"] + 1):
            matchups = fetch(f"league/{league_id}/matchups/{week}")
            for team in matchups:
                rid            = team["roster_id"]
                players_points = team.get("players_points") or {}
                starters_set   = set(team.get("starters") or [])

                for pid, pts in players_points.items():
                    roster_data[rid][pid]["total"] += pts
                    if pid in starters_set:
                        roster_data[rid][pid]["starter"] += pts

        # Convert nested defaultdicts to plain dicts for storage
        season_pts[season] = {rid: dict(pid_map) for rid, pid_map in roster_data.items()}

    return season_pts


# ── Step 2: Fetch draft picks ──────────────────────────────────────────────────

def collect_draft_picks() -> list[dict]:
    """
    Returns a list of dicts, one per non-keeper pick, with keys:
        season, round, pick_no, roster_id, player_id
    """
    all_picks = []

    for season, cfg in SEASONS.items():
        print(f"  [{season}] Fetching draft picks...")
        draft_id = cfg["draft_id"]
        picks    = fetch(f"draft/{draft_id}/picks")

        for pick in picks:
            # Skip keeper picks (is_keeper is True or "true")
            if pick.get("is_keeper"):
                continue
            player_id = pick.get("player_id")
            roster_id = pick.get("roster_id")    # roster_id of the team that made the pick
            round_num = pick.get("round")
            pick_no   = pick.get("pick_no")      # overall pick number (1-based)
            if player_id and roster_id and round_num:
                all_picks.append({
                    "season":    season,
                    "round":     int(round_num),
                    "pick_no":   int(pick_no) if pick_no else None,
                    "roster_id": int(roster_id),
                    "player_id": str(player_id),
                })

    return all_picks


# ── Step 3: Fetch player names ─────────────────────────────────────────────────

def fetch_player_names() -> dict[str, str]:
    """Returns {player_id: full_name}."""
    print("  Fetching NBA player names...")
    players = fetch("players/nba")
    names = {}
    for pid, p in players.items():
        full = (
            p.get("full_name")
            or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        )
        names[str(pid)] = full or f"ID:{pid}"
    return names


# ── Step 4: Build the chart DataFrame ─────────────────────────────────────────

def build_chart_df(
    picks:       list[dict],
    season_pts:  dict,
    player_names: dict[str, str],
) -> pd.DataFrame:
    """
    Joins picks with point totals and returns a DataFrame with columns:
        season, round, pick_no, roster_id, username, player_id,
        player_name, starter_pts, total_pts
    """
    rows = []

    for pick in picks:
        season    = pick["season"]
        roster_id = pick["roster_id"]
        player_id = pick["player_id"]

        # Resolve username, accounting for the roster-7 rename
        if roster_id == 7:
            username = ROSTER_7_BY_SEASON.get(season, "JeremyW")
        else:
            username = ROSTER_MAP.get(roster_id, f"roster_{roster_id}")

        # Look up that team's point accumulation for this player in this season
        player_map = season_pts.get(season, {}).get(roster_id, {})
        pts_entry  = player_map.get(player_id, {"starter": 0.0, "total": 0.0})

        rows.append({
            "season":      season,
            "round":       pick["round"],
            "pick_no":     pick["pick_no"],
            "roster_id":   roster_id,
            "username":    username,
            "player_id":   player_id,
            "player_name": player_names.get(player_id, f"ID:{player_id}"),
            "starter_pts": pts_entry["starter"],
            "total_pts":   pts_entry["total"],
        })

    df = pd.DataFrame(rows)

    # Sort: round ascending, then total_pts descending within each round
    df = df.sort_values(["round", "total_pts"], ascending=[True, False])
    df = df.reset_index(drop=True)

    return df


# ── Step 5: Plot ───────────────────────────────────────────────────────────────

def plot_draft_chart(df: pd.DataFrame, output_path: str):
    """
    Draws the tall horizontal bar chart and saves it to output_path.

    Layout:
      • One row per pick (all 90 rows)
      • Section dividers between rounds with header + average annotation
      • Two bars per row: ghost (total_pts) and solid (starter_pts)
      • Y-tick label: "PlayerName (R{round}, {season}) — username"
      • Team legend in top-right corner
    """
    n_rows  = len(df)
    fig_h   = 38
    fig_w   = 16

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(PANEL_COLOR)

    # ── Draw bars ──────────────────────────────────────────────────────────────
    y_positions = list(range(n_rows))   # 0 = top row in data order (R1 best)

    for i, row in df.iterrows():
        y      = i  # row index maps directly to y position
        color  = TEAM_COLORS.get(row["username"], "#888888")

        # Ghost bar: total_pts (semi-transparent, full width)
        ax.barh(y, row["total_pts"],
                color=color, alpha=0.4, height=0.72, left=0, zorder=2)

        # Solid bar: starter_pts (opaque, inner)
        ax.barh(y, row["starter_pts"],
                color=color, alpha=0.9, height=0.72, left=0, zorder=3)

    # ── Y-tick labels ─────────────────────────────────────────────────────────
    y_labels = [
        f"{row['player_name']} (R{row['round']}, {row['season']}) — {row['username']}"
        for _, row in df.iterrows()
    ]
    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=7.8, color=TEXT_COLOR)

    # Invert so R1 top-pick is at the top of the chart
    ax.invert_yaxis()

    # ── Round dividers and headers ────────────────────────────────────────────
    # We need to identify the boundary between rounds.
    # Because df is sorted round asc, find the first index of each new round.
    round_groups = df.groupby("round", sort=True)

    for round_num, grp in round_groups:
        first_idx = grp.index[0]
        last_idx  = grp.index[-1]

        # Divider line just above the first row of the round
        divider_y = first_idx - 0.5
        ax.axhline(divider_y, color="#444a5a", linewidth=1.4, zorder=5)

        # Round header: centred label slightly above divider
        avg_total   = grp["total_pts"].mean()
        avg_starter = grp["starter_pts"].mean()

        header_text = (
            f"── Round {round_num} ──   "
            f"avg total: {avg_total:,.0f} pts   avg starter: {avg_starter:,.0f} pts"
        )
        # Place the label at the divider y, just to the left of the chart
        ax.text(
            -15,                   # slightly left of x=0
            divider_y,
            header_text,
            va="bottom", ha="left",
            fontsize=9, fontweight="bold",
            color="#cccccc", zorder=6,
        )

    # ── Axes formatting ────────────────────────────────────────────────────────
    ax.set_xlabel("Fantasy Points", color=MUTED_COLOR, fontsize=11)
    ax.tick_params(axis="x", colors=MUTED_COLOR, labelsize=9)
    ax.tick_params(axis="y", colors=TEXT_COLOR,  labelsize=7.8, length=0)

    ax.xaxis.grid(True, color=GRID_COLOR, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)

    # Reasonable x-axis upper bound with a little breathing room
    max_pts = df["total_pts"].max()
    ax.set_xlim(-80, max_pts * 1.12)

    # ── Title ─────────────────────────────────────────────────────────────────
    fig.suptitle(
        "In House Studs — Rookie Draft Picks by Player (2023–2025)\n"
        "Solid bar = starter pts  |  Transparent bar = total pts",
        fontsize=14, fontweight="bold", color=TEXT_COLOR,
        y=1.004,
    )

    # ── Team legend ───────────────────────────────────────────────────────────
    # Build one legend handle per unique username that appears in the data
    seen_users = df["username"].unique()
    legend_handles = []
    for user in sorted(seen_users, key=lambda u: u.lower()):
        color  = TEAM_COLORS.get(user, "#888888")
        patch  = mpatches.Patch(facecolor=color, label=user, alpha=0.85)
        legend_handles.append(patch)

    legend = ax.legend(
        handles=legend_handles,
        loc="upper right",
        fontsize=8,
        facecolor=PANEL_COLOR,
        edgecolor=GRID_COLOR,
        labelcolor=TEXT_COLOR,
        framealpha=0.9,
        title="Teams",
        title_fontsize=8.5,
    )
    legend.get_title().set_color(MUTED_COLOR)

    # ── Save ──────────────────────────────────────────────────────────────────
    plt.tight_layout(pad=2.0)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    print(f"  Chart saved → {output_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "draft_analysis.png")

    print("\n=== Rookie Draft Picks by Player (2023–2025) ===\n")

    # Step 1: Matchup data
    print("[1/4] Collecting starter + total points per player per team per season...")
    season_pts = collect_season_points()

    # Step 2: Draft picks
    print("\n[2/4] Fetching draft picks...")
    picks = collect_draft_picks()
    print(f"      {len(picks)} non-keeper picks loaded")

    # Step 3: Player names
    print("\n[3/4] Fetching player names...")
    player_names = fetch_player_names()

    # Step 4: Build DataFrame + plot
    print("\n[4/4] Building chart data and plotting...")
    df = build_chart_df(picks, season_pts, player_names)

    # Print a summary table to stdout
    print(f"\n  {'Player':<28} {'Season':>6} {'Rnd':>3} {'Username':<20} "
          f"{'Starter':>8} {'Total':>8}")
    print("  " + "-" * 82)
    for _, row in df.iterrows():
        print(f"  {row['player_name']:<28} {row['season']:>6} {row['round']:>3}  "
              f"{row['username']:<20} {row['starter_pts']:>8,.0f} {row['total_pts']:>8,.0f}")

    plot_draft_chart(df, output_path)

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
