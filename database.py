import os
import sqlite3
import json

DB_FILE = "tournament.db"

def init_db(db_path=DB_FILE):
    """Initializes the SQLite tables for storing tournament state and global stats."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Metadata/Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Groups assignment table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_assignments (
        group_id INTEGER,
        slot INTEGER,
        algo_id INTEGER,
        PRIMARY KEY (group_id, slot)
    )
    """)
    
    # Standings table
    cursor.execute("PRAGMA table_info(standings)")
    columns = [col[1] for col in cursor.fetchall()]
    if columns and "ko_played" not in columns:
        cursor.execute("DROP TABLE IF EXISTS standings")
        
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS standings (
        algo_id INTEGER PRIMARY KEY,
        group_id INTEGER,
        played INTEGER,
        points INTEGER,
        match_wins INTEGER,
        match_draws INTEGER,
        match_losses INTEGER,
        round_wins INTEGER,
        round_losses INTEGER,
        ns INTEGER,
        ko_played INTEGER DEFAULT 0,
        ko_points INTEGER DEFAULT 0,
        ko_match_wins INTEGER DEFAULT 0,
        ko_match_losses INTEGER DEFAULT 0,
        ko_round_wins INTEGER DEFAULT 0,
        ko_round_losses INTEGER DEFAULT 0,
        ko_ns INTEGER DEFAULT 0
    )
    """)
    
    # Bracket entrants table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bracket (
        position INTEGER PRIMARY KEY,
        algo_id INTEGER
    )
    """)
    
    # ELO ratings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS elo_ratings (
        algo_name TEXT PRIMARY KEY,
        rating REAL DEFAULT 1500.0
    )
    """)
    
    # Hall of Fame table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hall_of_fame (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        champion_name TEXT,
        year INTEGER,
        record TEXT,
        avg_finish_time REAL,
        path TEXT
    )
    """)
    
    # Scenario performance table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scenario_performance (
        algo_name TEXT,
        scenario_id INTEGER,
        total_time_ns INTEGER DEFAULT 0,
        total_ops INTEGER DEFAULT 0,
        runs INTEGER DEFAULT 0,
        PRIMARY KEY (algo_name, scenario_id)
    )
    """)
    
    # Tournament Archives table (stands, brackets, fixtures of past years)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tournament_archives (
        year INTEGER PRIMARY KEY,
        standings_json TEXT,
        bracket_json TEXT,
        fixtures_json TEXT,
        champion TEXT
    )
    """)
    
    # Expanded Historical Stats table (supporting results lists, championship years, etc.)
    # We drop the old historical_stats table if it uses the older structure
    cursor.execute("PRAGMA table_info(historical_stats)")
    columns = [col[1] for col in cursor.fetchall()]
    if columns and "draws" not in columns:
        cursor.execute("DROP TABLE IF EXISTS historical_stats")
        
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_stats (
        algo_name TEXT PRIMARY KEY,
        played INTEGER DEFAULT 0,
        won INTEGER DEFAULT 0,
        lost INTEGER DEFAULT 0,
        draws INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        round_wins INTEGER DEFAULT 0,
        round_losses INTEGER DEFAULT 0,
        fastest_ns INTEGER DEFAULT -1,
        longest_ns INTEGER DEFAULT -1,
        group_stage INTEGER DEFAULT 0,
        r16_apps INTEGER DEFAULT 0,
        qf_apps INTEGER DEFAULT 0,
        sf_apps INTEGER DEFAULT 0,
        championships INTEGER DEFAULT 0,
        championship_years TEXT DEFAULT '[]',
        runner_up_count INTEGER DEFAULT 0,
        runner_up_years TEXT DEFAULT '[]',
        r16_results TEXT DEFAULT '[]',
        qf_results TEXT DEFAULT '[]',
        sf_results TEXT DEFAULT '[]',
        total_sorted_time_ns INTEGER DEFAULT 0,
        total_sorted_rounds INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()

def has_saved_tournament(db_path=DB_FILE):
    """Checks if there is a saved group draw in the database."""
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM group_assignments")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except sqlite3.Error:
        return False

def save_tournament(tournament, db_path=DB_FILE):
    """Saves the entire state of a Tournament instance to SQLite."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    elo_state = {}
    elo_diffs = {}
    for a in tournament.algos:
        elo_state[a['name']] = a.get('elo', 1500.0)
        elo_diffs[a['name']] = a.get('tournament_elo_diff', 0.0)
        
    settings_data = [
        ("year", str(getattr(tournament, "year", 2026))),
        ("array_size", str(tournament.array_size)),
        ("knockouts_size", str(tournament.knockouts_size)),
        ("final_size", str(tournament.final_size)),
        ("visual_delay", str(tournament.visual_delay)),
        ("group_timeout", str(getattr(tournament, "group_timeout", 30))),
        ("ko_timeout", str(getattr(tournament, "ko_timeout", 60))),
        ("final_timeout", str(getattr(tournament, "final_timeout", 240))),
        ("current_stage", tournament.current_stage),
        ("next_fixture_idx", str(getattr(tournament, "next_fixture_idx", 0))),
        ("elo_state_json", json.dumps(elo_state)),
        ("elo_diffs_json", json.dumps(elo_diffs)),
        ("paths_json", json.dumps(getattr(tournament, "paths", {}))),
        ("total_sorted_rounds_json", json.dumps(getattr(tournament, "total_sorted_rounds", {}))),
        ("total_sorted_time_ns_json", json.dumps(getattr(tournament, "total_sorted_time_ns", {}))),
        ("fastest_round_ns", str(getattr(tournament, "fastest_round_ns", 999999999999))),
        ("fastest_round_algo", str(getattr(tournament, "fastest_round_algo", ""))),
        ("lowest_ops_round_val", str(getattr(tournament, "lowest_ops_round_val", 999999999999))),
        ("lowest_ops_round_algo", str(getattr(tournament, "lowest_ops_round_algo", ""))),
        ("giant_kills_json", json.dumps(getattr(tournament, "giant_kills", []))),
        ("autoplay", str(1 if getattr(tournament, "autoplay", False) else 0)),
        ("bracket_entrants_json", json.dumps(getattr(tournament, "bracket_entrants", []))),
        ("active_cup", getattr(tournament, "active_cup", "World Cup")),
        ("wc_teams_json", json.dumps(getattr(tournament, "wc_teams", []))),
        ("challenger_teams_json", json.dumps(getattr(tournament, "challenger_teams", []))),
        ("relegated_teams_json", json.dumps(getattr(tournament, "relegated_teams", []))),
        ("promoted_teams_json", json.dumps(getattr(tournament, "promoted_teams", []))),
        ("challenger_cup_winner", getattr(tournament, "challenger_cup_winner", "")),
        ("cc_current_bracket_json", json.dumps(getattr(tournament, "cc_current_bracket", []))),
        ("cc_bracket_entrants_json", json.dumps(getattr(tournament, "cc_bracket_entrants", []))),
        ("cc_lcp_bracket_json", json.dumps(getattr(tournament, "cc_lcp_bracket", []))),
        ("cc_lcp_entrants_json", json.dumps(getattr(tournament, "cc_lcp_entrants", []))),
        ("archive_wc_standings_json", json.dumps(getattr(tournament, "archive_wc_standings", []))),
        ("archive_wc_bracket_json", json.dumps(getattr(tournament, "archive_wc_bracket", []))),
        ("archive_wc_fixtures_json", json.dumps(getattr(tournament, "archive_wc_fixtures", []))),
        ("archive_wc_champ", getattr(tournament, "archive_wc_champ", "")),
        ("knockout_results_json", json.dumps(getattr(tournament, "knockout_results", {}))),
        ("cc_knockout_results_json", json.dumps(getattr(tournament, "cc_knockout_results", {}))),
        ("archive_wc_results_json", json.dumps(getattr(tournament, "archive_wc_results", {})))
    ]
    cursor.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", settings_data)

    cursor.execute("DELETE FROM group_assignments")
    group_data = []
    for g_id, algos in enumerate(tournament.groups):
        for slot, algo_id in enumerate(algos):
            group_data.append((g_id, slot, algo_id))
    cursor.executemany("INSERT INTO group_assignments (group_id, slot, algo_id) VALUES (?, ?, ?)", group_data)
    
    cursor.execute("DELETE FROM standings")
    standings_data = []
    for s in tournament.standings:
        standings_data.append((
            s['algo'], s['group'], s['played'], s['points'],
            s['matchWins'], s['matchDraws'], s['matchLosses'],
            s['roundWins'], s['roundLosses'], s['ns'],
            s.get('ko_played', 0), s.get('ko_points', 0),
            s.get('ko_matchWins', 0), s.get('ko_matchLosses', 0),
            s.get('ko_roundWins', 0), s.get('ko_roundLosses', 0),
            s.get('ko_ns', 0)
        ))
    cursor.executemany("""
    INSERT INTO standings (
        algo_id, group_id, played, points, match_wins, match_draws, match_losses, round_wins, round_losses, ns,
        ko_played, ko_points, ko_match_wins, ko_match_losses, ko_round_wins, ko_round_losses, ko_ns
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, standings_data)
    
    cursor.execute("DELETE FROM bracket")
    bracket_data = [(pos, algo_id) for pos, algo_id in enumerate(tournament.current_bracket)]
    cursor.executemany("INSERT INTO bracket (position, algo_id) VALUES (?, ?)", bracket_data)
    
    conn.commit()
    conn.close()

def load_tournament(tournament, db_path=DB_FILE):
    """Loads the tournament state from SQLite into a Tournament instance."""
    if not has_saved_tournament(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM settings")
        settings_dict = dict(cursor.fetchall())
        if "year" in settings_dict:
            tournament.year = int(settings_dict["year"])
        if "array_size" in settings_dict:
            tournament.array_size = int(settings_dict["array_size"])
        if "knockouts_size" in settings_dict:
            tournament.knockouts_size = int(settings_dict["knockouts_size"])
        if "final_size" in settings_dict:
            tournament.final_size = int(settings_dict["final_size"])
        if "visual_delay" in settings_dict:
            tournament.visual_delay = float(settings_dict["visual_delay"])
            
        group_to = 30
        ko_to = 60
        final_to = 240
        if "timeout" in settings_dict:
            val = int(settings_dict["timeout"])
            group_to = val
            ko_to = val
            final_to = val
            
        tournament.group_timeout = int(settings_dict.get("group_timeout", group_to))
        tournament.ko_timeout = int(settings_dict.get("ko_timeout", ko_to))
        tournament.final_timeout = int(settings_dict.get("final_timeout", final_to))
        if "current_stage" in settings_dict:
            tournament.current_stage = settings_dict["current_stage"]
        if "next_fixture_idx" in settings_dict:
            tournament.next_fixture_idx = int(settings_dict["next_fixture_idx"])
        else:
            tournament.next_fixture_idx = 0
            
        if "elo_state_json" in settings_dict:
            elo_state = json.loads(settings_dict["elo_state_json"])
            for a in tournament.algos:
                if a['name'] in elo_state:
                    a['elo'] = elo_state[a['name']]
        if "elo_diffs_json" in settings_dict:
            elo_diffs = json.loads(settings_dict["elo_diffs_json"])
            for a in tournament.algos:
                if a['name'] in elo_diffs:
                    a['tournament_elo_diff'] = elo_diffs[a['name']]

        if "paths_json" in settings_dict:
            tournament.paths = json.loads(settings_dict["paths_json"])
        if "total_sorted_rounds_json" in settings_dict:
            tournament.total_sorted_rounds = json.loads(settings_dict["total_sorted_rounds_json"])
        if "total_sorted_time_ns_json" in settings_dict:
            tournament.total_sorted_time_ns = json.loads(settings_dict["total_sorted_time_ns_json"])
        if "fastest_round_ns" in settings_dict:
            tournament.fastest_round_ns = int(settings_dict["fastest_round_ns"])
        if "fastest_round_algo" in settings_dict:
            tournament.fastest_round_algo = settings_dict["fastest_round_algo"]
        if "lowest_ops_round_val" in settings_dict:
            tournament.lowest_ops_round_val = int(settings_dict["lowest_ops_round_val"])
        if "lowest_ops_round_algo" in settings_dict:
            tournament.lowest_ops_round_algo = settings_dict["lowest_ops_round_algo"]
        if "giant_kills_json" in settings_dict:
            tournament.giant_kills = json.loads(settings_dict["giant_kills_json"])
        if "autoplay" in settings_dict:
            tournament.autoplay = (settings_dict["autoplay"] == "1")
        if "bracket_entrants_json" in settings_dict:
            tournament.bracket_entrants = json.loads(settings_dict["bracket_entrants_json"])

        tournament.active_cup = settings_dict.get("active_cup", "World Cup")
        tournament.wc_teams = json.loads(settings_dict.get("wc_teams_json", "[]"))
        tournament.challenger_teams = json.loads(settings_dict.get("challenger_teams_json", "[]"))
        tournament.relegated_teams = json.loads(settings_dict.get("relegated_teams_json", "[]"))
        tournament.promoted_teams = json.loads(settings_dict.get("promoted_teams_json", "[]"))
        
        # Backward-compatibility fallbacks
        new_algo_names = ["PDQSort", "GrailSort", "Flash Sort", "WikiSort", "Sleep Sort", "American Flag Sort", "Gravity Sort", "Slowsort"]
        if not tournament.wc_teams:
            tournament.wc_teams = [a['name'] for a in tournament.algos if a['name'] not in new_algo_names]
        if not tournament.challenger_teams:
            tournament.challenger_teams = [a['name'] for a in tournament.algos if a['name'] in new_algo_names and a['name'] not in tournament.relegated_teams and a['name'] not in tournament.promoted_teams]

        tournament.challenger_cup_winner = settings_dict.get("challenger_cup_winner", "")
        tournament.cc_current_bracket = json.loads(settings_dict.get("cc_current_bracket_json", "[]"))
        tournament.cc_bracket_entrants = json.loads(settings_dict.get("cc_bracket_entrants_json", "[]"))
        tournament.cc_lcp_bracket = json.loads(settings_dict.get("cc_lcp_bracket_json", "[]"))
        tournament.cc_lcp_entrants = json.loads(settings_dict.get("cc_lcp_entrants_json", "[]"))
        tournament.archive_wc_standings = json.loads(settings_dict.get("archive_wc_standings_json", "[]"))
        tournament.archive_wc_bracket = json.loads(settings_dict.get("archive_wc_bracket_json", "[]"))
        tournament.archive_wc_fixtures = json.loads(settings_dict.get("archive_wc_fixtures_json", "[]"))
        tournament.archive_wc_champ = settings_dict.get("archive_wc_champ", "")
        tournament.knockout_results = json.loads(settings_dict.get("knockout_results_json", "{}"))
        tournament.cc_knockout_results = json.loads(settings_dict.get("cc_knockout_results_json", "{}"))
        tournament.archive_wc_results = json.loads(settings_dict.get("archive_wc_results_json", "{}"))

        cursor.execute("SELECT group_id, slot, algo_id FROM group_assignments ORDER BY group_id, slot")
        rows = cursor.fetchall()
        max_g = 7
        for r in rows:
            max_g = max(max_g, r[0])
        groups = [[] for _ in range(max_g + 1)]
        for r in rows:
            g_id, slot, algo_id = r
            groups[g_id].append(algo_id)
        tournament.groups = groups
        tournament.build_schedule()
        
        # Ensure tournament.standings has 40 entries
        if not hasattr(tournament, 'standings') or len(tournament.standings) != len(tournament.algos):
            tournament.standings = [{'algo': i, 'group': -1, 'played': 0, 'points': 0, 'matchWins': 0, 'matchDraws': 0, 'matchLosses': 0, 'roundWins': 0, 'roundLosses': 0, 'ns': 0, 'ko_played': 0, 'ko_points': 0, 'ko_matchWins': 0, 'ko_matchLosses': 0, 'ko_roundWins': 0, 'ko_roundLosses': 0, 'ko_ns': 0} for i in range(len(tournament.algos))]
            
        cursor.execute("SELECT algo_id, group_id, played, points, match_wins, match_draws, match_losses, round_wins, round_losses, ns, ko_played, ko_points, ko_match_wins, ko_match_losses, ko_round_wins, ko_round_losses, ko_ns FROM standings")
        rows = cursor.fetchall()
        for r in rows:
            algo_id, g_id, played, pts, m_w, m_d, m_l, r_w, r_l, ns, ko_p, ko_pts, ko_mw, ko_ml, ko_rw, ko_rl, ko_ns = r
            if 0 <= algo_id < len(tournament.standings):
                s = tournament.standings[algo_id]
                s['group'] = g_id
                s['played'] = played
                s['points'] = pts
                s['matchWins'] = m_w
                s['matchDraws'] = m_d
                s['matchLosses'] = m_l
                s['roundWins'] = r_w
                s['roundLosses'] = r_l
                s['ns'] = ns
                s['ko_played'] = ko_p
                s['ko_points'] = ko_pts
                s['ko_matchWins'] = ko_mw
                s['ko_matchLosses'] = ko_ml
                s['ko_roundWins'] = ko_rw
                s['ko_roundLosses'] = ko_rl
                s['ko_ns'] = ko_ns
        
        cursor.execute("SELECT algo_id FROM bracket ORDER BY position")
        rows = cursor.fetchall()
        tournament.current_bracket = [r[0] for r in rows]
        
        conn.close()
        return True
    except sqlite3.Error:
        return False

def delete_saved_tournament(db_path=DB_FILE):
    """Deletes temporary active tournament state settings to start a fresh season."""
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM group_assignments")
    cursor.execute("DELETE FROM standings")
    cursor.execute("DELETE FROM bracket")
    # Delete running settings except the current year counter
    cursor.execute("DELETE FROM settings WHERE key != 'year'")
    conn.commit()
    conn.close()

# Global/Historical Helper Functions

def get_elo_ratings(db_path=DB_FILE):
    """Loads all saved ELO ratings. Defaults to 1500.0 if not set."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT algo_name, rating FROM elo_ratings")
    res = dict(cursor.fetchall())
    conn.close()
    return res

def save_elo_ratings(ratings, db_path=DB_FILE):
    """Saves a dictionary of elo ratings {algo_name: rating}."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    data = [(name, rating) for name, rating in ratings.items()]
    cursor.executemany("INSERT OR REPLACE INTO elo_ratings (algo_name, rating) VALUES (?, ?)", data)
    conn.commit()
    conn.close()

def get_historical_stats(db_path=DB_FILE):
    """Loads historical stats for all algorithms."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT algo_name, played, won, lost, draws, points, round_wins, round_losses, fastest_ns, longest_ns, 
               group_stage, r16_apps, qf_apps, sf_apps, championships, championship_years, 
               runner_up_count, runner_up_years, r16_results, qf_results, sf_results, 
               total_sorted_time_ns, total_sorted_rounds
        FROM historical_stats
    """)
    rows = cursor.fetchall()
    conn.close()
    
    stats = {}
    for r in rows:
        stats[r[0]] = {
            'played': r[1],
            'won': r[2],
            'lost': r[3],
            'draws': r[4],
            'points': r[5],
            'round_wins': r[6],
            'round_losses': r[7],
            'fastest_ns': r[8],
            'longest_ns': r[9],
            'group_stage': r[10],
            'r16_apps': r[11],
            'qf_apps': r[12],
            'sf_apps': r[13],
            'championships': r[14],
            'championship_years': json.loads(r[15] or '[]'),
            'runner_up_count': r[16],
            'runner_up_years': json.loads(r[17] or '[]'),
            'r16_results': json.loads(r[18] or '[]'),
            'qf_results': json.loads(r[19] or '[]'),
            'sf_results': json.loads(r[20] or '[]'),
            'total_sorted_time_ns': r[21],
            'total_sorted_rounds': r[22]
        }
    return stats

def update_historical_stats(algo_name, match_played=0, match_won=0, match_lost=0, match_draws=0, points_inc=0,
                            round_wins=0, round_losses=0, round_time_ns=-1, group_stage_inc=0,
                            r16_inc=0, qf_inc=0, sf_inc=0, championship_inc=0, championship_year=None,
                            runner_up_inc=0, runner_up_year=None, r16_result=None, qf_result=None, sf_result=None,
                            total_sorted_time_ns_inc=0, total_sorted_rounds_inc=0, db_path=DB_FILE):
    """Updates historical stats for a single algorithm, preserving records and list tracking."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT played, won, lost, draws, points, round_wins, round_losses, fastest_ns, longest_ns, 
               group_stage, r16_apps, qf_apps, sf_apps, championships, championship_years, 
               runner_up_count, runner_up_years, r16_results, qf_results, sf_results, 
               total_sorted_time_ns, total_sorted_rounds
        FROM historical_stats WHERE algo_name = ?
    """, (algo_name,))
    row = cursor.fetchone()
    
    if row:
        (played, won, lost, draws, points, r_wins, r_losses, fastest, longest, 
         g_stage, r16, qf, sf, champs, champ_yrs_str, runner_up_cnt, runner_up_yrs_str, 
         r16_res_str, qf_res_str, sf_res_str, total_time, total_rounds) = row
         
        champ_yrs = json.loads(champ_yrs_str or '[]')
        runner_up_yrs = json.loads(runner_up_yrs_str or '[]')
        r16_res = json.loads(r16_res_str or '[]')
        qf_res = json.loads(qf_res_str or '[]')
        sf_res = json.loads(sf_res_str or '[]')
        
        played += match_played
        won += match_won
        lost += match_lost
        draws += match_draws
        points += points_inc
        r_wins += round_wins
        r_losses += round_losses
        g_stage += group_stage_inc
        r16 += r16_inc
        qf += qf_inc
        sf += sf_inc
        champs += championship_inc
        runner_up_cnt += runner_up_inc
        total_time += total_sorted_time_ns_inc
        total_rounds += total_sorted_rounds_inc
        
        if round_time_ns > 0:
            if fastest == -1 or round_time_ns < fastest:
                fastest = round_time_ns
            if longest == -1 or round_time_ns > longest:
                longest = round_time_ns
                
        if championship_year is not None:
            champ_yrs.append(championship_year)
        if runner_up_year is not None:
            runner_up_yrs.append(runner_up_year)
        if r16_result is not None:
            r16_res.append(r16_result)
        if qf_result is not None:
            qf_res.append(qf_result)
        if sf_result is not None:
            sf_res.append(sf_result)
            
    else:
        played = match_played
        won = match_won
        lost = match_lost
        draws = match_draws
        points = points_inc
        r_wins = round_wins
        r_losses = round_losses
        fastest = round_time_ns if round_time_ns > 0 else -1
        longest = round_time_ns if round_time_ns > 0 else -1
        g_stage = group_stage_inc
        r16 = r16_inc
        qf = qf_inc
        sf = sf_inc
        champs = championship_inc
        runner_up_cnt = runner_up_inc
        total_time = total_sorted_time_ns_inc
        total_rounds = total_sorted_rounds_inc
        
        champ_yrs = [championship_year] if championship_year is not None else []
        runner_up_yrs = [runner_up_year] if runner_up_year is not None else []
        r16_res = [r16_result] if r16_result is not None else []
        qf_res = [qf_result] if qf_result is not None else []
        sf_res = [sf_result] if sf_result is not None else []
        
    cursor.execute("""
        INSERT OR REPLACE INTO historical_stats
        (algo_name, played, won, lost, draws, points, round_wins, round_losses, fastest_ns, longest_ns, 
         group_stage, r16_apps, qf_apps, sf_apps, championships, championship_years, 
         runner_up_count, runner_up_years, r16_results, qf_results, sf_results, 
         total_sorted_time_ns, total_sorted_rounds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (algo_name, played, won, lost, draws, points, r_wins, r_losses, fastest, longest,
          g_stage, r16, qf, sf, champs, json.dumps(champ_yrs),
          runner_up_cnt, json.dumps(runner_up_yrs), json.dumps(r16_res), json.dumps(qf_res), json.dumps(sf_res),
          total_time, total_rounds))
    
    conn.commit()
    conn.close()

def get_hall_of_fame(db_path=DB_FILE):
    """Retrieves all Hall of Fame champion entries."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT champion_name, year, record, avg_finish_time, path FROM hall_of_fame ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    hof = []
    for r in rows:
        hof.append({
            'champion_name': r[0],
            'year': r[1],
            'record': r[2],
            'avg_finish_time': r[3],
            'path': r[4]
        })
    return hof

def add_hall_of_fame_entry(champion_name, year, record, avg_finish_time, path, db_path=DB_FILE):
    """Adds a champion entry to the Hall of Fame."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hall_of_fame (champion_name, year, record, avg_finish_time, path)
        VALUES (?, ?, ?, ?, ?)
    """, (champion_name, year, record, avg_finish_time, path))
    conn.commit()
    conn.close()

