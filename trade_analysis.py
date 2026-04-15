"""
trade_analysis.py
-----------------
2026 Rookie Draft Trade Analysis: Pick #4 vs Picks #9 + #10

Fetches historical fantasy data from the Sleeper API to:
  1. Compute total fantasy points per player per team per season (2023-2025)
  2. Map each rookie draft pick slot to the total fantasy points that player
     produced in their first season as a starter
  3. Build a pick value curve (mean + std dev for pick slots 1-10)
  4. Compare the trade: pick #4 vs picks #9 + #10
  5. Fetch current rosters for Ju1ius and MattBlake and compute age distributions
  6. Output a 3-panel dark-themed chart saved to trade_analysis.png

Run with:
  uv run --with requests --with matplotlib --with numpy --with pandas trade_analysis.py
"""

import os
import sys
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict
from datetime import datetime

# ── Constants ──────────────────────────────────────────────────────────────────

BASE_URL = "https://api.sleeper.app/v1"

# League and draft IDs by season
LEAGUES = {
    "2023": {
        "league_id": "981579242393636864",
        "draft_id":  "981579242393636865",
    },
    "2024": {
        "league_id": "1145596058320506880",
        "draft_id":  "1145596058320506881",
    },
    "2025": {
        "league_id": "1219479299124371456",
        "draft_id":  "1219479299132768256",
    },
}

# Current (2025) league used for roster fetching
CURRENT_LEAGUE_ID = "1219479299124371456"

# Roster ID → display name mapping (consistent across all seasons)
ROSTER_MAP = {
    1:  "Ju1ius",
    2:  "ISTOLL21",
    3:  "MattBlake",
    4:  "joshstoll9",
    5:  "blockadamd00",
    6:  "fastillo15",
    7:  "JeremyW",          # 2023 name; morgannakonechny in 2024-25
    8:  "ryrythejedi",
    9:  "Hamiltontp",
    10: "Larz00",
}

# Teams involved in the trade
TEAM_COLORS = {
    "Ju1ius":   "#E63946",
    "MattBlake": "#FF9800",
}

# Dark-theme palette
BG_COLOR    = "#0f1117"
PANEL_COLOR = "#1a1d26"
GRID_COLOR  = "#2e3140"
TEXT_COLOR  = "white"
MUTED_COLOR = "#aaaaaa"

# Pick slots to model
PICK_SLOTS = list(range(1, 11))  # 1 through 10

# ── Helper: API fetch with error handling ──────────────────────────────────────

def fetch(endpoint: str) -> dict | list:
    """GET {BASE_URL}/{endpoint} and return parsed JSON."""
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Step 1: Compute fantasy points per player per team per season ──────────────

def get_starter_points_by_season() -> dict[str, dict[str, dict[str, float]]]:
    """
    Returns:
        {season: {roster_id_str: {player_id: total_starter_pts}}}
    Only counts points when the player was in the starting lineup.
    """
    season_data: dict[str, dict[str, dict[str, float]]] = {}

    for season, ids in LEAGUES.items():
        print(f"  Fetching matchup data for {season}...")
        league_id = ids["league_id"]

        league_meta = fetch(f"league/{league_id}")
        last_week   = league_meta["settings"].get("last_scored_leg", 0)

        # roster_id (int) → {player_id: cumulative starter pts}
        roster_pts: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for week in range(1, last_week + 1):
            matchups = fetch(f"league/{league_id}/matchups/{week}")
            for team in matchups:
                rid = team["roster_id"]
                players_points = team.get("players_points", {})
                for pid in team.get("starters", []):
                    roster_pts[rid][pid] += players_points.get(pid, 0.0)

        season_data[season] = {str(rid): dict(pts) for rid, pts in roster_pts.items()}

    return season_data


# ── Step 2: Fetch draft picks and map slot → player_id ────────────────────────

