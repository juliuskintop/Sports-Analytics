"""
team_analysis.py
----------------
Comprehensive analysis of Ju1ius's fantasy basketball team:
  - Current roster (players, ages, positions)
  - Historical starter points by player (2022-2025)
  - Per-category breakdown if available
  - 2026 draft capital (what picks Ju1ius holds)
  - League-wide roster comparison (ages, depth, scoring)
  - Potential trade targets (players on other teams, surplus vs need)

Run with:
    uv run python team_analysis.py
"""

import json
import requests
from collections import defaultdict
from datetime import date

BASE_URL = "https://api.sleeper.app/v1"
TODAY = date(2026, 4, 15)

# ── League chain ───────────────────────────────────────────────────────────────
LEAGUES = [
    {"id": "819248226988314624",  "season": "2022", "draft_id": "887431909352296448",  "max_weeks": 25},
    {"id": "981579242393636864",  "season": "2023", "draft_id": "981579242393636865",  "max_weeks": 25},
    {"id": "1145596058320506880", "season": "2024", "draft_id": "1145596058320506881", "max_weeks": 24},
    {"id": "1219479299124371456", "season": "2025", "draft_id": "1219479299132768256", "max_weeks": 24},
]

CURRENT_LEAGUE_ID = "1219479299124371456"
MY_ROSTER_ID      = 1   # Ju1ius

ROSTER_MAP = {
    1:  "Ju1ius",
    2:  "ISTOLL21",
    3:  "MattBlake",
    4:  "joshstoll9",
    5:  "blockadamd00",
    6:  "fastillo15",
    7:  "morgannakonechny",
    8:  "ryrythejedi",
    9:  "Hamiltontp",
    10: "Larz00",
}

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

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def player_age(p):
    birth_str = p.get("birth_date")
    if not birth_str:
        return None
    try:
        y, m, d = (int(x) for x in birth_str.split("-"))
        bd  = date(y, m, d)
        return (TODAY - bd).days // 365
    except Exception:
        return None

def player_full_name(p):
    return (
        p.get("full_name")
        or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        or "Unknown"
    )

# ── 1. Fetch all NBA player metadata ──────────────────────────────────────────
print("\n[1/6] Fetching NBA player metadata...")
all_players = fetch("players/nba")
player_meta = {}
for pid, p in all_players.items():
    player_meta[str(pid)] = {
        "name":      player_full_name(p),
        "age":       player_age(p),
        "position":  p.get("position") or "",
        "positions": p.get("fantasy_positions") or [p.get("position") or ""],
        "team":      p.get("team") or "FA",
        "years_exp": p.get("years_exp"),
    }

# ── 2. Fetch current league: rosters, users, scoring settings ────────────────
print("[2/6] Fetching current league data (2025)...")
league_info = fetch(f"league/{CURRENT_LEAGUE_ID}")
scoring_settings = league_info.get("scoring_settings", {})
roster_positions = league_info.get("roster_positions", [])

users    = fetch(f"league/{CURRENT_LEAGUE_ID}/users")
rosters  = fetch(f"league/{CURRENT_LEAGUE_ID}/rosters")

owner_to_name = {u["user_id"]: u["display_name"] for u in users}

# Build full roster map: roster_id → {username, players, reserve, picks}
roster_data = {}
for r in rosters:
    rid      = r["roster_id"]
    username = ROSTER_MAP.get(rid, owner_to_name.get(r.get("owner_id"), f"roster_{rid}"))
    settings = r.get("settings", {})
    metadata = r.get("metadata", {})
    roster_data[rid] = {
        "username": username,
        "players":  r.get("players") or [],
        "starters": r.get("starters") or [],
        "reserve":  r.get("reserve") or [],
        "taxi":     r.get("taxi") or [],
        "wins":     settings.get("wins", 0),
        "losses":   settings.get("losses", 0),
        "pf":       settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100,
        "pa":       settings.get("fpts_against", 0) + settings.get("fpts_against_decimal", 0) / 100,
        "streak":   metadata.get("streak", ""),
    }

