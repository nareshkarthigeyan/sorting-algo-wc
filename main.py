import sys
sys.setrecursionlimit(2000000)
import time
import random
import threading
import terminal_ui
import sorting_world_cup
import database

def run_self_test():
    print("Running self-test for 32 Python sorting algorithms...")
    algos = sorting_world_cup.get_algorithms()
    scenarios = [0, 1, 2, 3, 4]
    
    rng = random.Random(20260531)
    failures = 0
    
    for algo in algos:
        for scen in scenarios:
            input_arr = sorting_world_cup.make_input(scen, 6, rng)
            
            st = sorting_world_cup.VisualState(algo['name'])
            cancel = threading.Event()
            pause = threading.Event()
            paused_ns = sorting_world_cup.Accumulator()
            
            worker = threading.Thread(
                target=sorting_world_cup.run_sorter,
                args=(algo['sort'], input_arr, st, cancel, pause, paused_ns, 0.0)
            )
            worker.start()
            
            # Wait up to 2.0 seconds
            worker.join(timeout=2.0)
            if worker.is_alive():
                cancel.set()
                worker.join()
                
            with st.lock:
                ok = st.sorted
                cancelled = st.cancelled
                
            if not ok:
                failures += 1
                msg = " (timeout)" if cancelled else ""
                print(f"FAIL: {algo['name']} on {sorting_world_cup.SCENARIO_NAMES[scen]}{msg}")
                
    # Quick Sort smoke tests on size 100,000 (sorted scenario)
    smoke_names = ["Quick Sort", "3-Way Quick Sort"]
    for name in smoke_names:
        algo = next((a for a in algos if a['name'] == name), None)
        if algo is None:
            continue
            
        input_arr = sorting_world_cup.make_input(0, 100000, rng)
        st = sorting_world_cup.VisualState(algo['name'])
        cancel = threading.Event()
        pause = threading.Event()
        paused_ns = sorting_world_cup.Accumulator()
        
        worker = threading.Thread(
            target=sorting_world_cup.run_sorter,
            args=(algo['sort'], input_arr, st, cancel, pause, paused_ns, 0.0)
        )
        worker.start()
        
        # Wait up to 25.0 seconds
        worker.join(timeout=25.0)
        if worker.is_alive():
            cancel.set()
            worker.join()
            
        with st.lock:
            ok = st.sorted and not st.cancelled
            
        if not ok:
            failures += 1
            print(f"FAIL: {algo['name']} on 100,000 sorted values")
            
    if failures == 0:
        print("Self-test passed: 32 algorithms x 5 scenarios + 100,000-item quicksort smoke tests.")
        return 0
    else:
        print(f"Self-test failed: {failures} case(s).")
        return 1

def prompt_custom_value(prompt_text, val_type=int):
    """Temporarily restores terminal, prompts user for a custom value, validates it, and re-initializes terminal."""
    import terminal_ui
    import time
    terminal_ui.restore_terminal()
    print("\n" + "=" * 60)
    print(" CUSTOM SETTING CONFIGURATION")
    print("=" * 60)
    try:
        val_str = input(f" {prompt_text}: ").strip()
        if not val_str:
            print(" No value entered. Keeping current setting.")
            time.sleep(1.0)
            return None
        if val_type == int:
            val = int(val_str.replace(',', '').replace(' ', '').strip())
            if val <= 0:
                print(" Error: Value must be a positive integer.")
                time.sleep(1.5)
                return None
            return val
        elif val_type == float:
            val = float(val_str.strip())
            if val < 0:
                print(" Error: Value cannot be negative.")
                time.sleep(1.5)
                return None
            return val
    except ValueError:
        print(" Error: Invalid number format entered.")
        time.sleep(1.5)
        return None
    finally:
        terminal_ui.init_terminal()

def get_next_preset(current_val, presets, direction):
    if current_val in presets:
        idx = presets.index(current_val)
        return presets[(idx + direction) % len(presets)]
    else:
        closest = min(presets, key=lambda x: abs(x - current_val))
        idx = presets.index(closest)
        return presets[(idx + direction) % len(presets)]