def get_draft_slot_to_player() -> dict[str, dict[int, str]]:
    """
    Returns:
        {season: {pick_slot (1-based overall): player_id}}
    Pick slot is the overall pick number (e.g., slot 4 = 4th pick overall).
    """
    slot_map: dict[str, dict[int, str]] = {}

    for season, ids in LEAGUES.items():
        print(f"  Fetching draft picks for {season}...")
        draft_id = ids["draft_id"]
        picks    = fetch(f"draft/{draft_id}/picks")

        slot_to_player: dict[int, str] = {}
        for pick in picks:
            slot        = pick.get("pick_no")        # overall pick number
            player_id   = pick.get("player_id")
            if slot is not None and player_id:
                slot_to_player[int(slot)] = str(player_id)

        slot_map[season] = slot_to_player

    return slot_map


# ── Step 3: Map pick slot → starter points in rookie season ───────────────────

def build_pick_value_data(
    season_data:     dict[str, dict[str, dict[str, float]]],
    slot_to_player:  dict[str, dict[int, str]],
) -> pd.DataFrame:
    """
    For each draft pick in slots 1-10, find the total fantasy points that
    player scored as a starter in the season they were drafted.

    Returns a DataFrame with columns: [season, slot, player_id, points]
    """
    rows = []
    for season, slot_map in slot_to_player.items():
        roster_pts = season_data.get(season, {})

        # Flatten all rosters into {player_id: total_pts} for that season
        all_pts: dict[str, float] = {}
        for rid_pts in roster_pts.values():
            for pid, pts in rid_pts.items():
                all_pts[pid] = all_pts.get(pid, 0.0) + pts

        for slot in PICK_SLOTS:
            player_id = slot_map.get(slot)
            if player_id is None:
                continue
            pts = all_pts.get(player_id, 0.0)
            rows.append({
                "season":    season,
                "slot":      slot,
                "player_id": player_id,
                "points":    pts,
            })

    return pd.DataFrame(rows)


# ── Step 4: Build pick value curve (mean + std per slot) ──────────────────────