# ── 3. Accumulate starter points per player per team (all 4 seasons) ─────────
print("[3/6] Fetching historical matchup data (2022-2025)...")
# pts_by_player[player_id][username] = total starter pts across all seasons
pts_by_player     = defaultdict(lambda: defaultdict(float))
# season_pts[season][roster_id][player_id] = starter pts that season
season_pts_all    = {}
# weekly_scores[season][roster_id] = [week_pts, ...]
weekly_scores_all = {}

for league in LEAGUES:
    lid     = league["id"]
    season  = league["season"]
    max_wks = league["max_weeks"]

    meta = fetch(f"league/{lid}")
    last = min(meta["settings"].get("last_scored_leg", max_wks), max_wks)

    u_list  = fetch(f"league/{lid}/users")
    r_list  = fetch(f"league/{lid}/rosters")
    own_map = {u["user_id"]: u["display_name"] for u in u_list}
    # use ROSTER_MAP to keep names consistent
    rid_to_user = {}
    for r in r_list:
        rid = r["roster_id"]
        rid_to_user[rid] = ROSTER_MAP.get(rid, own_map.get(r.get("owner_id"), f"r{rid}"))

    s_pts  = defaultdict(lambda: defaultdict(float))   # rid → {pid: pts}
    w_pts  = defaultdict(list)                          # rid → [week_scores]

    print(f"  [{season}] {last} weeks...")
    for week in range(1, last + 1):
        matchups = fetch(f"league/{lid}/matchups/{week}")
        for team in matchups:
            rid  = team["roster_id"]
            user = rid_to_user.get(rid, f"r{rid}")
            pp   = team.get("players_points") or {}
            starters = set(team.get("starters") or [])
            wk_total = team.get("points", 0.0) or 0.0
            if wk_total > 0:
                w_pts[rid].append(float(wk_total))
            for pid in starters:
                pts = pp.get(pid, 0.0)
                if pts > 0:
                    pts_by_player[str(pid)][user] += pts
                    s_pts[rid][str(pid)] += pts

    season_pts_all[season]    = {rid: dict(pd) for rid, pd in s_pts.items()}
    weekly_scores_all[season] = {rid: list(wl)  for rid, wl in w_pts.items()}

# ── 4. Fetch 2026 draft traded picks (who owns what) ──────────────────────────
print("[4/6] Fetching 2026 draft capital (traded picks)...")

# First, get the upcoming/current draft for the 2025 league
# The 2026 rookie draft should be linked to the league
try:
    drafts_for_league = fetch(f"league/{CURRENT_LEAGUE_ID}/drafts")
    print(f"  Found {len(drafts_for_league)} draft(s) for current league")
    for d in drafts_for_league:
        print(f"    draft_id={d['draft_id']}  type={d.get('type')}  status={d.get('status')}  season={d.get('season')}")
except Exception as e:
    drafts_for_league = []
    print(f"  Error fetching drafts: {e}")

# Get traded picks for current league (shows future pick ownership)
traded_picks = []
try:
    traded_picks = fetch(f"league/{CURRENT_LEAGUE_ID}/traded_picks")
    print(f"  Found {len(traded_picks)} traded pick records")
except Exception as e:
    print(f"  Error fetching traded picks: {e}")

# ── 5. Fetch all transactions to understand trade history ─────────────────────
print("[5/6] Fetching recent transactions...")
recent_trades = []
try:
    for wk in range(1, 25):
        txns = fetch(f"league/{CURRENT_LEAGUE_ID}/transactions/{wk}")
        for t in txns:
            if t.get("type") == "trade" and t.get("status") == "complete":
                recent_trades.append(t)
except Exception:
    pass

# ── 6. Compute per-team summary stats ─────────────────────────────────────────
print("[6/6] Computing team statistics...")

import statistics