def run_settings(settings):
    """Sub-menu for modifying running settings with presets cycling and manual custom input."""
    array_sizes = [1000, 5000, 10000, 50000, 100000]
    knockouts_sizes = [50000, 100000, 200000, 500000, 1000000]
    final_sizes = [100000, 500000, 1000000, 5000000, 10000000]
    delays = [0.0, 0.0001, 0.0005, 0.001, 0.002, 0.005, 0.010]
    timeouts = [5, 10, 15, 20, 30, 60, 120, 240]
    
    selected_idx = 0
    
    while True:
        terminal_ui.render_settings_menu(
            selected_idx,
            settings['array_size'],
            settings['knockouts_size'],
            settings['final_size'],
            settings['visual_delay'],
            settings['group_timeout'],
            settings['ko_timeout'],
            settings['final_timeout'],
            settings['autoplay']
        )
        
        key = terminal_ui.read_key(block=True)
        if key == 'up' or key == 'k':
            selected_idx = (selected_idx - 1) % 9
        elif key == 'down' or key == 'j':
            selected_idx = (selected_idx + 1) % 9
        elif key == 'left' or key == 'h':
            if selected_idx == 0:
                settings['array_size'] = get_next_preset(settings['array_size'], array_sizes, -1)
            elif selected_idx == 1:
                settings['knockouts_size'] = get_next_preset(settings['knockouts_size'], knockouts_sizes, -1)
            elif selected_idx == 2:
                settings['final_size'] = get_next_preset(settings['final_size'], final_sizes, -1)
            elif selected_idx == 3:
                settings['visual_delay'] = get_next_preset(settings['visual_delay'], delays, -1)
            elif selected_idx == 4:
                settings['group_timeout'] = get_next_preset(settings['group_timeout'], timeouts, -1)
            elif selected_idx == 5:
                settings['ko_timeout'] = get_next_preset(settings['ko_timeout'], timeouts, -1)
            elif selected_idx == 6:
                settings['final_timeout'] = get_next_preset(settings['final_timeout'], timeouts, -1)
            elif selected_idx == 7:
                settings['autoplay'] = not settings['autoplay']
        elif key == 'right' or key == 'l':
            if selected_idx == 0:
                settings['array_size'] = get_next_preset(settings['array_size'], array_sizes, 1)
            elif selected_idx == 1:
                settings['knockouts_size'] = get_next_preset(settings['knockouts_size'], knockouts_sizes, 1)
            elif selected_idx == 2:
                settings['final_size'] = get_next_preset(settings['final_size'], final_sizes, 1)
            elif selected_idx == 3:
                settings['visual_delay'] = get_next_preset(settings['visual_delay'], delays, 1)
            elif selected_idx == 4:
                settings['group_timeout'] = get_next_preset(settings['group_timeout'], timeouts, 1)
            elif selected_idx == 5:
                settings['ko_timeout'] = get_next_preset(settings['ko_timeout'], timeouts, 1)
            elif selected_idx == 6:
                settings['final_timeout'] = get_next_preset(settings['final_timeout'], timeouts, 1)
            elif selected_idx == 7:
                settings['autoplay'] = not settings['autoplay']
        elif key == 'enter':
            if selected_idx == 0:
                new_val = prompt_custom_value("Enter custom Group Array Size", int)
                if new_val is not None: settings['array_size'] = new_val
            elif selected_idx == 1:
                new_val = prompt_custom_value("Enter custom Knockouts Array Size", int)
                if new_val is not None: settings['knockouts_size'] = new_val
            elif selected_idx == 2:
                new_val = prompt_custom_value("Enter custom Final Array Size", int)
                if new_val is not None: settings['final_size'] = new_val
            elif selected_idx == 3:
                new_val = prompt_custom_value("Enter custom Simulation Delay in seconds (e.g., 0.001)", float)
                if new_val is not None: settings['visual_delay'] = new_val
            elif selected_idx == 4:
                new_val = prompt_custom_value("Enter custom Group Stage Timeout in seconds (max 240)", int)
                if new_val is not None: settings['group_timeout'] = min(240, new_val)
            elif selected_idx == 5:
                new_val = prompt_custom_value("Enter custom Knockout Stage Timeout in seconds (max 240)", int)
                if new_val is not None: settings['ko_timeout'] = min(240, new_val)
            elif selected_idx == 6:
                new_val = prompt_custom_value("Enter custom Final Stage Timeout in seconds (max 240)", int)
                if new_val is not None: settings['final_timeout'] = min(240, new_val)
            elif selected_idx == 7:
                settings['autoplay'] = not settings['autoplay']
            elif selected_idx == 8:
                break