def build_pick_curve(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate pick_value_df by slot, computing mean and std dev of points.

    Returns DataFrame with columns: [slot, mean, std, count]
    """
    curve = (
        df.groupby("slot")["points"]
        .agg(mean="mean", std="std", count="count")
        .reset_index()
    )
    curve["std"] = curve["std"].fillna(0.0)
    return curve


# ── Step 5: Fetch player metadata (name + birth_date) ─────────────────────────

def fetch_player_metadata() -> dict[str, dict]:
    """
    Returns {player_id: {"name": str, "birth_date": str or None, "age": int or None}}
    """
    print("  Fetching NBA player metadata...")
    players = fetch("players/nba")

    meta = {}
    today = datetime.today()
    for pid, p in players.items():
        full_name = (
            p.get("full_name")
            or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        )
        birth_date_str = p.get("birth_date")  # "YYYY-MM-DD" or None
        age = None
        if birth_date_str:
            try:
                bd  = datetime.strptime(birth_date_str, "%Y-%m-%d")
                age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            except ValueError:
                pass
        meta[str(pid)] = {"name": full_name, "birth_date": birth_date_str, "age": age}

    return meta


# ── Step 6: Fetch current rosters and compute age distributions ───────────────

def fetch_roster_ages(
    player_meta: dict[str, dict],
) -> dict[str, list[int]]:
    """
    Fetches rosters for roster_id=1 (Ju1ius) and roster_id=3 (MattBlake)
    from the current league, then returns {team_name: [age, age, ...]}
    for all rostered players with known ages.
    """
    print("  Fetching current rosters...")
    rosters_raw = fetch(f"league/{CURRENT_LEAGUE_ID}/rosters")

    target_roster_ids = {1: "Ju1ius", 3: "MattBlake"}
    team_ages: dict[str, list[int]] = {}

    for r in rosters_raw:
        rid = r["roster_id"]
        if rid not in target_roster_ids:
            continue
        team_name = target_roster_ids[rid]
        player_ids = (r.get("players") or []) + (r.get("reserve") or [])
        ages = []
        for pid in player_ids:
            age = player_meta.get(str(pid), {}).get("age")
            if age is not None:
                ages.append(age)
        team_ages[team_name] = ages

    return team_ages


# ── Step 7: Compute trade value numbers ───────────────────────────────────────

def compute_trade_values(curve: pd.DataFrame) -> dict:
    """
    Returns a dict with:
      pick4_mean, pick4_std,
      pick9_mean, pick9_std,
      pick10_mean, pick10_std,
      combined_mean, combined_std,
      advantage (positive = pick4 side wins)
    """
    def get_row(slot):
        row = curve[curve["slot"] == slot]
        if row.empty:
            return 0.0, 0.0
        return float(row["mean"].iloc[0]), float(row["std"].iloc[0])

    p4_mean,  p4_std  = get_row(4)
    p9_mean,  p9_std  = get_row(9)
    p10_mean, p10_std = get_row(10)

    # Combined value of picks 9+10 (means add, variances add assuming independence)
    combined_mean = p9_mean + p10_mean
    combined_std  = np.sqrt(p9_std**2 + p10_std**2)

    return {
        "pick4_mean":    p4_mean,
        "pick4_std":     p4_std,
        "pick9_mean":    p9_mean,
        "pick9_std":     p9_std,
        "pick10_mean":   p10_mean,
        "pick10_std":    p10_std,
        "combined_mean": combined_mean,
        "combined_std":  combined_std,
        "advantage":     p4_mean - combined_mean,
    }


# ── Step 8: Generate 3-panel dark-themed chart ────────────────────────────────

def plot_trade_analysis(
    curve:        pd.DataFrame,
    pick_vals:    pd.DataFrame,
    trade_vals:   dict,
    team_ages:    dict[str, list[int]],
    player_meta:  dict[str, dict],
    slot_to_player: dict[str, dict[int, str]],
    output_path:  str,
):
    """
    Three-panel figure:
      Panel 1 (top-left):  Pick value curve with error bands, highlighting picks 4, 9, 10
      Panel 2 (top-right): Trade comparison bar chart (pick 4 vs 9+10)
      Panel 3 (bottom):    Age distribution histograms for Ju1ius and MattBlake
    """
    fig = plt.figure(figsize=(18, 12), facecolor=BG_COLOR)
    gs  = fig.add_gridspec(2, 2, hspace=0.45, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])   # pick value curve
    ax2 = fig.add_subplot(gs[0, 1])   # trade comparison
    ax3 = fig.add_subplot(gs[1, :])   # age distribution (full width)

    highlight_slots  = {4: TEAM_COLORS["Ju1ius"], 9: TEAM_COLORS["MattBlake"], 10: TEAM_COLORS["MattBlake"]}
    neutral_color    = "#4a90d9"
    band_alpha       = 0.15

    # ── Panel 1: Pick Value Curve ──────────────────────────────────────────────
    ax1.set_facecolor(PANEL_COLOR)
    slots = curve["slot"].values
    means = curve["mean"].values
    stds  = curve["std"].values

    # Error band
    ax1.fill_between(slots, means - stds, means + stds,
                     alpha=band_alpha, color=neutral_color, label="±1 SD")

    # Main line
    ax1.plot(slots, means, color=neutral_color, linewidth=2, zorder=3, label="Mean pts")

    # Highlight individual data points
    for _, row in pick_vals.iterrows():
        s = int(row["slot"])
        ax1.scatter(s, row["points"], alpha=0.4,
                    color=highlight_slots.get(s, MUTED_COLOR),
                    s=30, zorder=4)

    # Highlight the three key picks
    for slot, color in highlight_slots.items():
        row = curve[curve["slot"] == slot]
        if not row.empty:
            mean_val = float(row["mean"].iloc[0])
            ax1.scatter(slot, mean_val, color=color, s=100, zorder=5,
                        edgecolors="white", linewidths=0.8)
            label = f"#{slot}\n({mean_val:,.0f})"
            ax1.annotate(label, xy=(slot, mean_val),
                         xytext=(slot + 0.3, mean_val + stds[slot - 1] * 0.5 + 50),
                         color=color, fontsize=8, fontweight="bold",
                         ha="left")

    ax1.set_xticks(PICK_SLOTS)
    ax1.set_xlabel("Pick Slot (Overall)", color=MUTED_COLOR, fontsize=9)
    ax1.set_ylabel("Starter Fantasy Points (Rookie Season)", color=MUTED_COLOR, fontsize=9)
    ax1.set_title("Pick Value Curve — 2023-2025 Rookie Drafts", color=TEXT_COLOR,
                  fontsize=11, fontweight="bold", pad=10)
    ax1.tick_params(colors=MUTED_COLOR, labelsize=8)
    ax1.grid(True, color=GRID_COLOR, linewidth=0.6)
    ax1.set_facecolor(PANEL_COLOR)
    for spine in ax1.spines.values():
        spine.set_color(GRID_COLOR)

    legend = ax1.legend(fontsize=8, facecolor=PANEL_COLOR, edgecolor=GRID_COLOR,
                        labelcolor=TEXT_COLOR)

    # ── Panel 2: Trade Comparison ──────────────────────────────────────────────
    ax2.set_facecolor(PANEL_COLOR)

    trade_labels  = ["Pick #4\n(Ju1ius gives)", "Picks #9+#10\n(MattBlake gives)"]
    trade_means   = [trade_vals["pick4_mean"], trade_vals["combined_mean"]]
    trade_stds    = [trade_vals["pick4_std"],  trade_vals["combined_std"]]
    trade_colors  = [TEAM_COLORS["Ju1ius"],    TEAM_COLORS["MattBlake"]]

    bars = ax2.bar(
        trade_labels, trade_means,
        color=trade_colors, alpha=0.85,
        edgecolor="white", linewidth=0.6,
        width=0.45, zorder=3,
    )
    ax2.errorbar(
        trade_labels, trade_means, yerr=trade_stds,
        fmt="none", color="white", capsize=6, linewidth=1.5, zorder=4,
    )

    for bar, mean_val, std_val in zip(bars, trade_means, trade_stds):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            mean_val + std_val + 30,
            f"{mean_val:,.0f}",
            ha="center", va="bottom", color=TEXT_COLOR,
            fontsize=11, fontweight="bold",
        )

    adv = trade_vals["advantage"]
    adv_color = TEAM_COLORS["Ju1ius"] if adv > 0 else TEAM_COLORS["MattBlake"]
    adv_label = (
        f"Pick #4 advantage: +{adv:,.0f} pts"
        if adv >= 0
        else f"Picks #9+#10 advantage: +{-adv:,.0f} pts"
    )
    ax2.set_title("Trade Value Comparison", color=TEXT_COLOR, fontsize=11,
                  fontweight="bold", pad=10)
    ax2.set_ylabel("Expected Starter Points (Rookie Season)", color=MUTED_COLOR, fontsize=9)
    ax2.tick_params(colors=MUTED_COLOR, labelsize=9)
    ax2.grid(axis="y", color=GRID_COLOR, linewidth=0.6, zorder=0)
    ax2.set_axisbelow(True)
    for spine in ax2.spines.values():
        spine.set_color(GRID_COLOR)

    # Advantage annotation
    y_top = max(trade_means) + max(trade_stds) + 120
    ax2.annotate(
        adv_label,
        xy=(0.5, 0.97), xycoords="axes fraction",
        ha="center", va="top",
        color=adv_color, fontsize=9, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=PANEL_COLOR,
                  edgecolor=adv_color, linewidth=1.2),
    )

    # ── Panel 3: Age Distributions ────────────────────────────────────────────
    ax3.set_facecolor(PANEL_COLOR)

    bin_min  = 18
    bin_max  = 40
    bins     = list(range(bin_min, bin_max + 2))
    bar_w    = 0.4
    teams    = ["Ju1ius", "MattBlake"]
    offsets  = [-bar_w / 2, bar_w / 2]

    all_ages = []
    for t in teams:
        all_ages.extend(team_ages.get(t, []))
    unique_ages = sorted(set(all_ages))

    for team, offset in zip(teams, offsets):
        ages   = team_ages.get(team, [])
        color  = TEAM_COLORS[team]
        counts = {age: ages.count(age) for age in unique_ages}
        xs = [a + offset for a in unique_ages]
        ys = [counts.get(a, 0) for a in unique_ages]

        bars_age = ax3.bar(xs, ys, width=bar_w, color=color,
                           alpha=0.85, label=f"{team} (n={len(ages)})",
                           zorder=3, edgecolor="white", linewidth=0.4)

        # Count labels on bars
        for b, y in zip(bars_age, ys):
            if y > 0:
                ax3.text(b.get_x() + b.get_width() / 2, y + 0.05,
                         str(y), ha="center", va="bottom",
                         color=color, fontsize=7.5, fontweight="bold")

    # Median age lines
    for team in teams:
        ages = team_ages.get(team, [])
        if ages:
            med = float(np.median(ages))
            ax3.axvline(med, color=TEAM_COLORS[team], linestyle="--",
                        linewidth=1.4, alpha=0.7,
                        label=f"{team} median: {med:.1f}")

    ax3.set_xticks(unique_ages)
    ax3.set_xlabel("Player Age", color=MUTED_COLOR, fontsize=9)
    ax3.set_ylabel("Number of Players", color=MUTED_COLOR, fontsize=9)
    ax3.set_title("Roster Age Distribution — Ju1ius vs MattBlake (2025 Season)",
                  color=TEXT_COLOR, fontsize=11, fontweight="bold", pad=10)
    ax3.tick_params(colors=MUTED_COLOR, labelsize=8)
    ax3.grid(axis="y", color=GRID_COLOR, linewidth=0.6, zorder=0)
    ax3.set_axisbelow(True)
    for spine in ax3.spines.values():
        spine.set_color(GRID_COLOR)

    legend3 = ax3.legend(fontsize=8.5, facecolor=PANEL_COLOR,
                         edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR,
                         loc="upper right")

    # ── Super-title ────────────────────────────────────────────────────────────
    fig.suptitle(
        "2026 Draft Trade Analysis — Pick #4 (Ju1ius) vs Picks #9+#10 (MattBlake)",
        fontsize=15, fontweight="bold", color=TEXT_COLOR, y=1.01,
    )

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    print(f"  Chart saved to: {output_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "trade_analysis.png")

    print("\n=== 2026 Draft Trade Analysis ===\n")

    # --- Step 1: Matchup data ---
    print("[1/6] Fetching matchup data (starter points per player)...")
    season_data = get_starter_points_by_season()

    # --- Step 2: Draft picks ---
    print("[2/6] Fetching rookie draft picks...")
    slot_to_player = get_draft_slot_to_player()

    # --- Step 3: Build pick value DataFrame ---
    print("[3/6] Building pick value data...")
    pick_vals = build_pick_value_data(season_data, slot_to_player)
    print(f"      {len(pick_vals)} pick-slot observations across {len(LEAGUES)} drafts")

    # --- Step 4: Pick value curve ---
    print("[4/6] Computing pick value curve...")
    curve = build_pick_curve(pick_vals)
    print("\n  Pick Value Curve (mean ± std):")
    print("  {:>6}  {:>10}  {:>10}  {:>6}".format("Slot", "Mean", "Std", "n"))
    print("  " + "-" * 38)
    for _, row in curve.iterrows():
        print("  {:>6}  {:>10,.0f}  {:>10,.0f}  {:>6}".format(
            int(row["slot"]), row["mean"], row["std"], int(row["count"])))

    trade_vals = compute_trade_values(curve)
    print(f"\n  Trade Summary:")
    print(f"    Pick #4     → {trade_vals['pick4_mean']:,.0f} pts (±{trade_vals['pick4_std']:,.0f})")
    print(f"    Picks #9+10 → {trade_vals['combined_mean']:,.0f} pts (±{trade_vals['combined_std']:,.0f})")
    adv = trade_vals["advantage"]
    if adv > 0:
        print(f"    Pick #4 is worth +{adv:,.0f} pts MORE than the combined #9+#10")
    else:
        print(f"    Picks #9+#10 combined are worth +{-adv:,.0f} pts MORE than pick #4")

    # --- Step 5: Player metadata + ages ---
    print("\n[5/6] Fetching player metadata and roster ages...")
    player_meta = fetch_player_metadata()
    team_ages   = fetch_roster_ages(player_meta)

    for team, ages in team_ages.items():
        if ages:
            print(f"    {team}: {len(ages)} players, "
                  f"median age {np.median(ages):.1f}, "
                  f"range {min(ages)}-{max(ages)}")
        else:
            print(f"    {team}: no age data found")

    # --- Step 6: Generate chart ---
    print("\n[6/6] Generating 3-panel trade analysis chart...")
    plot_trade_analysis(
        curve=curve,
        pick_vals=pick_vals,
        trade_vals=trade_vals,
        team_ages=team_ages,
        player_meta=player_meta,
        slot_to_player=slot_to_player,
        output_path=output_path,
    )

    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