team_stats = {}
for rid, info in roster_data.items():
    username = info["username"]
    all_pids = info["players"] + info["reserve"] + info["taxi"]

    # Age distribution
    ages = [player_meta[str(pid)]["age"] for pid in all_pids if player_meta.get(str(pid), {}).get("age")]
    # Position distribution
    positions = []
    for pid in all_pids:
        meta = player_meta.get(str(pid), {})
        positions.extend(meta.get("positions", [meta.get("position", "")]))

    # Historical starter pts for this roster (all seasons combined by roster_id)
    hist_pts = 0.0
    for season, s_data in season_pts_all.items():
        # find rid in that season (roster_id is consistent)
        rid_pts = s_data.get(rid, {})
        hist_pts += sum(rid_pts.values())

    # Weekly scoring distribution (all seasons)
    all_weeks = []
    for season, w_data in weekly_scores_all.items():
        all_weeks.extend(w_data.get(rid, []))

    team_stats[rid] = {
        "username":   username,
        "wins":       info["wins"],
        "losses":     info["losses"],
        "pf":         info["pf"],
        "pa":         info["pa"],
        "n_players":  len(info["players"]),
        "ages":       ages,
        "median_age": statistics.median(ages) if ages else None,
        "avg_age":    sum(ages) / len(ages) if ages else None,
        "hist_pts":   hist_pts,
        "avg_wk":     sum(all_weeks) / len(all_weeks) if all_weeks else 0,
        "max_wk":     max(all_weeks) if all_weeks else 0,
        "std_wk":     statistics.stdev(all_weeks) if len(all_weeks) > 1 else 0,
    }

# ── OUTPUT ─────────────────────────────────────────────────────────────────────

print("\n" + "="*80)
print("LEAGUE SCORING SETTINGS (key categories)")
print("="*80)
key_cats = ["pts_rebs_asts", "pts", "reb", "ast", "stl", "blk", "to", "fgm", "fga", "fg3m", "ftm", "fta"]
for cat, val in scoring_settings.items():
    if val != 0:
        print(f"  {cat:<30} {val:>6.2f}")

print("\n" + "="*80)
print("ROSTER POSITIONS")
print("="*80)
print(" ", roster_positions)

print("\n" + "="*80)
print("MY ROSTER (Ju1ius — roster_id=1)")
print("="*80)
my_info = roster_data[MY_ROSTER_ID]
print(f"  Record: {my_info['wins']}W - {my_info['losses']}L")
print(f"  PF: {my_info['pf']:.1f}   PA: {my_info['pa']:.1f}")
print(f"\n  {'#':<3} {'Name':<28} {'Pos':<6} {'Age':<5} {'Team':<6} {'AllTime Starter Pts':>20}")
print("  " + "-"*75)

my_pids = my_info["players"] + my_info["reserve"] + my_info["taxi"]
my_player_rows = []
for pid in my_pids:
    meta  = player_meta.get(str(pid), {})
    name  = meta.get("name", f"ID:{pid}")
    pos   = "/".join(meta.get("positions", [meta.get("position","?")])) if meta.get("positions") else meta.get("position","?")
    age   = meta.get("age", "?")
    team  = meta.get("team", "FA")
    total_sp = sum(pts_by_player[str(pid)].values())
    my_pts_2025 = season_pts_all.get("2025", {}).get(MY_ROSTER_ID, {}).get(str(pid), 0.0)
    my_player_rows.append((name, pos, age, team, total_sp, my_pts_2025, str(pid)))

my_player_rows.sort(key=lambda x: x[5], reverse=True)  # sort by 2025 pts

ir_set   = set(str(p) for p in my_info.get("reserve", []))
taxi_set = set(str(p) for p in my_info.get("taxi", []))
seen_pids = set()
deduped_rows = []
for row in my_player_rows:
    pid_str = row[6]
    if pid_str not in seen_pids:
        seen_pids.add(pid_str)
        deduped_rows.append(row)

for i, (name, pos, age, team, alltime, pts25, pid) in enumerate(deduped_rows):
    flag = ""
    if str(pid) in ir_set:
        flag = " [IR]"
    elif str(pid) in taxi_set:
        flag = " [TAXI]"
    alltime_str = f"{alltime:,.0f}" if alltime is not None else "N/A"
    pts25_str   = f"{pts25:,.0f}"   if pts25   is not None else "N/A"
    print(f"  {i+1:<3} {name:<28} {pos:<6} {str(age or '?'):<5} {team:<6} {alltime_str:>12} alltime  |  {pts25_str:>7} pts25{flag}")

print("\n" + "="*80)
print("MY 2025 SEASON PER-PLAYER BREAKDOWN")
print("="*80)
my_2025_pts = season_pts_all.get("2025", {}).get(MY_ROSTER_ID, {})
rows_2025 = []
for pid, pts in my_2025_pts.items():
    meta = player_meta.get(pid, {})
    rows_2025.append((meta.get("name", pid), pts, meta.get("position",""), meta.get("age","")))