def get_scenario_performance(db_path=DB_FILE):
    """Retrieves scenario statistics for all algorithms."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT algo_name, scenario_id, total_time_ns, total_ops, runs FROM scenario_performance")
    rows = cursor.fetchall()
    conn.close()
    
    perf = {}
    for r in rows:
        name, scen_id, total_time, total_ops, runs = r
        if name not in perf:
            perf[name] = {}
        perf[name][scen_id] = {
            'avg_time_ns': total_time / runs if runs > 0 else 0,
            'avg_ops': total_ops / runs if runs > 0 else 0,
            'runs': runs
        }
    return perf

def update_scenario_performance(algo_name, scenario_id, time_ns, ops, db_path=DB_FILE):
    """Updates scenario stats for an algorithm, incrementing run count and adding time and operation counts."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT total_time_ns, total_ops, runs FROM scenario_performance
        WHERE algo_name = ? AND scenario_id = ?
    """, (algo_name, scenario_id))
    row = cursor.fetchone()
    
    if row:
        total_time, total_ops, runs = row
        total_time += time_ns
        total_ops += ops
        runs += 1
    else:
        total_time = time_ns
        total_ops = ops
        runs = 1
        
    cursor.execute("""
        INSERT OR REPLACE INTO scenario_performance (algo_name, scenario_id, total_time_ns, total_ops, runs)
        VALUES (?, ?, ?, ?, ?)
    """, (algo_name, scenario_id, total_time, total_ops, runs))
    
    conn.commit()
    conn.close()

# Tournament Season Archival Helpers

def archive_tournament_season(year, standings, bracket, fixtures, champion, cc_standings=None, cc_bracket=None, cc_fixtures=None, cc_champ=None, cc_lcp_bracket=None, wc_results=None, cc_results=None, db_path=DB_FILE):
    """Stores the complete standings, bracket tree, fixtures, and champion name of a season."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    if cc_standings is not None:
        standings_data = {"wc": standings, "cc": cc_standings}
        bracket_data = {
            "wc": bracket,
            "cc_main": cc_bracket,
            "cc_lcp": cc_lcp_bracket,
            "wc_results": wc_results if wc_results is not None else {},
            "cc_results": cc_results if cc_results is not None else {}
        }
        fixtures_data = {"wc": fixtures, "cc": cc_fixtures}
        champion_data = json.dumps({"wc": champion, "cc": cc_champ})
    else:
        standings_data = standings
        bracket_data = {
            "wc": bracket,
            "wc_results": wc_results if wc_results is not None else {}
        }
        fixtures_data = fixtures
        champion_data = champion

    cursor.execute("""
        INSERT OR REPLACE INTO tournament_archives (year, standings_json, bracket_json, fixtures_json, champion)
        VALUES (?, ?, ?, ?, ?)
    """, (year, json.dumps(standings_data), json.dumps(bracket_data), json.dumps(fixtures_data), champion_data))
    conn.commit()
    conn.close()

