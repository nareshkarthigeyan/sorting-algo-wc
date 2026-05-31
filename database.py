import os
import sqlite3

DB_FILE = "tournament.db"

def init_db(db_path=DB_FILE):
    """Initializes the SQLite tables for storing tournament state."""
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
        ns INTEGER
    )
    """)
    
    # Bracket entrants table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bracket (
        position INTEGER PRIMARY KEY,
        algo_id INTEGER
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
    
    # 1. Save Settings / Metadata
    settings_data = [
        ("array_size", str(tournament.array_size)),
        ("visual_delay", str(tournament.visual_delay)),
        ("timeout", str(tournament.timeout)),
        ("current_stage", tournament.current_stage),
        ("next_fixture_idx", str(getattr(tournament, "next_fixture_idx", 0)))
    ]
    cursor.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", settings_data)

    
    # 2. Save Groups
    cursor.execute("DELETE FROM group_assignments")
    group_data = []
    for g_id, algos in enumerate(tournament.groups):
        for slot, algo_id in enumerate(algos):
            group_data.append((g_id, slot, algo_id))
    cursor.executemany("INSERT INTO group_assignments (group_id, slot, algo_id) VALUES (?, ?, ?)", group_data)
    
    # 3. Save Standings
    cursor.execute("DELETE FROM standings")
    standings_data = []
    for s in tournament.standings:
        standings_data.append((
            s['algo'], s['group'], s['played'], s['points'],
            s['matchWins'], s['matchDraws'], s['matchLosses'],
            s['roundWins'], s['roundLosses'], s['ns']
        ))
    cursor.executemany("""
    INSERT INTO standings (
        algo_id, group_id, played, points, match_wins, match_draws, match_losses, round_wins, round_losses, ns
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, standings_data)
    
    # 4. Save Bracket
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
        
        # 1. Load Settings
        cursor.execute("SELECT key, value FROM settings")
        settings_dict = dict(cursor.fetchall())
        if "array_size" in settings_dict:
            tournament.array_size = int(settings_dict["array_size"])
        if "visual_delay" in settings_dict:
            tournament.visual_delay = float(settings_dict["visual_delay"])
        if "timeout" in settings_dict:
            tournament.timeout = int(settings_dict["timeout"])
        if "current_stage" in settings_dict:
            tournament.current_stage = settings_dict["current_stage"]
        if "next_fixture_idx" in settings_dict:
            tournament.next_fixture_idx = int(settings_dict["next_fixture_idx"])
        else:
            tournament.next_fixture_idx = 0

            
        # 2. Load Groups
        cursor.execute("SELECT group_id, slot, algo_id FROM group_assignments ORDER BY group_id, slot")
        rows = cursor.fetchall()
        groups = [[] for _ in range(8)]
        for r in rows:
            g_id, slot, algo_id = r
            groups[g_id].append(algo_id)
        tournament.groups = groups
        tournament.build_schedule() # Rebuild schedule based on restored groups
        
        # 3. Load Standings
        cursor.execute("SELECT algo_id, group_id, played, points, match_wins, match_draws, match_losses, round_wins, round_losses, ns FROM standings")
        rows = cursor.fetchall()
        standings = []
        for r in rows:
            algo_id, g_id, played, pts, m_w, m_d, m_l, r_w, r_l, ns = r
            standings.append({
                'algo': algo_id,
                'group': g_id,
                'played': played,
                'points': pts,
                'matchWins': m_w,
                'matchDraws': m_d,
                'matchLosses': m_l,
                'roundWins': r_w,
                'roundLosses': r_l,
                'ns': ns
            })
        # Sort standings by algo index to match tournament setup
        standings.sort(key=lambda x: x['algo'])
        tournament.standings = standings
        
        # 4. Load Bracket
        cursor.execute("SELECT algo_id FROM bracket ORDER BY position")
        rows = cursor.fetchall()
        tournament.current_bracket = [r[0] for r in rows]
        
        conn.close()
        return True
    except sqlite3.Error:
        return False