rows_2025.sort(key=lambda x: x[1], reverse=True)
print(f"  {'Name':<28} {'Pos':<6} {'Age':<5} {'2025 Starter Pts':>18}")
print("  " + "-"*60)
for name, pts, pos, age in rows_2025[:20]:
    print(f"  {name:<28} {pos:<6} {str(age):<5} {pts:>18,.1f}")

print("\n" + "="*80)
print("LEAGUE-WIDE TEAM COMPARISON")
print("="*80)
print(f"  {'Team':<22} {'W':>3} {'L':>3} {'PF':>8} {'PA':>8} {'Avg Wk':>8} {'Med Age':>8} {'AllTime':>10}")
print("  " + "-"*78)
for rid in sorted(team_stats.keys()):
    ts = team_stats[rid]
    marker = " ◄" if rid == MY_ROSTER_ID else ""
    print(f"  {ts['username']:<22} {ts['wins']:>3} {ts['losses']:>3} "
          f"{ts['pf']:>8,.0f} {ts['pa']:>8,.0f} "
          f"{ts['avg_wk']:>8.1f} "
          f"{str(round(ts['median_age'],1)) if ts['median_age'] else 'N/A':>8} "
          f"{ts['hist_pts']:>10,.0f}{marker}")

print("\n" + "="*80)
print("ROSTER AGE BREAKDOWN BY TEAM")
print("="*80)
for rid in sorted(team_stats.keys()):
    ts   = team_stats[rid]
    ages = sorted(ts["ages"])
    marker = " ◄ MY TEAM" if rid == MY_ROSTER_ID else ""
    avg_str = f"{ts['avg_age']:.1f}" if ts['avg_age'] else "N/A"
    med_str = f"{ts['median_age']:.1f}" if ts['median_age'] else "N/A"
    young   = sum(1 for a in ages if a <= 24)
    prime   = sum(1 for a in ages if 25 <= a <= 29)
    old     = sum(1 for a in ages if a >= 30)
    print(f"  {ts['username']:<22}  avg={avg_str}  med={med_str}  ≤24:{young}  25-29:{prime}  ≥30:{old}{marker}")

print("\n" + "="*80)
print("DRAFT CAPITAL — TRADED PICKS FOR CURRENT/FUTURE SEASONS")
print("="*80)
# Group traded picks by owner
my_picks = [p for p in traded_picks if p.get("owner_id") == str(MY_ROSTER_ID) or p.get("roster_id") == MY_ROSTER_ID]
print(f"\n  All {len(traded_picks)} traded pick records (showing season, round, original owner → current owner):")
for p in sorted(traded_picks, key=lambda x: (x.get("season",""), x.get("round",0))):
    original = ROSTER_MAP.get(p.get("roster_id"), f"r{p.get('roster_id')}")
    current  = ROSTER_MAP.get(p.get("owner_id"),  f"r{p.get('owner_id')}")
    prev     = ROSTER_MAP.get(p.get("previous_owner_id"), "?") if p.get("previous_owner_id") else "—"
    marker   = " ◄◄ MINE" if p.get("owner_id") == MY_ROSTER_ID else ""
    print(f"  {p.get('season','?')}  R{p.get('round','?')}  orig={original:<20}  curr={current:<20}  prev={prev}{marker}")

print("\n" + "="*80)
print("UPCOMING DRAFTS")
print("="*80)
for d in drafts_for_league:
    print(f"  draft_id={d['draft_id']}")
    print(f"    type={d.get('type')}  status={d.get('status')}  season={d.get('season')}")
    print(f"    rounds={d.get('rounds')}  picks_per_round={d.get('picks_per_round')}")
    slot_to_roster = d.get("slot_to_roster_id", {})
    order = d.get("draft_order") or {}
    print(f"    draft_order (user→slot): {order}")
    print(f"    slot_to_roster: {slot_to_roster}")

print("\n" + "="*80)
print("TOP PLAYERS ON OTHER TEAMS — TRADE TARGET CANDIDATES")
print("="*80)
# Find best players (by all-time starter pts) currently on teams other than mine
my_current_pids = set(str(p) for p in my_info["players"] + my_info["reserve"] + my_info["taxi"])

