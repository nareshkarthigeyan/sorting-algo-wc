import os
import sys
import time
import select
import tty
import termios
import contextlib
import math

# --- ANSI TrueColor Definitions ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Premium palette (Slate-900 theme with cyan, violet, green accents)
BG = "\033[48;2;15;23;42m"          # Slate 900
BG_CARD = "\033[48;2;30;41;59m"     # Slate 800
BG_HOT = "\033[48;2;51;65;85m"       # Slate 700

FG = "\033[38;2;248;250;252m"       # Slate 50
FG_MUTED = "\033[38;2;148;163;184m" # Slate 400
FG_DARK = "\033[38;2;71;85;105m"    # Slate 600

CYAN = "\033[38;2;34;211;238m"      # Cyan 400
BLUE = "\033[38;2;96;165;250m"      # Blue 400
VIOLET = "\033[38;2;192;132;252m"   # Violet 400
GREEN = "\033[38;2;52;211;153m"     # Emerald 400
RED = "\033[38;2;248;113;113m"      # Red 400
AMBER = "\033[38;2;251;191;36m"     # Amber 400
GOLD = "\033[38;2;234;179;8m"       # Yellow 500

HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR = "\033[2J"
HOME = "\033[H"

def init_terminal():
    """Switches to alternate screen buffer and hides cursor to prevent scrolling/trails."""
    sys.stdout.write("\033[?1049h" + HIDE_CURSOR)
    sys.stdout.flush()

def restore_terminal():
    """Restores main screen buffer and restores cursor."""
    sys.stdout.write(SHOW_CURSOR + "\033[?1049l")
    sys.stdout.flush()

def write_screen(text):
    """Flicker-free single-pass write to the top-left of terminal, clearing leftovers."""
    sys.stdout.write(HOME + "\033[J" + text)
    sys.stdout.flush()

@contextlib.contextmanager
def raw_mode():
    """Temporarily enables raw terminal input mode for non-blocking key reads."""
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        yield
        return
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def read_key(block=True):
    """Reads a single key or key sequence. Blocks by default, or returns None if block=False and no key is pressed."""
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        # Fallback to simple input if not a TTY
        line = sys.stdin.readline()
        return line.strip() if line else None

    timeout = None if block else 0.05
    with raw_mode():
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            # Check for multi-byte escape sequences (e.g. arrow keys)
            # Use 50ms timeout to ensure we don't drop slow terminal bytes
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                return 'esc'
            ch2 = sys.stdin.read(1)
            if ch2 in ('[', 'O'):
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r:
                    return 'esc'
                ch3 = sys.stdin.read(1)
                if ch3 == 'A': return 'up'
                elif ch3 == 'B': return 'down'
                elif ch3 == 'C': return 'right'
                elif ch3 == 'D': return 'left'
            return 'esc'
        elif ch in ('\r', '\n'):
            return 'enter'
        elif ch == ' ':
            return 'space'
        elif ch == '\x7f':  # Backspace on mac
            return 'backspace'
        elif ch == '\x03':  # Ctrl-C
            raise KeyboardInterrupt()
        return ch.lower()


def clear_screen():
    write_screen("")

def get_term_size():
    try:
        columns, lines = os.get_terminal_size()
        return columns, lines
    except OSError:
        return 80, 24

# --- Block Graph Drawing Helpers ---
BLOCKS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

def get_block_char(val, min_v, max_v):
    if max_v == min_v:
        return BLOCKS[-1]
    norm = (val - min_v) / (max_v - min_v)
    idx = math.floor(norm * (len(BLOCKS) - 1))
    idx = max(0, min(len(BLOCKS) - 1, idx))
    return BLOCKS[idx]

