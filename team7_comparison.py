"""
team7_comparison.py
===================
"JeremyW vs morgannakonechny — Same Team, Different Eras"

Produces a multi-panel comparison chart for roster_id=7 across all 4 seasons
(2022-2025).  JeremyW managed in 2022-2023; morgannakonechny took over in
2024-2025.

Run with:
    uv run --with requests --with matplotlib --with numpy python3 team7_comparison.py

Output:  team7_comparison.png  (saved next to this script)
"""

import os
import sys
import requests
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL = "https://api.sleeper.app/v1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "team7_comparison.png")

# Roster ID we care about (same slot across all seasons)
TARGET_ROSTER_ID = 7

# Season definitions: (year_label, league_id, draft_id, total_weeks)
SEASONS = [
    ("2022", "819248226988314624",  "887431909352296448",  25),
    ("2023", "981579242393636864",  "981579242393636865",  25),
    ("2024", "1145596058320506880", "1145596058320506881", 24),
    ("2025", "1219479299124371456", "1219479299132768256", 24),
]

# Manager assignment: Jeremy ran 2022-2023, Morgan ran 2024-2025
JEREMY_YEARS  = {"2022", "2023"}
MORGAN_YEARS  = {"2024", "2025"}

JEREMY_NAME  = "JeremyW"
MORGAN_NAME  = "morgannakonechny"

JEREMY_COLOR = "#F06292"   # pink
MORGAN_COLOR = "#29B6F6"   # blue

# Dark theme palette
BG_COLOR    = "#0f1117"
PANEL_COLOR = "#1a1d26"
TEXT_COLOR  = "#e0e0e0"
DIM_COLOR   = "#777777"
GRID_COLOR  = "#2e3140"

# ── Helper: color by year ──────────────────────────────────────────────────────

def season_color(year: str) -> str:
    """Return the manager color for a given season year string."""
    return JEREMY_COLOR if year in JEREMY_YEARS else MORGAN_COLOR


