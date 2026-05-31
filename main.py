import sys
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
            
            # Wait up to 2 seconds
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
        
        # Wait up to 15.0 seconds
        worker.join(timeout=15.0)
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

def run_settings(settings):
    """Sub-menu for modifying running settings."""
    array_sizes = [1000, 5000, 10000, 50000, 100000]
    active_size_idx = array_sizes.index(settings['array_size']) if settings['array_size'] in array_sizes else 4
    
    delays = [0.0, 0.0001, 0.0005, 0.001, 0.002, 0.005, 0.010]
    active_delay_idx = delays.index(settings['visual_delay']) if settings['visual_delay'] in delays else 0
    
    timeouts = [1, 2, 5, 10, 15, 20, 30]
    active_timeout_idx = timeouts.index(settings['timeout']) if settings['timeout'] in timeouts else 2
    
    selected_idx = 0
    
    while True:
        terminal_ui.render_settings_menu(
            selected_idx,
            array_sizes, active_size_idx,
            delays, active_delay_idx,
            timeouts, active_timeout_idx
        )
        
        key = terminal_ui.read_key(block=True)
        if key == 'up' or key == 'k':
            selected_idx = (selected_idx - 1) % 4
        elif key == 'down' or key == 'j':
            selected_idx = (selected_idx + 1) % 4
        elif key == 'left' or key == 'h':
            if selected_idx == 0:
                active_size_idx = (active_size_idx - 1) % len(array_sizes)
                settings['array_size'] = array_sizes[active_size_idx]
            elif selected_idx == 1:
                active_delay_idx = (active_delay_idx - 1) % len(delays)
                settings['visual_delay'] = delays[active_delay_idx]
            elif selected_idx == 2:
                active_timeout_idx = (active_timeout_idx - 1) % len(timeouts)
                settings['timeout'] = timeouts[active_timeout_idx]
        elif key == 'right' or key == 'l':
            if selected_idx == 0:
                active_size_idx = (active_size_idx + 1) % len(array_sizes)
                settings['array_size'] = array_sizes[active_size_idx]
            elif selected_idx == 1:
                active_delay_idx = (active_delay_idx + 1) % len(delays)
                settings['visual_delay'] = delays[active_delay_idx]
            elif selected_idx == 2:
                active_timeout_idx = (active_timeout_idx + 1) % len(timeouts)
                settings['timeout'] = timeouts[active_timeout_idx]
        elif key == 'enter':
            if selected_idx == 3: # Back
                break

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(run_self_test())
        
    import atexit
    atexit.register(terminal_ui.restore_terminal)
    
    terminal_ui.init_terminal()
    try:
        algos = sorting_world_cup.get_algorithms()
        settings = {
            'array_size': 100000,
            'visual_delay': 0.0,
            'timeout': 5
        }
        
        # Initialize tournament instance
        tournament = sorting_world_cup.Tournament(
            algos,
            array_size=settings['array_size'],
            visual_delay=settings['visual_delay'],
            timeout=settings['timeout']
        )
        
        # Resume session check
        if database.has_saved_tournament():
            while True:
                terminal_ui.render_resume_prompt()
                key = terminal_ui.read_key(block=True)
                if key == 'y':
                    success = database.load_tournament(tournament)
                    if success:
                        settings['array_size'] = tournament.array_size
                        settings['visual_delay'] = tournament.visual_delay
                        settings['timeout'] = tournament.timeout
                    break
                elif key == 'n':
                    # Start fresh (default initialization already drew groups)
                    break
        
        menu_options = [
            "1. Tournament Initialization / Group Draw",
            "2. Scheduling of Matches",
            "3. Play Tournament",
            "4. Points Table",
            "5. Bracket View",
            "6. Settings / Calibration",
            "7. Save Tournament State",
            "8. Load Tournament State",
            "9. Exit"
        ]
        selected_menu_idx = 0
        
        while True:
            # Update tournament parameters from settings
            tournament.array_size = settings['array_size']
            tournament.visual_delay = settings['visual_delay']
            tournament.timeout = settings['timeout']
            
            terminal_ui.render_main_menu(
                menu_options,
                selected_menu_idx,
                settings['array_size'],
                settings['visual_delay'],
                settings['timeout']
            )
            
            key = terminal_ui.read_key(block=True)
            if key == 'up' or key == 'k':
                selected_menu_idx = (selected_menu_idx - 1) % len(menu_options)
            elif key == 'down' or key == 'j':
                selected_menu_idx = (selected_menu_idx + 1) % len(menu_options)
            elif key == 'enter':
                if selected_menu_idx == 0:  # Group Draw
                    tournament.draw_groups(animated=True)
                    database.save_tournament(tournament)  # Auto-save after group draw
                    print("\n  Group Draw complete! Press Enter to return to main menu...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 1:  # Scheduling of Matches
                    header = terminal_ui.draw_trophy_header("SCHEDULED FIXTURES")
                    content = []
                    for g in range(8):
                        content.append(f"{terminal_ui.BOLD}{terminal_ui.GOLD}GROUP {chr(ord('A') + g)} fixtures:{terminal_ui.RESET}")
                        local_idx = 1
                        for f in tournament.fixtures:
                            if f['group'] != g:
                                continue
                            nameA = algos[f['a']]['name']
                            nameB = algos[f['b']]['name']
                            content.append(f"  {local_idx}. {nameA:<24} vs {nameB:<24}")
                            local_idx += 1
                        content.append("")
                    box = terminal_ui.draw_box("LOTTERY FIXTURES", content, width=76, color=terminal_ui.BLUE)
                    terminal_ui.write_screen(header + "\n" + box + "\n\n  Press Enter to return to main menu...")
                    while True:
                        if terminal_ui.read_key(block=True) == 'enter':
                            break
                elif selected_menu_idx == 2:  # Play Tournament
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
                elif selected_menu_idx == 5:  # Settings
                    run_settings(settings)
                elif selected_menu_idx == 6:  # Save State
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
                elif selected_menu_idx == 7:  # Load State
                    success = database.load_tournament(tournament)
                    terminal_ui.clear_screen()
                    header = terminal_ui.draw_trophy_header("LOAD RESULT")
                    if success:
                        settings['array_size'] = tournament.array_size
                        settings['visual_delay'] = tournament.visual_delay
                        settings['timeout'] = tournament.timeout
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
                elif selected_menu_idx == 8:  # Exit
                    break

    finally:
        terminal_ui.restore_terminal()
        print("Exiting Sorting World Cup. Goodbye!")

if __name__ == "__main__":
    main()