def make_bar_graph(values, width=32):
    """Generates a list of single-character blocks representing array values."""
    if not values:
        return " " * width
    
    # Resample values to fit the exact width
    n = len(values)
    resampled = []
    for i in range(width):
        idx = min(n - 1, (i * (n - 1)) // max(1, width - 1))
        resampled.append(values[idx])
    
    min_v = min(values)
    max_v = max(values)
    
    return "".join(get_block_char(x, min_v, max_v) for x in resampled)

def make_sortedness_bar(percentage, width=20):
    """Renders a color-coded percentage bar."""
    filled = int((percentage / 100.0) * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    
    # Select color based on progress
    if percentage < 30:
        color = RED
    elif percentage < 70:
        color = AMBER
    else:
        color = GREEN
        
    return f"{color}{'█' * filled}{FG_DARK}{'░' * empty}{RESET} {BOLD}{percentage:3.0f}%{RESET}"

# --- Visual Layout Helpers ---
def draw_trophy_header(subtitle=""):
    ascii_cup = [
        "      ___________        .-=========-.        ___________",
        "     '._==_==_=_.'      /             \\      '._=_==_==_.'",
        "     .-\\:      /-.     /   SORTING     \\     .-\\      :/-.",
        "    | (|:.     |) |   |   WORLD CUP     |   | (|     .:|) |",
        "     '-|:.     |-'     \\     2026      /     '-|     .:|-'",
        "       \\::.    /        '-=========-'        \\    .::/",
        "        '::. .'                               '. .::'",
        "          ) (                                   ) (",
        "        _.' '._                               _.' '._",
        "       `\"\"\"\"\"\"\"`                             `\"\"\"\"\"\"\"`"
    ]
    lines = []
    lines.append(f"{GOLD}")
    for line in ascii_cup:
        lines.append(line)
    lines.append(f"{RESET}")
    
    if subtitle:
        width = 65
        padding = max(0, (width - len(subtitle)) // 2)
        lines.append(f"{BOLD}{CYAN}{' ' * padding}{subtitle}{RESET}\n")
    return "\n".join(lines)

def draw_simple_header(subtitle=""):
    if not subtitle:
        return ""
    width = 76
    title_str = f" {BOLD}{CYAN}{subtitle.upper()}{RESET} "
    raw_len = len(subtitle) + 2
    pad_left = (width - raw_len) // 2
    pad_right = width - raw_len - pad_left
    return f"\n{GOLD}{'═' * pad_left}{RESET}{title_str}{GOLD}{'═' * pad_right}{RESET}\n"

def draw_box(title, content_lines, width=76, color=BLUE):
    """Draws a rounded Unicode box around lines of text."""
    box_lines = []
    # Title formatting
    title_str = f" {title} " if title else ""
    rem = width - len(title_str) - 2
    top = f"{color}╭{title_str.center(width - 2, '─')}{color}╮{RESET}"
    box_lines.append(top)
    
    for line in content_lines:
        # Strip ANSI codes to calculate actual length
        stripped_len = len(ansi_strip(line))
        pad = max(0, width - 2 - stripped_len)
        box_lines.append(f"{color}│{RESET} {line}{' ' * pad}{color}│{RESET}")
        
    bot = f"{color}╰{'─' * (width - 2)}╯{RESET}"
    box_lines.append(bot)
    return "\n".join(box_lines)

def ansi_strip(text):
    """Removes ANSI control sequences from a string for text length calculations."""
    import re
    return re.sub(r'\033\[[0-9;]*[a-zA-Z]', '', text)

def render_resume_prompt():
    """Renders a beautiful prompt asking the user if they want to resume a saved tournament."""
    header = draw_trophy_header("RESTORE SESSION")
    content = [
        " A saved tournament state has been detected in the database.",
        " You can resume the saved session or start a new tournament.",
        "",
        f"  {CYAN}▶ Resume Saved Tournament? (Y/N){RESET}",
        "",
        f"  {FG_MUTED}Press Y to Resume / Press N to Start Fresh and Delete Save{RESET}",
        ""
    ]
    box = draw_box("RESTORE TOURNAMENT PROGRESS", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

# --- Specific Screens ---


def render_main_menu(options, selected_idx, array_size, delay, timeout):
    """Renders the main menu dashboard with options and settings information."""
    header = draw_trophy_header("MAIN MENU")
    
    content = [
        f"  Welcome to the {BOLD}{GOLD}Sorting Algorithm World Cup 2026{RESET}!",
        f"  Run 32 sorting algorithms in group stage round-robins and knockout brackets.",
        "",
        f"  {FG_MUTED}Active Configuration:{RESET}",
        f"    • Array Size:     {CYAN}{array_size:,}{RESET} values",
        f"    • Simulation Delay: {AMBER}{delay * 1000:.0f} ms{RESET} per visual check",
        f"    • Group Timeout:  {RED}{timeout} seconds{RESET}",
        "",
        f"  {FG_MUTED}Use Arrow keys (↑/↓) or (J/K) to select and press Enter:{RESET}",
        ""
    ]
    
    for i, opt in enumerate(options):
        if i == selected_idx:
            content.append(f"    {CYAN}▶ {BOLD}{UNDERLINE}{opt}{RESET}")
        else:
            content.append(f"      {opt}")
            
    content.append("")
    box = draw_box("TOURNAMENT TRACKS", content, width=76, color=BLUE)
    write_screen(header + "\n" + box)

def render_settings_menu(selected_idx, array_sizes, active_size_idx, delays, active_delay_idx, timeouts, active_timeout_idx):
    """Renders an interactive settings modifier screen."""
    header = draw_trophy_header("SETTINGS")
    
    opts = [
        ("Array Size", f"{array_sizes[active_size_idx]:,} elements"),
        ("Simulation Delay", f"{delays[active_delay_idx] * 1000:.0f} ms"),
        ("Match Timeout", f"{timeouts[active_timeout_idx]} seconds"),
        ("Back to Main Menu", "")
    ]
    
    content = [
        "Customize tournament mechanics to observe slower algorithms or run faster races.",
        f"Use {CYAN}Arrow Keys (←/→){RESET} to change values of the selected setting.",
        ""
    ]
    
    for i, (name, val) in enumerate(opts):
        cursor = f"{CYAN}▶ {BOLD}" if i == selected_idx else "  "
        if val:
            line = f"{cursor}{name:<25} {AMBER}◀ {val:<12} ▶{RESET}"
        else:
            line = f"{cursor}{name}{RESET}"
        content.append(line)
        
    content.append("")
    box = draw_box("CONCURRENT STAGE DESIGN", content, width=76, color=VIOLET)
    write_screen(header + "\n" + box)

def render_bracket_view(bracket, current_stage, algo_names):
    """Draws a gorgeous ASCII representation of the knockout brackets."""
    header = draw_trophy_header("BRACKET STAGE")
    content = [
        f"Stage: {BOLD}{GOLD}{current_stage}{RESET}",
        "Top 2 from each group advanced into a single-elimination tournament.",
        ""
    ]
    if not bracket:
        content.append(f"  {RED}Bracket is not populated yet. Run the Group Stage first!{RESET}")
    else:
        for i in range(0, len(bracket), 2):
            left_algo = algo_names[bracket[i]]
            right_algo = algo_names[bracket[i+1]] if i+1 < len(bracket) else "CHAMPION"
            content.append(f"      ╭──────────────────────────────╮")
            content.append(f"   {i//2 + 1:2} │ {CYAN}{left_algo:<28}{RESET}│")
            content.append(f"      │              {FG_MUTED}VS{RESET}              │")
            content.append(f"      │ {VIOLET}{right_algo:<28}{RESET}│")
            content.append(f"      ╰──────────────────────────────╯")
            content.append("")
    content.append(f"Press {CYAN}Enter{RESET} to return...")
    box = draw_box("KNOCKOUT TREE STANDINGS", content, width=76, color=VIOLET)
    write_screen(header + "\n" + box)

def render_standings_view(standings, algo_names, page=0):
    """Renders the points tables for all 8 groups, split into two pages for clean layout."""
    header = draw_trophy_header("GROUP STANDINGS")
    groups_to_render = range(0, 4) if page == 0 else range(4, 8)
    
    content = []
    content.append(f"Showing Groups {chr(ord('A') + groups_to_render[0])}-{chr(ord('A') + groups_to_render[-1])}  |  Use {CYAN}← / → Arrows{RESET} to switch pages.")
    content.append(f"Press {CYAN}Enter{RESET} to exit to main menu.")
    content.append("")
    
    for g in groups_to_render:
        table_header = f"{BOLD}{GOLD}GROUP {chr(ord('A') + g)}{RESET}"
        content.append(table_header)
        # Table columns: Pos, Name, Played, Points, Wins, Draws, Losses, Round Wins (Diff)
        col_header = f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5}{RESET}"
        content.append(col_header)
        
        # Extract standings for this group
        group_stands = [s for s in standings if s['group'] == g]
        # Sort group standings: points, then matchWins, then round Diff, then nanoseconds
        group_stands.sort(key=lambda x: (
            -x['points'],
            -x['matchWins'],
            -(x['roundWins'] - x['roundLosses']),
            x['ns']
        ))
        
        for pos, s in enumerate(group_stands, 1):
            name = algo_names[s['algo']][:18]
            diff = s['roundWins'] - s['roundLosses']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            color_row = GREEN if pos <= 2 else RESET
            row = f"   {pos:<2} {color_row}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}"
            content.append(row)
        content.append("  " + "─" * 48)
        content.append("")
        
    box = draw_box("ROUND ROBIN SUMMARY", content, width=76, color=GREEN)
    write_screen(header + "\n" + box)

def render_group_draw(groups, algo_names, highlighted_group=-1, opening_pot=None):
    """Renders the lottery draw board where algorithms are assigned to groups."""
    subtitle = "GROUP DRAW LOTTERY"
    if opening_pot is not None:
        subtitle += f" - POT {opening_pot + 1}"
    header = draw_trophy_header(subtitle)
    
    # Render all 8 groups in a 4x2 grid
    # Groups are: A(0), B(1), C(2), D(3), E(4), F(5), G(6), H(7)
    grid_lines = []
    
    # We display groups in pairs: (A, B), (C, D), (E, F), (G, H)
    pairs = [(0, 1), (2, 3), (4, 5), (6, 7)]
    
    for g1, g2 in pairs:
        border1_color = CYAN if g1 == highlighted_group else BLUE
        border2_color = CYAN if g2 == highlighted_group else BLUE
        
        grid_lines.append(f"{border1_color}╭─ GROUP {chr(ord('A') + g1)} ─────────────────╮  {border2_color}╭─ GROUP {chr(ord('A') + g2)} ─────────────────╮")
        
        # Render slot items (up to 4 per group)
        for slot in range(4):
            item1 = algo_names[groups[g1][slot]][:25] if slot < len(groups[g1]) else "........................."
            item2 = algo_names[groups[g2][slot]][:25] if slot < len(groups[g2]) else "........................."
            
            c1 = GREEN if slot < len(groups[g1]) else FG_DARK
            c2 = GREEN if slot < len(groups[g2]) else FG_DARK
            
            grid_lines.append(f"{border1_color}│{RESET} {c1}{item1:<27}{RESET} {border1_color}│{RESET}  {border2_color}│{RESET} {c2}{item2:<27}{RESET} {border2_color}│")
            
        grid_lines.append(f"{border1_color}╰─────────────────────────────╯  {border2_color}╰─────────────────────────────╯")
        grid_lines.append("")
        
    write_screen(header + "\n" + "\n".join(grid_lines))

def format_ns(ns):
    if ns is None:
        return "N/A"
    return f"{ns / 1_000_000_000:.6f}s"
def draw_live_bracket_box(bracket, current_match_idx, stage_winners, algo_names, stage_title, current_winner_idx=None):
    if not bracket or current_match_idx is None:
        return ""
        
    lines = []
    num_matches = len(bracket) // 2
    for m in range(num_matches):
        a_idx = bracket[2 * m]
        b_idx = bracket[2 * m + 1]
        a_name = algo_names[a_idx] if a_idx < len(algo_names) else f"Algo {a_idx}"
        b_name = algo_names[b_idx] if b_idx < len(algo_names) else f"Algo {b_idx}"
        
        # Check if winner is decided
        winner = None
        if m < len(stage_winners):
            winner = stage_winners[m]
        elif m == current_match_idx and current_winner_idx is not None:
            winner = current_winner_idx
            
        if winner is not None:
            if winner == a_idx:
                winner_str = f"{BOLD}{GREEN}{a_name}{RESET}"
                loser_str = f"{FG_DARK}{b_name}{RESET}"
            elif winner == b_idx:
                winner_str = f"{FG_DARK}{a_name}{RESET}"
                loser_str = f"{BOLD}{GREEN}{b_name}{RESET}"
            else:
                winner_str = f"{FG_MUTED}{a_name}{RESET}"
                loser_str = f"{FG_MUTED}{b_name}{RESET}"
            lines.append(f"  {FG_MUTED}✓{RESET} Match {m+1:<2}: {winner_str} {FG_MUTED}def.{RESET} {loser_str}")
        elif m == current_match_idx:
            lines.append(f"  {BOLD}{CYAN}▶{RESET} Match {m+1:<2}: {BOLD}{CYAN}{a_name}{RESET} {BOLD}{FG_MUTED}vs{RESET} {BOLD}{VIOLET}{b_name}{RESET}  {BOLD}{AMBER}◀ LIVE{RESET}")
        else:
            lines.append(f"    Match {m+1:<2}: {FG_DARK}{a_name} vs {b_name}{RESET}")
            
    return "\n" + draw_box(f"{stage_title.upper()} PROGRESS (LIVE)", lines, width=76, color=VIOLET)

def render_live_race(stA, stB, scenario_name, scenario_desc, round_num, array_size, match_score=None, group_id=None, standings=None, algo_names=None, stage_title=None, bracket=None, current_match_idx=None, stage_winners=None):
    """Renders a gorgeous real-time split-screen visual dashboard of a live race."""
    # Title header
    header_lines = [
        f" {GOLD}SORTING WORLD CUP - LIVE DUEL{RESET} ".center(74, "="),
        f"Round {BOLD}{round_num} / 5{RESET}  |  Scenario: {CYAN}{scenario_name}{RESET}",
        f"Array Size: {AMBER}{array_size:,}{RESET} values",
        f"{FG_MUTED}{scenario_desc[:74]}{RESET}",
        "─" * 76,
        ""
    ]
    header = "\n".join(header_lines)
    
    # Fetch states thread-safely
    with stA.lock:
        nameA = stA.name
        doneA = stA.done
        cancelledA = stA.cancelled
        sortedA = stA.sorted
        elapsedMsA = stA.elapsed_ms
        nsA = stA.ns
        opsA = stA.operations
        readsA = stA.reads
        writesA = stA.writes
        orderA = stA.order_meter
        sampleA = list(stA.sample)
        
    with stB.lock:
        nameB = stB.name
        doneB = stB.done
        cancelledB = stB.cancelled
        sortedB = stB.sorted
        elapsedMsB = stB.elapsed_ms
        nsB = stB.ns
        opsB = stB.operations
        readsB = stB.reads
        writesB = stB.writes
        orderB = stB.order_meter
        sampleB = list(stB.sample)

    # Helper to format status text
    def get_status_str(done, sorted_, cancelled, elapsed, ns):
        if done:
            if sorted_:
                return f"{GREEN}{BOLD}DONE ({elapsed/1000:.3f}s){RESET}"
            elif cancelled:
                return f"{RED}{BOLD}TERMINATED{RESET}"
            else:
                return f"{RED}{BOLD}FAILED{RESET}"
        return f"{BLUE}RUNNING ({elapsed/1000:.3f}s){RESET}"

    statusA = get_status_str(doneA, sortedA, cancelledA, elapsedMsA, nsA)
    statusB = get_status_str(doneB, sortedB, cancelledB, elapsedMsB, nsB)

    # Render Visual Block Graphs (width = 32 characters)
    graphA = make_bar_graph(sampleA, width=32)
    graphB = make_bar_graph(sampleB, width=32)

    # Left-Right cards
    card = []
    card.append(f" {CYAN}{BOLD}{nameA.upper()[:28]:<32}{RESET}   │   {VIOLET}{BOLD}{nameB.upper()[:28]:<32}{RESET}")
    card.append(f" Status: {statusA:<25}   │   Status: {statusB:<25}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Array Visualization:               │   Array Visualization:")
    card.append(f" {BLUE}{graphA}{RESET}   │   {BLUE}{graphB}{RESET}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Sortedness:                        │   Sortedness:")
    card.append(f" {make_sortedness_bar(orderA, width=16)}            │   {make_sortedness_bar(orderB, width=16)}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Operations: {opsA:<21,}   │   Operations: {opsB:<21,}")
    card.append(f" Reads:      {readsA:<21,}   │   Reads:      {readsB:<21,}")
    card.append(f" Writes:     {writesA:<21,}   │   Writes:     {writesB:<21,}")
    
    # Use match number stage_title as the box title
    box_title = stage_title.upper() if stage_title else "DUELING STATISTICS"
    box_box = draw_box(box_title, card, width=76, color=BLUE)
    
    score_line = ""
    if match_score:
        winsA, winsB, ties = match_score
        score_line = f"\n  {BOLD}{CYAN}Live Match Score: {nameA} {winsA} - {winsB} {nameB}{RESET}  {FG_MUTED}(Ties: {ties}){RESET}\n"
        
    group_box = ""
    if group_id is not None and standings is not None and algo_names is not None:
        import copy
        # Create deep copy of standings to compute "as-it-stands" live standings
        temp_standings = copy.deepcopy(standings)
        
        # Find entry indices in standings copy
        entryA, entryB = None, None
        for s in temp_standings:
            if algo_names[s['algo']] == nameA:
                entryA = s
            elif algo_names[s['algo']] == nameB:
                entryB = s
                
        # Apply temporary round outcomes if any round has completed
        if entryA and entryB and match_score:
            winsA, winsB, ties = match_score
            if winsA > 0 or winsB > 0 or ties > 0:
                entryA['played'] += 1
                entryB['played'] += 1
                entryA['roundWins'] += winsA
                entryA['roundLosses'] += winsB
                entryB['roundWins'] += winsB
                entryB['roundLosses'] += winsA
                
                if winsA > winsB:
                    entryA['points'] += 3
                    entryA['matchWins'] += 1
                    entryB['matchLosses'] += 1
                elif winsB > winsA:
                    entryB['points'] += 3
                    entryB['matchWins'] += 1
                    entryA['matchLosses'] += 1
                else:
                    entryA['points'] += 1
                    entryB['points'] += 1
                    entryA['matchDraws'] += 1
                    entryB['matchDraws'] += 1
                    
        group_stands = [s for s in temp_standings if s['group'] == group_id]
        group_stands.sort(key=lambda x: (
            -x['points'],
            -x['matchWins'],
            -(x['roundWins'] - x['roundLosses']),
            x['ns']
        ))
        
        table_lines = []
        table_lines.append(f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5}{RESET}")
        for pos, s in enumerate(group_stands, 1):
            name = algo_names[s['algo']][:18]
            diff = s['roundWins'] - s['roundLosses']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            
            # Highlight current competitors, and grey out the others
            if algo_names[s['algo']] == nameA:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{CYAN}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}"
            elif algo_names[s['algo']] == nameB:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{VIOLET}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}"
            else:
                row = f"   {FG_DARK}{pos:<2} {name:<20} {s['played']:>3} {s['points']:>4} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}{RESET}"
            table_lines.append(row)
        group_box = "\n" + draw_box(f"GROUP {chr(ord('A') + group_id)} STANDINGS (LIVE)", table_lines, width=76, color=GREEN)
        
    bracket_box = ""
    if bracket is not None and current_match_idx is not None and stage_winners is not None:
        bracket_box = draw_live_bracket_box(bracket, current_match_idx, stage_winners, algo_names, stage_title)
        
    write_screen(header + "\n" + box_box + score_line + group_box + bracket_box)

def draw_round_result(nameA, nameB, rr, winsA, winsB, ties, stage_title, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None):
    """Draws a beautiful block summarizing the match outcome, including group standings if available."""
    header = draw_simple_header("MATCH COMPLETED")
    
    winner_name = "TIE MATCH" if winsA == winsB else (nameA if winsA > winsB else nameB)
    status_color = AMBER if winsA == winsB else GREEN
    
    # Render with same visual layout and size as dueling stats cards
    card = []
    card.append(f" {CYAN}{BOLD}{nameA.upper()[:28]:<32}{RESET}   │   {VIOLET}{BOLD}{nameB.upper()[:28]:<32}{RESET}")
    card.append(f" Outcome: {status_color}{winner_name.upper()[:23]:<23}{RESET}   │   Outcome: {status_color}{winner_name.upper()[:23]:<23}{RESET}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Final Score:                       │   Final Score:")
    card.append(f" Wins: {winsA:<29}   │   Wins: {winsB:<29}")
    card.append(f" Ties: {ties:<29}   │   Ties: {ties:<29}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Performance Metrics:               │   Performance Metrics:")
    card.append(f" Operations: {rr.operations if hasattr(rr, 'operations') else 'N/A':<22}   │   Operations: {rr.operations if hasattr(rr, 'operations') else 'N/A':<22}")
    card.append(f" Total Time: {format_ns(rr.nsA) if rr.nsA else 'N/A':<22}   │   Total Time: {format_ns(rr.nsB) if rr.nsB else 'N/A':<22}")
    card.append(f" ─" * 17 + "   │  " + " ─" * 17)
    card.append(f" Status: {GREEN}DONE{RESET:<27}   │   Status: {GREEN}DONE{RESET:<27}")
    
    box_title = stage_title.upper() if stage_title else "MATCH SUMMARY"
    box = draw_box(box_title, card, width=76, color=GOLD)
    
    group_box = ""
    if group_id is not None and standings is not None and algo_names is not None:
        import copy
        # Create copy and apply final results so the points table is fully updated
        temp_standings = copy.deepcopy(standings)
        
        entryA, entryB = None, None
        for s in temp_standings:
            if algo_names[s['algo']] == nameA:
                entryA = s
            elif algo_names[s['algo']] == nameB:
                entryB = s
                
        if entryA and entryB:
            entryA['played'] += 1
            entryB['played'] += 1
            entryA['roundWins'] += winsA
            entryA['roundLosses'] += winsB
            entryB['roundWins'] += winsB
            entryB['roundLosses'] += winsA
            
            if winsA > winsB:
                entryA['points'] += 3
                entryA['matchWins'] += 1
                entryB['matchLosses'] += 1
            elif winsB > winsA:
                entryB['points'] += 3
                entryB['matchWins'] += 1
                entryA['matchLosses'] += 1
            else:
                entryA['points'] += 1
                entryB['points'] += 1
                entryA['matchDraws'] += 1
                entryB['matchDraws'] += 1
                
        group_stands = [s for s in temp_standings if s['group'] == group_id]
        group_stands.sort(key=lambda x: (
            -x['points'],
            -x['matchWins'],
            -(x['roundWins'] - x['roundLosses']),
            x['ns']
        ))
        
        table_lines = []
        table_lines.append(f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5}{RESET}")
        for pos, s in enumerate(group_stands, 1):
            name = algo_names[s['algo']][:18]
            diff = s['roundWins'] - s['roundLosses']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            
            # Highlight current competitors, and grey out the others
            if algo_names[s['algo']] == nameA:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{CYAN}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}"
            elif algo_names[s['algo']] == nameB:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{VIOLET}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}"
            else:
                row = f"   {FG_DARK}{pos:<2} {name:<20} {s['played']:>3} {s['points']:>4} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5}{RESET}"
            table_lines.append(row)
        group_box = "\n" + draw_box(f"GROUP {chr(ord('A') + group_id)} STANDINGS (FINAL)", table_lines, width=76, color=GREEN)
        
    bracket_box = ""
    if bracket is not None and current_match_idx is not None and stage_winners is not None:
        current_winner_idx = bracket[2 * current_match_idx] if winsA > winsB else bracket[2 * current_match_idx + 1]
        bracket_box = draw_live_bracket_box(bracket, current_match_idx, stage_winners, algo_names, stage_title, current_winner_idx=current_winner_idx)
        
    write_screen(header + "\n" + box + group_box + bracket_box)

    

