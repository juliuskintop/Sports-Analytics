import requests
import json
import matplotlib.pyplot as plt
from collections import defaultdict

BASE_URL = "https://api.sleeper.app/v1"

# ── 1. League chain (oldest → newest) ────────────────────────────────────────
LEAGUE_IDS = [
    ("819248226988314624",  "2022"),
    ("981579242393636864",  "2023"),
    ("1145596058320506880", "2024"),
    ("1219479299124371456", "2025"),
]

# ── 2. Collect starter points per (username, player_id) ──────────────────────
all_data: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

for league_id, season in LEAGUE_IDS:
    print(f"Processing {season}...")
    league   = requests.get(f"{BASE_URL}/league/{league_id}").json()
    last_week = league["settings"].get("last_scored_leg", 0)

    users    = requests.get(f"{BASE_URL}/league/{league_id}/users").json()
    owner_to_name = {u["user_id"]: u["display_name"] for u in users}

    rosters  = requests.get(f"{BASE_URL}/league/{league_id}/rosters").json()
    roster_to_name = {r["roster_id"]: owner_to_name.get(r["owner_id"], "unknown") for r in rosters}

    for week in range(1, last_week + 1):
        matchups = requests.get(f"{BASE_URL}/league/{league_id}/matchups/{week}").json()
        for team in matchups:
            username = roster_to_name.get(team["roster_id"], "unknown")
            players_points = team.get("players_points", {})
            for pid in team.get("starters", []):
                all_data[username][pid] += players_points.get(pid, 0.0)

# ── 3. Fetch player names ─────────────────────────────────────────────────────
print("Fetching player names...")
players = requests.get(f"{BASE_URL}/players/nba").json()
player_name = {
    pid: p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    for pid, p in players.items()
}

# ── 4. Config ─────────────────────────────────────────────────────────────────
TEAM_NAMES = {
    "Ju1ius":           "Ball Cancer",
    "ISTOLL21":         "The Meat-Off",
    "MattBlake":        "BallSiak",
    "joshstoll9":       "Wembys 4 for 4",
    "blockadamd00":     "Redraft Next Year?",
    "fastillo15":       "Curious Mike and Friends",
    "morgannakonechny": "big purr",
    "ryrythejedi":      "27 days, 27 nights",
    "Hamiltontp":       "Halibussy",
    "Larz00":           "Gid(didd)ey's Kiddies",
}

MANAGERS = list(TEAM_NAMES.keys())

COLORS = [
    "#E63946", "#2196F3", "#FF9800", "#9C27B0", "#4CAF50",
    "#00BCD4", "#F06292", "#8BC34A", "#FF5722", "#607D8B",
]

TOP_N = 10

# ── 5. Plot ───────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 5, figsize=(26, 14))
fig.patch.set_facecolor("#0f1117")
axes_flat = axes.flatten()

for idx, (mgr, ax) in enumerate(zip(MANAGERS, axes_flat)):
    player_pts = all_data.get(mgr, {})
    ranked = sorted(player_pts.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    names  = [player_name.get(pid, f"ID:{pid}") for pid, _ in ranked]
    pts    = [p for _, p in ranked]
    color  = COLORS[idx]

    bars = ax.barh(range(len(names)), pts, color=color, alpha=0.85, height=0.65, zorder=3)
    bars[0].set_alpha(1.0)
    bars[0].set_edgecolor("white")
    bars[0].set_linewidth(1.2)

    for i, (bar, val) in enumerate(zip(bars, pts)):
        ax.text(
            val + 30, bar.get_y() + bar.get_height() / 2,
            f"{val:,.0f}",
            va="center", ha="left", fontsize=7.5, color="white",
            fontweight="bold" if i == 0 else "normal",
        )

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8.2, color="white")
    ax.invert_yaxis()
    ax.set_facecolor("#1a1d26")
    ax.tick_params(colors="#aaaaaa", labelsize=8)
    ax.xaxis.set_tick_params(labelcolor="#777777")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.xaxis.grid(True, color="#2e3140", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    team = TEAM_NAMES.get(mgr, mgr)
    ax.set_title(f"{mgr}\n{team}", fontsize=9.5, color="white",
                 fontweight="bold", pad=8, loc="left")

    max_pts = pts[0] if pts else 1
    ax.set_xlim(0, max_pts * 1.18)
    ax.tick_params(axis="x", colors="#555555", labelsize=7)

fig.suptitle(
    "In House Studs — All-Time Starter Points by Team (2022-2025)",
    fontsize=17, fontweight="bold", color="white", y=1.01,
)

plt.tight_layout(pad=2.5, h_pad=3.5, w_pad=2.5)
plt.savefig("alltime_barchart.png", dpi=150, bbox_inches="tight", facecolor="#0f1117")
print("Saved to alltime_barchart.png")
plt.show()