def get_archived_seasons(db_path=DB_FILE):
    """Retrieves all archived years/seasons in descending order."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT year, champion FROM tournament_archives ORDER BY year DESC")
    rows = cursor.fetchall()
    conn.close()
    
    decoded = []
    for yr, champ in rows:
        try:
            val = json.loads(champ)
            if isinstance(val, dict) and "wc" in val:
                decoded.append((yr, val["wc"]))
            else:
                decoded.append((yr, str(champ)))
        except Exception:
            decoded.append((yr, str(champ)))
    return decoded

def get_archived_season_details(year, db_path=DB_FILE):
    """Retrieves detailed archived records for a specific tournament year."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT standings_json, bracket_json, fixtures_json, champion FROM tournament_archives WHERE year = ?", (year,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            standings = json.loads(row[0])
            bracket = json.loads(row[1])
            fixtures = json.loads(row[2])
            champ_raw = row[3]
            try:
                champ_dict = json.loads(champ_raw)
                if isinstance(champ_dict, dict) and "wc" in champ_dict:
                    wc_champ = champ_dict["wc"]
                    cc_champ = champ_dict.get("cc", "")
                else:
                    wc_champ = str(champ_raw)
                    cc_champ = ""
            except Exception:
                wc_champ = str(champ_raw)
                cc_champ = ""
                
            return {
                'standings': standings,
                'bracket': bracket,
                'fixtures': fixtures,
                'champion': wc_champ,
                'cc_champion': cc_champ
            }
        except Exception:
            pass
    return None