def run_exhibition_match(idx, algos, settings, rng):
    """Runs a legendary showcase duel between selected algorithms."""
    if idx == 0:
        a_name, b_name = "Quick Sort", "Merge Sort"
        size = 5000
    elif idx == 1:
        a_name, b_name = "Timsort", "IntroSort"
        size = 5000
    elif idx == 2:
        a_name, b_name = "Bogo Sort", "Stooge Sort"
        size = 6  # Force small size so bogo can finish
    else:
        return
        
    algoA = next(a for a in algos if a['name'] == a_name)
    algoB = next(a for a in algos if a['name'] == b_name)
    
    terminal_ui.clear_screen()
    print(terminal_ui.draw_simple_header("EXHIBITION MATCH"))
    
    sorting_world_cup.play_match(
        algoA, algoB, "Legendary Exhibition", rng, 'exhibition',
        size, settings['visual_delay'], settings['timeout'],
        algo_list=algos
    )
    
    print("\n  Exhibition complete! Press Enter to return...")
    while True:
        if terminal_ui.read_key(block=True) == 'enter':
            break

def run_battle_royale(algos, settings, rng):
    """Runs an 8-way concurrent sorting Battle Royale with vertical progress visualization."""
    names = ["IntroSort", "Timsort", "Merge Sort", "Quick Sort", "3-Way Quick Sort", "Heap Sort", "Counting Sort", "Radix Sort (LSD)"]
    selected_algos = [a for a in algos if a['name'] in names]
    
    size = 5000
    input_arr = sorting_world_cup.make_input(1, size, rng)  # Randomized
    
    states = [sorting_world_cup.VisualState(a['name']) for a in selected_algos]
    cancel_events = [threading.Event() for _ in range(8)]
    pause_events = [threading.Event() for _ in range(8)]
    accumulators = [sorting_world_cup.Accumulator() for _ in range(8)]
    
    threads = []
    for idx, a in enumerate(selected_algos):
        t = threading.Thread(
            target=sorting_world_cup.run_sorter,
            args=(a['sort'], input_arr, states[idx], cancel_events[idx], pause_events[idx], accumulators[idx], settings['visual_delay'])
        )
        threads.append(t)
        
    for t in threads:
        t.start()
        
    start_time = time.perf_counter()
    timeout = settings['timeout']
    
    while True:
        all_done = True
        now = time.perf_counter()
        elapsed = now - start_time
        elapsed_ms = int(elapsed * 1000)
        
        for idx, st in enumerate(states):
            with st.lock:
                done = st.done
            if not done:
                all_done = False
                with st.lock:
                    st.elapsed_ms = elapsed_ms
                    
            if elapsed > timeout and not done:
                cancel_events[idx].set()
                
        terminal_ui.render_exhibition_battle_royale(states, "Randomized Array", elapsed_ms, size)
        
        if all_done:
            break
            
        time.sleep(0.1)
        
    for t in threads:
        t.join()
        
    terminal_ui.render_exhibition_battle_royale(states, "Randomized Array", elapsed_ms, size)
    
    print("\n  Battle Royale complete! Press Enter to return...")
    while True:
        if terminal_ui.read_key(block=True) == 'enter':
            break