def manager_for(year: str) -> str:
    """Return the manager display name for a given season year string."""
    return JEREMY_NAME if year in JEREMY_YEARS else MORGAN_NAME


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict | list:
    """GET a Sleeper API endpoint and return parsed JSON, with minimal error handling."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_roster7_owner(league_id: str) -> tuple[str, str]:
    """
    Return (owner_id, display_name) for roster_id=7 in the given league.
    Falls back to ('unknown', 'unknown') if not found.
    """
    users   = fetch_json(f"{BASE_URL}/league/{league_id}/users")
    rosters = fetch_json(f"{BASE_URL}/league/{league_id}/rosters")

    # Build owner_id → display_name map
    id_to_name = {u["user_id"]: u["display_name"] for u in users}

    for r in rosters:
        if r["roster_id"] == TARGET_ROSTER_ID:
            owner_id = r.get("owner_id", "unknown")
            return owner_id, id_to_name.get(owner_id, "unknown")

    return "unknown", "unknown"


def fetch_season_data(year: str, league_id: str, draft_id: str, total_weeks: int) -> dict:
    """
    Fetch everything we need for one season and return a structured dict:

    {
        "year":      str,
        "owner":     str,   # display name
        "wins":      int,
        "losses":    int,
        "ties":      int,
        "pf":        float,
        "pa":        float,
        "weekly":    list[float],   # actual scored weeks (non-zero)
        "playoff":   str | None,    # "winner" / "runner_up" / "appeared" / None
        "trades":    int,
        "picks":     list[dict],    # draft picks for roster 7
    }
    """
    print(f"  Fetching league {year} …")
    league  = fetch_json(f"{BASE_URL}/league/{league_id}")
    rosters = fetch_json(f"{BASE_URL}/league/{league_id}/rosters")
    users   = fetch_json(f"{BASE_URL}/league/{league_id}/users")

    id_to_name = {u["user_id"]: u["display_name"] for u in users}

    # Find roster 7
    roster7 = next((r for r in rosters if r["roster_id"] == TARGET_ROSTER_ID), None)
    if roster7 is None:
        raise ValueError(f"Roster {TARGET_ROSTER_ID} not found in league {league_id}")

    owner_id    = roster7.get("owner_id", "unknown")
    owner_name  = id_to_name.get(owner_id, "unknown")

    # Record from roster settings (Sleeper stores cumulative W/L/PF/PA there)
    settings = roster7.get("settings", {})
    wins    = settings.get("wins",   0)
    losses  = settings.get("losses", 0)
    ties    = settings.get("ties",   0)
    pf      = settings.get("fpts",   0) + settings.get("fpts_decimal", 0) / 100
    pa      = settings.get("fpts_against", 0) + settings.get("fpts_against_decimal", 0) / 100

    # Weekly scores — iterate all regular-season matchups
    weekly_scores: list[float] = []
    print(f"    Fetching matchups for {total_weeks} weeks …")
    for week in range(1, total_weeks + 1):
        matchups = fetch_json(f"{BASE_URL}/league/{league_id}/matchups/{week}")
        for m in matchups:
            if m["roster_id"] == TARGET_ROSTER_ID:
                pts = m.get("points", 0.0) or 0.0
                if pts > 0:
                    weekly_scores.append(float(pts))
                break

    # Playoff result — check winners bracket
    playoff_result = None
    try:
        brackets = fetch_json(f"{BASE_URL}/league/{league_id}/winners_bracket")
        # Find the highest-round match roster 7 appeared in
        r7_rounds: list[int] = []
        for match in brackets:
            if TARGET_ROSTER_ID in (match.get("t1"), match.get("t2")):
                r7_rounds.append(match.get("r", 0))
        if r7_rounds:
            playoff_result = "appeared"
            max_round = max(r7_rounds)
            # Check if they won the championship match (typically the final round)
            for match in brackets:
                if match.get("r") == max_round and match.get("w") == TARGET_ROSTER_ID:
                    playoff_result = "winner"
                    break
                elif match.get("r") == max_round and TARGET_ROSTER_ID in (match.get("t1"), match.get("t2")):
                    playoff_result = "runner_up"
    except Exception:
        pass  # Bracket data not available

    # Trade count for this roster
    trade_count = 0
    try:
        transactions = fetch_json(f"{BASE_URL}/league/{league_id}/transactions/1")
        # Transactions endpoint only returns one round at a time; aggregate across all weeks
        all_trades: list[dict] = []
        for wk in range(1, total_weeks + 1):
            txns = fetch_json(f"{BASE_URL}/league/{league_id}/transactions/{wk}")
            for t in txns:
                if t.get("type") == "trade":
                    roster_ids = t.get("roster_ids", [])
                    if TARGET_ROSTER_ID in roster_ids:
                        all_trades.append(t)
        # De-duplicate by transaction id
        seen = set()
        for t in all_trades:
            tid = t.get("transaction_id")
            if tid not in seen:
                seen.add(tid)
                trade_count += 1
    except Exception:
        pass

    # Draft picks for this roster
    picks: list[dict] = []
    try:
        draft_picks = fetch_json(f"{BASE_URL}/draft/{draft_id}/picks")
        picks = [p for p in draft_picks if p.get("roster_id") == TARGET_ROSTER_ID]
    except Exception:
        pass

    return {
        "year":    year,
        "owner":   owner_name,
        "wins":    wins,
        "losses":  losses,
        "ties":    ties,
        "pf":      pf,
        "pa":      pa,
        "weekly":  weekly_scores,
        "playoff": playoff_result,
        "trades":  trade_count,
        "picks":   picks,
    }


# ── Chart building ─────────────────────────────────────────────────────────────

def style_ax(ax: plt.Axes, title: str = "") -> None:
    """Apply the dark panel style to an axis."""
    ax.set_facecolor(PANEL_COLOR)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    if title:
        ax.set_title(title, color=TEXT_COLOR, fontsize=10, fontweight="bold", pad=8)
    ax.grid(color=GRID_COLOR, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def build_stat_card(ax: plt.Axes, label: str, values: list[float],
                    years: list[str], fmt: str = "{:.0f}") -> None:
    """
    Row 0 panels: horizontal bar per season colored by manager.
    `label` is the metric name (e.g., 'Wins').
    """
    colors = [season_color(y) for y in years]
    y_pos  = range(len(years))

    bars = ax.barh(list(y_pos), values, color=colors, height=0.55, zorder=3)

    # Value labels inside/outside the bars
    max_val = max(values) if values else 1
    for bar, val, yr in zip(bars, values, years):
        x_label = val + max_val * 0.02
        ax.text(x_label, bar.get_y() + bar.get_height() / 2,
                fmt.format(val),
                va="center", ha="left", fontsize=8, color=TEXT_COLOR)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(years, color=TEXT_COLOR, fontsize=9)
    ax.set_xlim(0, max_val * 1.25)
    ax.invert_yaxis()
    style_ax(ax, label)


def build_weekly_line(ax: plt.Axes, season_data: list[dict]) -> None:
    """
    Row 1 left: weekly scoring line chart.
    Each season is its own line; dashed horizontal lines show per-manager averages.
    """
    line_styles = ["-", "--", "-.", ":"]

    jeremy_scores: list[float] = []
    morgan_scores: list[float] = []

    for i, sd in enumerate(season_data):
        yr    = sd["year"]
        wkly  = sd["weekly"]
        color = season_color(yr)
        ls    = line_styles[i % len(line_styles)]
        ax.plot(range(1, len(wkly) + 1), wkly,
                color=color, linewidth=1.6, linestyle=ls,
                label=yr, zorder=3, marker="o", markersize=2.5)
        if yr in JEREMY_YEARS:
            jeremy_scores.extend(wkly)
        else:
            morgan_scores.extend(wkly)

    # Per-manager average dashed lines
    if jeremy_scores:
        j_avg = np.mean(jeremy_scores)
        ax.axhline(j_avg, color=JEREMY_COLOR, linestyle="--",
                   linewidth=1.2, alpha=0.7,
                   label=f"{JEREMY_NAME} avg ({j_avg:.1f})")
    if morgan_scores:
        m_avg = np.mean(morgan_scores)
        ax.axhline(m_avg, color=MORGAN_COLOR, linestyle="--",
                   linewidth=1.2, alpha=0.7,
                   label=f"{MORGAN_NAME} avg ({m_avg:.1f})")

    ax.set_xlabel("Week", color=TEXT_COLOR, fontsize=9)
    ax.set_ylabel("Points", color=TEXT_COLOR, fontsize=9)
    ax.legend(fontsize=7.5, facecolor=PANEL_COLOR, labelcolor=TEXT_COLOR,
              edgecolor=GRID_COLOR, loc="upper right")
    style_ax(ax, "Weekly Scoring — All Seasons")


def build_boxplots(ax: plt.Axes, season_data: list[dict]) -> None:
    """
    Row 1 right: one box per season colored by manager, with a vertical divider
    between Jeremy (2022-23) and Morgan (2024-25) eras.
    """
    all_data  = [sd["weekly"] for sd in season_data]
    years     = [sd["year"]   for sd in season_data]
    colors    = [season_color(y) for y in years]
    positions = list(range(1, len(years) + 1))

    bp = ax.boxplot(all_data, positions=positions, patch_artist=True,
                    widths=0.5,
                    medianprops={"color": "white", "linewidth": 2},
                    whiskerprops={"color": DIM_COLOR},
                    capprops={"color": DIM_COLOR},
                    flierprops={"markerfacecolor": DIM_COLOR,
                                "marker": "o", "markersize": 4})

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    # Era divider between pos 2 and 3
    ax.axvline(2.5, color="#555566", linewidth=1.5, linestyle="--", alpha=0.8)

    ax.set_xticks(positions)
    ax.set_xticklabels(years, color=TEXT_COLOR, fontsize=9)
    ax.set_ylabel("Points", color=TEXT_COLOR, fontsize=9)

    # Era labels at the top
    ax.text(1.5, ax.get_ylim()[1] if ax.get_ylim()[1] != 1.0 else 200,
            JEREMY_NAME, color=JEREMY_COLOR, fontsize=8,
            ha="center", va="bottom", fontweight="bold")
    ax.text(3.5, ax.get_ylim()[1] if ax.get_ylim()[1] != 1.0 else 200,
            MORGAN_NAME, color=MORGAN_COLOR, fontsize=8,
            ha="center", va="bottom", fontweight="bold")

    style_ax(ax, "Score Distribution by Season")


def build_pf_pa_scatter(ax: plt.Axes, season_data: list[dict]) -> None:
    """
    Row 2 left: PF vs PA scatter.  One dot per season, labeled by year.
    Diagonal 'break-even' line at PF==PA.
    """
    pf_vals = [sd["pf"] for sd in season_data]
    pa_vals = [sd["pa"] for sd in season_data]
    years   = [sd["year"] for sd in season_data]

    all_vals = pf_vals + pa_vals
    vmin = min(all_vals) * 0.97
    vmax = max(all_vals) * 1.03

    # Break-even diagonal
    ax.plot([vmin, vmax], [vmin, vmax],
            color=DIM_COLOR, linewidth=1.2, linestyle="--",
            alpha=0.6, label="Break even", zorder=2)

    for pf, pa, yr in zip(pf_vals, pa_vals, years):
        color = season_color(yr)
        ax.scatter(pa, pf, color=color, s=120, zorder=4)
        ax.annotate(yr, (pa, pf),
                    textcoords="offset points", xytext=(8, 4),
                    color=color, fontsize=9, fontweight="bold")

    ax.set_xlabel("Points Against (PA)", color=TEXT_COLOR, fontsize=9)
    ax.set_ylabel("Points For (PF)",     color=TEXT_COLOR, fontsize=9)
    ax.set_xlim(vmin, vmax)
    ax.set_ylim(vmin, vmax)
    ax.legend(fontsize=8, facecolor=PANEL_COLOR, labelcolor=TEXT_COLOR,
              edgecolor=GRID_COLOR)
    style_ax(ax, "PF vs PA by Season")


def build_wins_losses_bar(ax: plt.Axes, season_data: list[dict]) -> None:
    """
    Row 2 right: grouped bar chart — Wins (solid) and Losses (hatched) per season.
    Vertical divider between the two manager eras.
    """
    years    = [sd["year"]   for sd in season_data]
    wins_v   = [sd["wins"]   for sd in season_data]
    losses_v = [sd["losses"] for sd in season_data]
    colors   = [season_color(y) for y in years]

    x     = np.arange(len(years))
    width = 0.35

    for i, (yr, w, l, c) in enumerate(zip(years, wins_v, losses_v, colors)):
        ax.bar(x[i] - width / 2, w, width, color=c, alpha=0.85,
               zorder=3, label=f"{yr} W" if i == 0 else "_")
        ax.bar(x[i] + width / 2, l, width, color=c, alpha=0.45,
               hatch="//", edgecolor=c, zorder=3)

    # Era divider between 2023 and 2024 (between index 1 and 2)
    ax.axvline(1.5, color="#555566", linewidth=1.5, linestyle="--", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(years, color=TEXT_COLOR, fontsize=9)
    ax.set_ylabel("Games", color=TEXT_COLOR, fontsize=9)

    # Custom legend
    win_patch  = mpatches.Patch(facecolor="#aaaaaa", label="Wins  (solid)")
    loss_patch = mpatches.Patch(facecolor="#aaaaaa", hatch="//",
                                edgecolor="#888888", label="Losses (hatched)")
    ax.legend(handles=[win_patch, loss_patch], fontsize=8,
              facecolor=PANEL_COLOR, labelcolor=TEXT_COLOR, edgecolor=GRID_COLOR)
    style_ax(ax, "Wins vs Losses by Season")


def build_summary_table(ax: plt.Axes, season_data: list[dict]) -> None:
    """
    Row 3: head-to-head summary table comparing both managers side by side.
    Aggregates stats for Jeremy (2022-23) and Morgan (2024-25).
    """
    def agg(years_set: set) -> dict:
        sds = [sd for sd in season_data if sd["year"] in years_set]
        if not sds:
            return {}
        all_weekly = [w for sd in sds for w in sd["weekly"]]
        total_w = sum(sd["wins"]   for sd in sds)
        total_l = sum(sd["losses"] for sd in sds)
        total_pf = sum(sd["pf"] for sd in sds)
        total_pa = sum(sd["pa"] for sd in sds)
        return {
            "seasons":    len(sds),
            "record":     f"{total_w}W – {total_l}L",
            "win_pct":    f"{total_w / max(total_w + total_l, 1) * 100:.1f}%",
            "total_pf":   f"{total_pf:,.1f}",
            "total_pa":   f"{total_pa:,.1f}",
            "pt_diff":    f"{total_pf - total_pa:+,.1f}",
            "avg_pts":    f"{np.mean(all_weekly):.2f}" if all_weekly else "—",
            "max_wk":     f"{max(all_weekly):.2f}"    if all_weekly else "—",
            "min_wk":     f"{min(all_weekly):.2f}"    if all_weekly else "—",
            "playoffs":   sum(1 for sd in sds if sd["playoff"] is not None),
            "trades":     sum(sd["trades"] for sd in sds),
        }

    j = agg(JEREMY_YEARS)
    m = agg(MORGAN_YEARS)

    metrics = [
        ("Seasons managed",    "seasons"),
        ("Total record",       "record"),
        ("Win %",              "win_pct"),
        ("Total PF",           "total_pf"),
        ("Total PA",           "total_pa"),
        ("Point differential", "pt_diff"),
        ("Avg pts / week",     "avg_pts"),
        ("Max single week",    "max_wk"),
        ("Min single week",    "min_wk"),
        ("Playoff appearances","playoffs"),
        ("Trades made",        "trades"),
    ]

    # Build table data: [metric, Jeremy value, Morgan value]
    cell_text = [[label, str(j.get(key, "—")), str(m.get(key, "—"))]
                 for label, key in metrics]

    col_labels  = ["Metric", JEREMY_NAME, MORGAN_NAME]
    col_colors  = [PANEL_COLOR, JEREMY_COLOR + "55", MORGAN_COLOR + "55"]
    cell_colors = []
    for row in cell_text:
        cell_colors.append([PANEL_COLOR, JEREMY_COLOR + "22", MORGAN_COLOR + "22"])

    ax.axis("off")
    tbl = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1, 1.7)

    # Style header row
    for col_idx, color in enumerate([PANEL_COLOR, JEREMY_COLOR, MORGAN_COLOR]):
        cell = tbl[0, col_idx]
        cell.set_facecolor(color)
        cell.set_text_props(color="white" if color != PANEL_COLOR else TEXT_COLOR,
                            fontweight="bold")

    # Style data rows
    for row_idx in range(1, len(metrics) + 1):
        tbl[row_idx, 0].set_facecolor(PANEL_COLOR)
        tbl[row_idx, 0].set_text_props(color=TEXT_COLOR)
        tbl[row_idx, 1].set_facecolor(JEREMY_COLOR + "22")
        tbl[row_idx, 1].set_text_props(color=JEREMY_COLOR)
        tbl[row_idx, 2].set_facecolor(MORGAN_COLOR + "22")
        tbl[row_idx, 2].set_text_props(color=MORGAN_COLOR)
        # Alternate row shading for readability
        if row_idx % 2 == 0:
            tbl[row_idx, 0].set_facecolor("#222535")
            tbl[row_idx, 1].set_facecolor(JEREMY_COLOR + "33")
            tbl[row_idx, 2].set_facecolor(MORGAN_COLOR + "33")

    ax.set_title("Head-to-Head Summary", color=TEXT_COLOR,
                 fontsize=11, fontweight="bold", pad=12)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Team 7 Comparison: JeremyW vs morgannakonechny")
    print("=" * 60)

    # ── 1. Fetch all season data ──────────────────────────────────────────────
    all_season_data: list[dict] = []
    for year, league_id, draft_id, total_weeks in SEASONS:
        sd = fetch_season_data(year, league_id, draft_id, total_weeks)
        print(f"  {year}: {sd['owner']}  |  {sd['wins']}W-{sd['losses']}L  "
              f"|  PF={sd['pf']:.1f}  PA={sd['pa']:.1f}  "
              f"|  {len(sd['weekly'])} weeks scored")
        all_season_data.append(sd)

    years = [sd["year"] for sd in all_season_data]

    # ── 2. Build figure ───────────────────────────────────────────────────────
    fig = plt.figure(figsize=(20, 22), facecolor=BG_COLOR)
    fig.patch.set_facecolor(BG_COLOR)

    gs = gridspec.GridSpec(
        4, 4,
        figure=fig,
        hspace=0.48,
        wspace=0.35,
        height_ratios=[1, 1.4, 1.4, 1.1],
    )

    # ── Row 0: Four stat card panels ─────────────────────────────────────────
    metrics_row0 = [
        ("Wins",       [sd["wins"]   for sd in all_season_data], "{:.0f}"),
        ("Losses",     [sd["losses"] for sd in all_season_data], "{:.0f}"),
        ("Points For", [sd["pf"]     for sd in all_season_data], "{:,.0f}"),
        ("Avg Pts/Wk", [np.mean(sd["weekly"]) if sd["weekly"] else 0
                        for sd in all_season_data], "{:.1f}"),
    ]

    for col, (label, values, fmt) in enumerate(metrics_row0):
        ax = fig.add_subplot(gs[0, col])
        build_stat_card(ax, label, values, years, fmt)

    # ── Row 1: Weekly line (left) + Box plots (right) ────────────────────────
    ax_line = fig.add_subplot(gs[1, 0:2])
    build_weekly_line(ax_line, all_season_data)

    ax_box = fig.add_subplot(gs[1, 2:4])
    build_boxplots(ax_box, all_season_data)

    # ── Row 2: PF vs PA scatter (left) + Wins/Losses bar (right) ────────────
    ax_scatter = fig.add_subplot(gs[2, 0:2])
    build_pf_pa_scatter(ax_scatter, all_season_data)

    ax_wl = fig.add_subplot(gs[2, 2:4])
    build_wins_losses_bar(ax_wl, all_season_data)

    # ── Row 3: Summary table ──────────────────────────────────────────────────
    ax_table = fig.add_subplot(gs[3, :])
    build_summary_table(ax_table, all_season_data)

    # ── Title & legend ────────────────────────────────────────────────────────
    fig.suptitle(
        "JeremyW vs morgannakonechny — Same Team, Different Eras  (Roster #7)",
        fontsize=16, fontweight="bold", color=TEXT_COLOR, y=0.995,
    )

    # Global manager color legend below the title
    jeremy_patch = mpatches.Patch(color=JEREMY_COLOR, label=f"{JEREMY_NAME}  (2022–2023)")
    morgan_patch = mpatches.Patch(color=MORGAN_COLOR, label=f"{MORGAN_NAME}  (2024–2025)")
    fig.legend(handles=[jeremy_patch, morgan_patch],
               loc="upper right", bbox_to_anchor=(0.98, 0.99),
               fontsize=9, facecolor=PANEL_COLOR, labelcolor=TEXT_COLOR,
               edgecolor=GRID_COLOR, framealpha=0.9)

    # ── Save ──────────────────────────────────────────────────────────────────
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    print(f"\nSaved to {OUTPUT_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