# Build: for each player with significant pts, who owns them now
pid_to_current_owner = {}
for rid, info in roster_data.items():
    for pid in info["players"] + info["reserve"] + info["taxi"]:
        pid_to_current_owner[str(pid)] = (rid, info["username"])

# Rank all rostered players by all-time starter pts who are NOT on my team
other_players = []
for pid_str, owner_info in pid_to_current_owner.items():
    if pid_str in my_current_pids:
        continue
    rid, username = owner_info
    total_sp = sum(pts_by_player[pid_str].values())
    sp_2025  = season_pts_all.get("2025", {}).get(rid, {}).get(pid_str, 0.0)
    meta     = player_meta.get(pid_str, {})
    other_players.append({
        "pid":      pid_str,
        "name":     meta.get("name", pid_str),
        "pos":      "/".join(meta.get("positions", [])) if meta.get("positions") else meta.get("position","?"),
        "age":      meta.get("age"),
        "team":     meta.get("team", "FA"),
        "owner":    username,
        "owner_rid": rid,
        "alltime":  total_sp,
        "pts_2025": sp_2025,
    })

other_players.sort(key=lambda x: x["pts_2025"], reverse=True)
print(f"\n  {'Name':<28} {'Pos':<6} {'Age':<5} {'Owner':<22} {'2025 Pts':>10} {'AllTime':>10}")
print("  " + "-"*86)
for row in other_players[:40]:
    print(f"  {row['name']:<28} {row['pos']:<6} {str(row['age'] or '?'):<5} "
          f"{row['owner']:<22} {row['pts_2025']:>10,.0f} {row['alltime']:>10,.0f}")

print("\n" + "="*80)
print("FREE AGENTS — TOP AVAILABLE PLAYERS")
print("="*80)
rostered_pids = set(pid_to_current_owner.keys())
fa_players = []
for pid_str, meta in player_meta.items():
    if pid_str in rostered_pids:
        continue
    total_sp = sum(pts_by_player[pid_str].values())
    if total_sp < 100:
        continue
    fa_players.append({
        "pid":     pid_str,
        "name":    meta.get("name", pid_str),
        "pos":     "/".join(meta.get("positions", [])) if meta.get("positions") else meta.get("position","?"),
        "age":     meta.get("age"),
        "team":    meta.get("team", "FA"),
        "alltime": total_sp,
    })
fa_players.sort(key=lambda x: x["alltime"], reverse=True)
print(f"\n  {'Name':<28} {'Pos':<6} {'Age':<5} {'NBA Team':<8} {'AllTime Starter Pts':>20}")
print("  " + "-"*72)
for row in fa_players[:20]:
    print(f"  {row['name']:<28} {row['pos']:<6} {str(row['age'] or '?'):<5} {row['team']:<8} {row['alltime']:>20,.0f}")

print("\n" + "="*80)
print("MY TEAM POSITION NEEDS ANALYSIS")
print("="*80)
pos_count = defaultdict(int)
for pid in my_info["players"]:
    meta = player_meta.get(str(pid), {})
    for p in (meta.get("positions") or [meta.get("position","?")]):
        pos_count[p] += 1
print(f"  Current roster positions: {dict(pos_count)}")
print(f"  League roster slots: {roster_positions}")

print("\n" + "="*80)
print("HISTORICAL SEASON-BY-SEASON PERFORMANCE (Ju1ius)")
print("="*80)
for season in ["2022","2023","2024","2025"]:
    league_cfg = next((l for l in LEAGUES if l["season"] == season), None)
    if not league_cfg:
        continue
    wks = weekly_scores_all.get(season, {}).get(MY_ROSTER_ID, [])
    sp  = season_pts_all.get(season, {}).get(MY_ROSTER_ID, {})
    total_sp = sum(sp.values())
    avg_wk   = sum(wks)/len(wks) if wks else 0
    info_s   = roster_data  # not per-season, but use current for record
    print(f"  {season}:  weeks={len(wks)}  avg_wk={avg_wk:.1f}  total_starter_pts={total_sp:,.0f}")

print("\n=== DONE ===\n")