def run_exhibitions(algos, settings, rng):
    """Controller for the exhibition side-events sub-menu."""
    selected_idx = 0
    while True:
        terminal_ui.render_exhibition_menu(selected_idx)
        key = terminal_ui.read_key(block=True)
        if key == 'up' or key == 'k':
            selected_idx = (selected_idx - 1) % 5
        elif key == 'down' or key == 'j':
            selected_idx = (selected_idx + 1) % 5
        elif key == 'enter':
            if selected_idx == 4:
                break
            elif selected_idx == 3:
                run_battle_royale(algos, settings, rng)
            else:
                run_exhibition_match(selected_idx, algos, settings, rng)

def run_scenario_strengths(algos):
    """Displays the scenario performance heatmap rankings."""
    perf = database.get_scenario_performance()
    algo_names = [a['name'] for a in algos]
    
    page = 0
    while True:
        terminal_ui.render_scenario_strengths_view(perf, algo_names, page=page)
        k = terminal_ui.read_key(block=True)
        if k == 'enter':
            break
        elif k == 'left' or k == 'h':
            page = 0
        elif k == 'right' or k == 'l':
            page = 1

def run_hall_of_fame():
    """Scrolls through the Hall of Fame champ records."""
    hof = database.get_hall_of_fame()
    while True:
        terminal_ui.render_hall_of_fame_view(hof)
        k = terminal_ui.read_key(block=True)
        if k == 'enter':
            break

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(run_self_test())
        
    # Database migration/init
    database.init_db()
    
    import atexit
    atexit.register(terminal_ui.restore_terminal)
    
    terminal_ui.init_terminal()
    try:
        algos = sorting_world_cup.get_algorithms()
        settings = {
            'array_size': 100000,
            'knockouts_size': 1000000,
            'final_size': 10000000,
            'visual_delay': 0.0,
            'group_timeout': 30,
            'ko_timeout': 60,
            'final_timeout': 240,
            'autoplay': False
        }
        
        tournament = sorting_world_cup.Tournament(
            algos,
            array_size=settings['array_size'],
            knockouts_size=settings['knockouts_size'],
            final_size=settings['final_size'],
            visual_delay=settings['visual_delay'],
            group_timeout=settings['group_timeout'],
            ko_timeout=settings['ko_timeout'],
            final_timeout=settings['final_timeout'],
            autoplay=settings['autoplay']
        )
        
        if database.has_saved_tournament():
            success = database.load_tournament(tournament)
            if success:
                settings['array_size'] = tournament.array_size
                settings['knockouts_size'] = tournament.knockouts_size
                settings['final_size'] = tournament.final_size
                settings['visual_delay'] = tournament.visual_delay
                settings['group_timeout'] = tournament.group_timeout
                settings['ko_timeout'] = tournament.ko_timeout
                settings['final_timeout'] = tournament.final_timeout
                settings['autoplay'] = getattr(tournament, 'autoplay', False)
        
        menu_options = [
            "1. Tournament Initialization / Group Draw",
            "2. Scheduling of Matches",
            "3. Play Tournament",
            "4. Points Table",
            "5. Bracket View",
            "6. Consolidated Points Tables",
            "7. World Rating Board",
            "8. Tournament History Archives",
            "9. Legendary Exhibition Matches",
            "10. Scenario Strengths / Heatmaps",
            "11. Hall of Fame",
            "12. Settings / Calibration",
            "13. Start Next Year / Season Reset",
            "14. Save Tournament State",
            "15. Load Tournament State",
            "16. Exit"
        ]
        selected_menu_idx = 0
        
        while True:
            tournament.array_size = settings['array_size']
            tournament.knockouts_size = settings['knockouts_size']
            tournament.final_size = settings['final_size']
            tournament.visual_delay = settings['visual_delay']
            tournament.group_timeout = settings['group_timeout']
            tournament.ko_timeout = settings['ko_timeout']
            tournament.final_timeout = settings['final_timeout']
            tournament.autoplay = settings['autoplay']
            
            terminal_ui.render_main_menu(
                menu_options,
                selected_menu_idx,
                settings['array_size'],
                settings['visual_delay'],
                settings['group_timeout']
            )
            
            key = terminal_ui.read_key(block=True)
            if key == 'up' or key == 'k':
                selected_menu_idx = (selected_menu_idx - 1) % len(menu_options)
            elif key == 'down' or key == 'j':
                selected_menu_idx = (selected_menu_idx + 1) % len(menu_options)
            elif key == 'enter':
                if selected_menu_idx == 0:  # Group Draw
                    tournament.draw_groups(animated=True)
                    database.save_tournament(tournament)
                    print("\n  Group Draw complete! Press Enter to return to main menu...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 1:  # Scheduling of Matches (Paginated, 2 pages)
                    page = 0
                    while True:
                        terminal_ui.render_fixtures_view(tournament.fixtures, [a['name'] for a in algos], page=page)
                        k = terminal_ui.read_key(block=True)
                        if k == 'enter':
                            break
                        elif k == 'left' or k == 'h':
                            page = 0
                        elif k == 'right' or k == 'l':
                            page = 1
                elif selected_menu_idx == 2:  # Play Tournament
                    if tournament.current_stage == "Group Stage":
                        tournament.play_group_stage()
                    tournament.play_knockouts()
                elif selected_menu_idx == 3:  # Points Table
                    page = 0
                    while True:
                        terminal_ui.render_standings_view(tournament.standings, [a['name'] for a in algos], page=page)
                        k = terminal_ui.read_key(block=True)
                        if k == 'enter':
                            break
                        elif k == 'left' or k == 'h':
                            page = 0
                        elif k == 'right' or k == 'l':
                            page = 1
                elif selected_menu_idx == 4:  # Bracket View
                    bracket = []
                    if tournament.current_bracket:
                        bracket = tournament.current_bracket
                    elif any(s['played'] > 0 for s in tournament.standings):
                        try:
                            bracket = tournament.qualified()
                        except Exception:
                            pass
                    stage_title = tournament.current_stage if tournament.current_stage != "Group Stage" else "ROUND OF 16"
                    terminal_ui.render_bracket_view(bracket, stage_title if bracket else "NOT AVAILABLE", [a['name'] for a in algos])
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 5:  # Consolidated Points Tables
                    # Build current season consolidated list combining group + knockout stats
                    current_list = []
                    for s in tournament.standings:
                        played = s['played'] + s.get('ko_played', 0)
                        points = s['points'] + s.get('ko_points', 0)
                        wins = s['matchWins'] + s.get('ko_matchWins', 0)
                        draws = s['matchDraws']
                        losses = s['matchLosses'] + s.get('ko_matchLosses', 0)
                        r_wins = s['roundWins'] + s.get('ko_roundWins', 0)
                        r_losses = s['roundLosses'] + s.get('ko_roundLosses', 0)
                        ns = s['ns'] + s.get('ko_ns', 0)
                        current_list.append({
                            'name': algos[s['algo']]['name'],
                            'played': played,
                            'points': points,
                            'matchWins': wins,
                            'matchDraws': draws,
                            'matchLosses': losses,
                            'roundWins': r_wins,
                            'roundLosses': r_losses,
                            'ns': ns
                        })
                    # Sort current season consolidated standings
                    current_list.sort(key=lambda x: (
                        -x['points'],
                        -x['matchWins'],
                        -(x['roundWins'] - x['roundLosses']),
                        x['ns']
                    ))
                    
                    # Load all-time consolidated list
                    hist_stats = database.get_historical_stats()
                    all_time_list = []
                    for a in algos:
                        name = a['name']
                        stats = hist_stats.get(name, {
                            'played': 0, 'won': 0, 'lost': 0, 'draws': 0, 'points': 0,
                            'round_wins': 0, 'round_losses': 0, 'total_sorted_time_ns': 0,
                            'total_sorted_rounds': 0
                        })
                        all_time_list.append({
                            'name': name,
                            'played': stats.get('played', 0),
                            'points': stats.get('points', 0),
                            'matchWins': stats.get('won', 0),
                            'matchDraws': stats.get('draws', 0),
                            'matchLosses': stats.get('lost', 0),
                            'roundWins': stats.get('round_wins', 0),
                            'roundLosses': stats.get('round_losses', 0),
                            'total_sorted_time_ns': stats.get('total_sorted_time_ns', 0),
                            'total_sorted_rounds': stats.get('total_sorted_rounds', 0)
                        })
                    # Sort all-time consolidated standings
                    all_time_list.sort(key=lambda x: (
                        -x['points'],
                        -x['matchWins'],
                        -(x['roundWins'] - x['roundLosses']),
                        x['total_sorted_time_ns'] / x['total_sorted_rounds'] if x['total_sorted_rounds'] > 0 else 999999999999
                    ))
                    
                    page = 0
                    while True:
                        terminal_ui.render_consolidated_standings(current_list, all_time_list, page=page)
                        k = terminal_ui.read_key(block=True)
                        if k == 'enter':
                            break
                        elif k == 'left' or k == 'h':
                            page = (page - 1) % 4
                        elif k == 'right' or k == 'l':
                            page = (page + 1) % 4
                elif selected_menu_idx == 6:  # World Rating Board
                    ratings = database.get_elo_ratings()
                    hist_stats = database.get_historical_stats()
                    
                    ratings_list = []
                    for a in algos:
                        name = a['name']
                        stats = hist_stats.get(name, {
                            'played': 0, 'won': 0, 'lost': 0, 'total_sorted_time_ns': 0,
                            'total_sorted_rounds': 0
                        })
                        ratings_list.append({
                            'name': name,
                            'elo': ratings.get(name, 1500.0),
                            'played': stats.get('played', 0),
                            'won': stats.get('won', 0),
                            'lost': stats.get('lost', 0),
                            'total_sorted_time_ns': stats.get('total_sorted_time_ns', 0),
                            'total_sorted_rounds': stats.get('total_sorted_rounds', 0)
                        })
                    ratings_list.sort(key=lambda x: -x['elo'])
                    
                    page = 0
                    while True:
                        terminal_ui.render_rating_board(ratings_list, page=page)
                        k = terminal_ui.read_key(block=True)
                        if k == 'enter':
                            break
                        elif k == 'left' or k == 'h':
                            page = 0
                        elif k == 'right' or k == 'l':
                            page = 1
                elif selected_menu_idx == 7:  # Tournament History Archives
                    seasons = database.get_archived_seasons()
                    selected_year_idx = 0
                    
                    while True:
                        terminal_ui.render_archives_years_list(seasons, selected_year_idx)
                        k = terminal_ui.read_key(block=True)
                        
                        if k == 'up' or k == 'k':
                            if seasons:
                                selected_year_idx = (selected_year_idx - 1) % (len(seasons) + 1)
                            else:
                                selected_year_idx = 0
                        elif k == 'down' or k == 'j':
                            if seasons:
                                selected_year_idx = (selected_year_idx + 1) % (len(seasons) + 1)
                            else:
                                selected_year_idx = 0
                        elif k == 'enter':
                            if selected_year_idx == len(seasons) or not seasons:
                                break
                            else:
                                selected_year, champ = seasons[selected_year_idx]
                                archive_details = database.get_archived_season_details(selected_year)
                                if archive_details:
                                    detail_idx = 0
                                    while True:
                                        terminal_ui.render_archive_details_menu(selected_year, champ, detail_idx)
                                        det_k = terminal_ui.read_key(block=True)
                                        if det_k == 'up' or det_k == 'k':
                                            detail_idx = (detail_idx - 1) % 3
                                        elif det_k == 'down' or det_k == 'j':
                                            detail_idx = (detail_idx + 1) % 3
                                        elif det_k == 'enter':
                                            if detail_idx == 0:
                                                page = 0
                                                while True:
                                                    terminal_ui.render_standings_view(archive_details['standings'], [a['name'] for a in algos], page=page)
                                                    st_k = terminal_ui.read_key(block=True)
                                                    if st_k == 'enter':
                                                        break
                                                    elif st_k == 'left' or st_k == 'h':
                                                        page = 0
                                                    elif st_k == 'right' or st_k == 'l':
                                                        page = 1
                                            elif detail_idx == 1:
                                                terminal_ui.render_bracket_view(archive_details['bracket'], "Finished", [a['name'] for a in algos])
                                                while True:
                                                    if terminal_ui.read_key(block=True) == 'enter':
                                                        break
                                            elif detail_idx == 2:
                                                break
                elif selected_menu_idx == 8:  # Legendary Exhibition Matches
                    run_exhibitions(algos, settings, tournament.rng)
                elif selected_menu_idx == 9:  # Scenario Strengths
                    run_scenario_strengths(algos)
                elif selected_menu_idx == 10:  # Hall of Fame
                    run_hall_of_fame()
                elif selected_menu_idx == 11:  # Settings
                    run_settings(settings)
                elif selected_menu_idx == 12:  # Start Next Year / Season Reset
                    terminal_ui.clear_screen()
                    header = terminal_ui.draw_trophy_header("SEASON RESET")
                    box = terminal_ui.draw_box(
                        "CONFIRM RESET",
                        [
                            "",
                            f"  Are you sure you want to skip to Year {tournament.year + 1}?",
                            "  This will archive the current standing progress and reset the board.",
                            "",
                            "  Press [Y] to confirm or [N] to cancel."
                        ],
                        width=76,
                        color=terminal_ui.RED
                    )
                    terminal_ui.write_screen(header + "\n" + box)
                    confirmed = False
                    while True:
                        k = terminal_ui.read_key(block=True)
                        if k == 'y':
                            confirmed = True
                            break
                        elif k == 'n':
                            break
                    if confirmed:
                        current_list = []
                        for s in tournament.standings:
                            current_list.append({
                                'algo': s['algo'],
                                'points': s['points'] + s.get('ko_points', 0)
                            })
                        current_list.sort(key=lambda x: -x['points'])
                        leader_name = algos[current_list[0]['algo']]['name'] if current_list else "None"
                        
                        tournament.reset_season(champ_name=leader_name)
                        
                        terminal_ui.clear_screen()
                        box = terminal_ui.draw_box(
                            "RESET SUCCESSFUL",
                            ["", f"  Successfully advanced to Season Year {tournament.year}!", ""],
                            width=76,
                            color=terminal_ui.GREEN
                        )
                        terminal_ui.write_screen(header + "\n" + box + "\n\n  Press Enter to return to main menu...")
                        while True:
                            if terminal_ui.read_key(block=True) == 'enter':
                                break
                elif selected_menu_idx == 13:  # Save State
                    database.save_tournament(tournament)
                    terminal_ui.clear_screen()
                    header = terminal_ui.draw_trophy_header("SAVE SUCCESSFUL")
                    box = terminal_ui.draw_box(
                        "SAVE STATUS",
                        ["", "  Tournament state successfully saved to SQLite database!", ""],
                        width=76,
                        color=terminal_ui.GREEN
                    )
                    terminal_ui.write_screen(header + "\n" + box + "\n\n  Press Enter to return to main menu...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 14:  # Load State
                    success = database.load_tournament(tournament)
                    terminal_ui.clear_screen()
                    header = terminal_ui.draw_trophy_header("LOAD RESULT")
                    if success:
                        settings['array_size'] = tournament.array_size
                        settings['knockouts_size'] = tournament.knockouts_size
                        settings['final_size'] = tournament.final_size
                        settings['visual_delay'] = tournament.visual_delay
                        settings['group_timeout'] = tournament.group_timeout
                        settings['ko_timeout'] = tournament.ko_timeout
                        settings['final_timeout'] = tournament.final_timeout
                        msg = "  Tournament state successfully loaded from SQLite database!"
                        color = terminal_ui.GREEN
                    else:
                        msg = "  Error: No saved tournament state found in database."
                        color = terminal_ui.RED
                    box = terminal_ui.draw_box("LOAD STATUS", ["", msg, ""], width=76, color=color)
                    terminal_ui.write_screen(header + "\n" + box + "\n\n  Press Enter to return to main menu...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 15:  # Exit
                    break
 
    finally:
        terminal_ui.restore_terminal()
        print("Exiting Sorting World Cup. Goodbye!")

if __name__ == "__main__":
    main()
