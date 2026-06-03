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
        try:
            data = os.read(fd, 16)
        except Exception:
            return None
            
        if not data:
            return None
            
        # Parse escape sequences
        if data == b'\x1b[A' or data == b'\x1bOA':
            return 'up'
        elif data == b'\x1b[B' or data == b'\x1bOB':
            return 'down'
        elif data == b'\x1b[C' or data == b'\x1bOC':
            return 'right'
        elif data == b'\x1b[D' or data == b'\x1bOD':
            return 'left'
        elif data == b'\x1b':
            return 'esc'
        elif data in (b'\r', b'\n'):
            return 'enter'
        elif data == b' ':
            return 'space'
        elif data == b'\x7f':  # Backspace on mac
            return 'backspace'
        elif data == b'\x03':  # Ctrl-C
            raise KeyboardInterrupt()
        elif data.startswith(b'\x1b'):
            return 'esc'
            
        try:
            return data.decode('utf-8', errors='ignore').lower()
        except Exception:
            return None


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
    # FIFA World Cup trophies on left and right, with central tournament label box
    left_trophy = [
        "       .-----.     ",
        "     .'   __  '.   ",
        "    /   .'  '.  \\  ",
        "   |   |      |  | ",
        "    \\   '.__.'  /  ",
        "     '.       .'   ",
        "       )  _  (     ",
        "      /  ( )  \\    ",
        "     /  /   \\  \\   ",
        "    |  |  _  |  |  ",
        "    |  | ( ) |  |  ",
        "    |  |  V  |  |  ",
        "   /  /       \\  \\ ",
        "  |  |         |  |",
        "  |  |=========|  |",
        "  |  |=========|  |",
        " /  /===========\\  \\",
        "|_________________|",
        "|                 |"
    ]
    right_trophy = left_trophy
    mid_block = [
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      ",
        "            .-=========-.             ",
        "           /             \\            ",
        "          |    SORTING    |           ",
        "          |   WORLD CUP   |           ",
        "          |     2026      |           ",
        "           \\             /            ",
        "            '-=========-'             ",
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      ",
        "                                      "
    ]
    lines = []
    lines.append(f"{GOLD}")
    for i in range(19):
        lines.append(left_trophy[i] + mid_block[i] + right_trophy[i])
    lines.append(f"{RESET}")
    
    if subtitle:
        width = 76
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

def render_settings_menu(selected_idx, current_size, current_ko_size, current_final_size, current_delay, group_timeout, ko_timeout, final_timeout, autoplay):
    """Renders an interactive settings modifier screen."""
    header = draw_trophy_header("SETTINGS")
    
    opts = [
        ("Group Array Size", f"{current_size:,} elements"),
        ("Knockouts Array Size", f"{current_ko_size:,} elements"),
        ("Final Array Size", f"{current_final_size:,} elements"),
        ("Simulation Delay", f"{current_delay * 1000:.4f} ms" if current_delay > 0 else "0 ms"),
        ("Group Stage Timeout", f"{group_timeout} seconds"),
        ("Knockout Stage Timeout", f"{ko_timeout} seconds"),
        ("Final Stage Timeout", f"{final_timeout} seconds"),
        ("Tournament Autoplay", "Enabled" if autoplay else "Disabled"),
        ("Back to Main Menu", "")
    ]
    
    content = [
        "Customize tournament mechanics to observe slower algorithms or run faster races.",
        f"Use {CYAN}Arrow Keys (←/→){RESET} to cycle presets/toggle, or press {CYAN}Enter{RESET} to type a custom value.",
        ""
    ]
    
    for i, (name, val) in enumerate(opts):
        cursor = f"{CYAN}▶ {BOLD}" if i == selected_idx else "  "
        if val:
            line = f"{cursor}{name:<25} {AMBER}◀ {val:<15} ▶{RESET}"
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
        # Table columns: Pos, Name, Played, Points, Wins, Draws, Losses, Round Wins (Diff), Avg Time
        col_header = f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5} {'AvgTime':>10}{RESET}"
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
            avg_ns = s['ns'] / s['played'] if s['played'] > 0 else 0
            avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s" if s['played'] > 0 else "0.0000s"
            color_row = GREEN if pos <= 2 else RESET
            row = f"   {pos:<2} {color_row}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}"
            content.append(row)
        content.append("  " + "─" * 60)
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
def draw_live_bracket_box(bracket, current_match_idx, stage_winners, algo_names, stage_title, current_winner_idx=None, stage_scores=None):
    if not bracket or current_match_idx is None:
        return ""
        
    lines = []
    num_matches = len(bracket) // 2
    for m in range(num_matches):
        a_idx = bracket[2 * m]
        b_idx = bracket[2 * m + 1]
        a_name = algo_names[a_idx] if (algo_names and a_idx < len(algo_names)) else f"Algo {a_idx}"
        b_name = algo_names[b_idx] if (algo_names and b_idx < len(algo_names)) else f"Algo {b_idx}"
        
        # Check if winner is decided
        winner = None
        score_str = ""
        if m < len(stage_winners):
            winner = stage_winners[m]
            if stage_scores and m < len(stage_scores):
                w_a, w_b = stage_scores[m]
                if winner == a_idx:
                    score_str = f" ({w_a}-{w_b})"
                else:
                    score_str = f" ({w_b}-{w_a})"
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
            lines.append(f"  {FG_MUTED}✓{RESET} Match {m+1:<2}: {winner_str} {FG_MUTED}def.{RESET} {loser_str}{score_str}")
        elif m == current_match_idx:
            lines.append(f"  {BOLD}{CYAN}▶{RESET} Match {m+1:<2}: {BOLD}{CYAN}{a_name}{RESET} {BOLD}{FG_MUTED}vs{RESET} {BOLD}{VIOLET}{b_name}{RESET}  {BOLD}{AMBER}◀ LIVE{RESET}")
        else:
            lines.append(f"    Match {m+1:<2}: {FG_DARK}{a_name} vs {b_name}{RESET}")
            
    return "\n" + draw_box(f"{stage_title.upper()} PROGRESS (LIVE)", lines, width=76, color=VIOLET)

def render_live_race(stA, stB, scenario_name, scenario_desc, round_num, array_size, match_score=None, group_id=None, standings=None, algo_names=None, stage_title=None, bracket=None, current_match_idx=None, stage_winners=None, stage_scores=None):
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
        table_lines.append(f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5} {'AvgTime':>10}{RESET}")
        for pos, s in enumerate(group_stands, 1):
            name = algo_names[s['algo']][:18]
            diff = s['roundWins'] - s['roundLosses']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            avg_ns = s['ns'] / s['played'] if s['played'] > 0 else 0
            avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s" if s['played'] > 0 else "0.0000s"
            
            # Highlight current competitors, and grey out the others
            if algo_names[s['algo']] == nameA:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{CYAN}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}"
            elif algo_names[s['algo']] == nameB:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{VIOLET}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}"
            else:
                row = f"   {FG_DARK}{pos:<2} {name:<20} {s['played']:>3} {s['points']:>4} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}{RESET}"
            table_lines.append(row)
        group_box = "\n" + draw_box(f"GROUP {chr(ord('A') + group_id)} STANDINGS (LIVE)", table_lines, width=76, color=GREEN)
        
    bracket_box = ""
    if bracket is not None and current_match_idx is not None and stage_winners is not None:
        bracket_box = draw_live_bracket_box(bracket, current_match_idx, stage_winners, algo_names, stage_title, stage_scores=stage_scores)
        
    write_screen(header + "\n" + box_box + score_line + group_box + bracket_box)

def draw_round_result(nameA, nameB, rr, winsA, winsB, ties, stage_title, group_id=None, standings=None, algo_names=None, bracket=None, current_match_idx=None, stage_winners=None, stage_scores=None):
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
        table_lines.append(f"  {FG_MUTED}{'Pos':<3} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5} {'AvgTime':>10}{RESET}")
        for pos, s in enumerate(group_stands, 1):
            name = algo_names[s['algo']][:18]
            diff = s['roundWins'] - s['roundLosses']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            avg_ns = s['ns'] / s['played'] if s['played'] > 0 else 0
            avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s" if s['played'] > 0 else "0.0000s"
            
            # Highlight current competitors, and grey out the others
            if algo_names[s['algo']] == nameA:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{CYAN}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}"
            elif algo_names[s['algo']] == nameB:
                c_pos = GREEN if pos <= 2 else RESET
                row = f"   {c_pos}{pos:<2} {BOLD}{VIOLET}{name:<20}{RESET} {s['played']:>3} {BOLD}{s['points']:>4}{RESET} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}"
            else:
                row = f"   {FG_DARK}{pos:<2} {name:<20} {s['played']:>3} {s['points']:>4} {s['matchWins']:>3} {s['matchDraws']:>3} {s['matchLosses']:>3} {diff_str:>5} {avg_time_str:>10}{RESET}"
            table_lines.append(row)
        group_box = "\n" + draw_box(f"GROUP {chr(ord('A') + group_id)} STANDINGS (FINAL)", table_lines, width=76, color=GREEN)
        
    bracket_box = ""
    if bracket is not None and current_match_idx is not None and stage_winners is not None:
        current_winner_idx = bracket[2 * current_match_idx] if winsA > winsB else bracket[2 * current_match_idx + 1]
        temp_scores = list(stage_scores) if stage_scores is not None else []
        temp_scores.append((winsA, winsB))
        bracket_box = draw_live_bracket_box(
            bracket,
            current_match_idx,
            stage_winners + [current_winner_idx],
            algo_names,
            stage_title,
            stage_scores=temp_scores
        )
        
    write_screen(header + "\n" + box + group_box + bracket_box)


# --- New Tournament TUI Screens ---

def render_pre_match_intro(algoA, algoB, rankA, rankB, probA, probB, stage_title):
    """Renders a beautiful comparison card of the competitors before they duel."""
    header = draw_simple_header(f"PRE-MATCH SHOWDOWN — {stage_title.upper()}")
    
    card = [
        f" {CYAN}{BOLD}{algoA['name'].upper()[:28]:<32}{RESET}   │   {VIOLET}{BOLD}{algoB['name'].upper()[:28]:<32}{RESET}",
        f" ELO Rating: {algoA.get('elo', 1500.0):<19.1f}   │   ELO Rating: {algoB.get('elo', 1500.0):<19.1f}",
        f" World Rank: #{rankA:<19}   │   World Rank: #{rankB:<19}",
        f" ─" * 17 + "   │  " + " ─" * 17,
        f" Category:   {algoA.get('category', 'N/A'):<17}   │   Category:   {algoB.get('category', 'N/A'):<17}",
        f" Year:       {algoA.get('year', 'N/A'):<17}   │   Year:       {algoB.get('year', 'N/A'):<17}",
        f" Inventor:   {algoA.get('inventor', 'N/A')[:17]:<17}   │   Inventor:   {algoB.get('inventor', 'N/A')[:17]:<17}",
        f" Complexity: {algoA.get('complexity', 'N/A'):<17}   │   Complexity: {algoB.get('complexity', 'N/A'):<17}",
        f" Memory:     {algoA.get('memory', 'N/A'):<17}   │   Memory:     {algoB.get('memory', 'N/A'):<17}",
        f" Stable:     {str(algoA.get('stable', 'N/A')):<17}   │   Stable:     {str(algoB.get('stable', 'N/A')):<17}",
        f" ─" * 17 + "   │  " + " ─" * 17,
        f" Win Prob:   {BOLD}{GREEN}{probA}%{RESET}{' ':<22}   │   Win Prob:   {BOLD}{GREEN}{probB}%{RESET}{' ':<22}",
        f" {make_sortedness_bar(probA, width=16)}            │   {make_sortedness_bar(probB, width=16)}",
        f" ─" * 17 + "   │  " + " ─" * 17,
    ]
    
    # Personalities and descriptions
    card.append(f" {CYAN}{algoA['name']}{RESET} Personality:")
    card.append(f"   {ITALIC}\"{algoA.get('personality', '')}\"{RESET}")
    card.append(f"   {FG_MUTED}{algoA.get('description', '')[:70]}{RESET}")
    card.append("")
    card.append(f" {VIOLET}{algoB['name']}{RESET} Personality:")
    card.append(f"   {ITALIC}\"{algoB.get('personality', '')}\"{RESET}")
    card.append(f"   {FG_MUTED}{algoB.get('description', '')[:70]}{RESET}")
    
    box = draw_box("MATCH PREVIEW", card, width=76, color=GOLD)
    write_screen(header + "\n" + box + "\n\n  Press Enter to launch match...")

def render_awards_screen(awards):
    """Renders the Academy-style tournament awards screen."""
    header = draw_trophy_header("TOURNAMENT AWARDS")
    
    content = [
        f"  {GOLD}GOLDEN TROPHY - Overall Champion:{RESET}",
        f"    🏆 {BOLD}{CYAN}{awards['champion']}{RESET}",
        "",
        f"  {AMBER}GOLDEN STOPWATCH - Fastest Round Finish:{RESET}",
        f"    ⏱ {BOLD}{GREEN}{awards['fastest_time']}{RESET}",
        "",
        f"  {GREEN}GOLDEN CPU - Lowest Operation Count in a Round:{RESET}",
        f"    ⚡ {BOLD}{VIOLET}{awards['lowest_ops']}{RESET}",
        "",
        f"  {BLUE}GOLDEN RAM STICK - Most Memory-Efficient:{RESET}",
        f"    💾 {BOLD}{BLUE}{awards['ram_winner']}{RESET}",
        "",
        f"  {VIOLET}GIANT KILLER - Biggest ELO Upset:{RESET}",
        f"    ⚔ {BOLD}{AMBER}{awards['gk_winner']}{RESET}",
        "",
        f"  {RED}WOODEN SPOON - Worst Tournament Performance:{RESET}",
        f"    🥄 {BOLD}{RED}{awards['wooden_spoon']}{RESET}",
        "",
        f"  Press {CYAN}Enter{RESET} to view the coronation and fireworks!"
    ]
    
    box = draw_box("THE ACADEMY AWARDS", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

def render_hall_of_fame_view(hof):
    """Renders the Hall of Fame champion scroll."""
    header = draw_trophy_header("HALL OF FAME")
    
    content = [
        "Persisted champions across all tournaments.",
        f"Press {CYAN}Enter{RESET} to return to main menu.",
        ""
    ]
    
    if not hof:
        content.append(f"  {FG_MUTED}No tournaments have completed yet. Be the first to win!{RESET}")
    else:
        for idx, entry in enumerate(hof, 1):
            content.append(f"  {GOLD}🏆 CHAMPION #{idx}: {BOLD}{entry['champion_name'].upper()}{RESET} ({entry['year']})")
            content.append(f"     Record:      {CYAN}{entry['record']}{RESET}")
            content.append(f"     Avg. Time:   {AMBER}{entry['avg_finish_time']:.4f}s{RESET}")
            # Wrap path string if it's too long
            path = entry['path']
            if len(path) > 65:
                path = path[:62] + "..."
            content.append(f"     Path:        {FG_MUTED}{path}{RESET}")
            content.append("")
            
    box = draw_box("HALL OF FAME INDUCTEES", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

def render_scenario_strengths_view(perf, algo_names, page=0):
    """Renders the scenario performance heatmap split in two pages."""
    header = draw_trophy_header("SCENARIO PERFORMANCE HEATMAP")
    
    content = [
        f"Average sort time in milliseconds.  |  Use {CYAN}← / → Arrows{RESET} to switch pages.",
        f"Press {CYAN}Enter{RESET} to return to main menu.",
        ""
    ]
    
    col_header = f"  {FG_MUTED}{'Algorithm':<22} {'Sorted':>9} {'Random':>9} {'Reversed':>9} {'Nearly S':>9} {'Dupl.':>9}{RESET}"
    content.append(col_header)
    content.append("  " + "─" * 70)
    
    start_idx = page * 16
    end_idx = min(len(algo_names), start_idx + 16)
    
    for i in range(start_idx, end_idx):
        name = algo_names[i]
        row_str = f"  {BOLD}{name:<22}{RESET}"
        
        for s_id in range(5):
            p = perf.get(name, {}).get(str(s_id)) or perf.get(name, {}).get(s_id)
            if p and p.get('avg_time_ns', 0) > 0:
                ms = p['avg_time_ns'] / 1_000_000
                if ms < 1.0:
                    time_val = f"{ms:.3f}ms"
                elif ms < 1000.0:
                    time_val = f"{ms:.1f}ms"
                else:
                    time_val = f"{ms/1000:.2f}s"
                    
                if ms < 5.0:
                    color = GREEN
                elif ms < 50.0:
                    color = AMBER
                else:
                    color = RED
                row_str += f" {color}{time_val:>9}{RESET}"
            else:
                row_str += f" {FG_DARK}{'N/A':>9}{RESET}"
        content.append(row_str)
        
    content.append("  " + "─" * 70)
    content.append(f"  Page {page+1} / 2")
    
    box = draw_box("SCENARIO HEATMAP", content, width=76, color=CYAN)
    write_screen(header + "\n" + box)

def render_exhibition_menu(selected_idx):
    """Renders the exhibition selection menu."""
    header = draw_trophy_header("EXHIBITION MATCHES")
    
    opts = [
        "1. Quick Sort vs Merge Sort (The Classic Rivalry)",
        "2. Timsort vs IntroSort (The Modern Elite Battle)",
        "3. Bogo Sort vs Stooge Sort (The Battle of the Inefficient)",
        "4. Fastest 8 Algorithms Battle Royale (The Elite 8 Showdown)",
        "5. Back to Main Menu"
    ]
    
    content = [
        "Select a legendary showcase match to watch the algorithms battle in real-time.",
        "These matches do not affect ELO ratings or tournament standings.",
        ""
    ]
    
    for i, opt in enumerate(opts):
        if i == selected_idx:
            content.append(f"    {CYAN}▶ {BOLD}{UNDERLINE}{opt}{RESET}")
        else:
            content.append(f"      {opt}")
            
    box = draw_box("EXHIBITION MATCH CARD", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

def render_exhibition_battle_royale(states, scenario_name, elapsed_ms, array_size):
    """Renders the stacked 8-way concurrent live progress of the Battle Royale."""
    header = draw_simple_header("LEGENDARY BATTLE ROYALE (8 ALGORITHMS)")
    
    content = [
        f"Scenario: {CYAN}{scenario_name}{RESET} | Size: {AMBER}{array_size:,}{RESET} values | Time: {elapsed_ms/1000:.3f}s",
        "─" * 70
    ]
    
    for st in states:
        with st.lock:
            name = st.name
            done = st.done
            sorted_ = st.sorted
            ops = st.operations
            elapsed = st.elapsed_ms
            order = st.order_meter
            cancelled = st.cancelled
            
        if done:
            if sorted_:
                status = f"{GREEN}DONE ({elapsed/1000:.3f}s){RESET}"
            elif cancelled:
                status = f"{RED}TERM{RESET}"
            else:
                status = f"{RED}FAIL{RESET}"
        else:
            status = f"{BLUE}RUNNING{RESET}"
            
        filled = int((order / 100.0) * 12)
        filled = max(0, min(12, filled))
        empty = 12 - filled
        progress_bar = f"{GREEN}{'█' * filled}{FG_DARK}{'░' * empty}{RESET} {order:3.0f}%"
        
        content.append(f"  {BOLD}{name:<20}{RESET} {progress_bar} {status:<15} {ops:>10,} ops")
        
    box = draw_box("8-WAY BATTLE ROYALE", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

def render_fixtures_view(fixtures, algo_names, page=0):
    """Renders the scheduled matches list split across 2 pages (Groups A-D vs E-H)."""
    header = draw_trophy_header("SCHEDULED FIXTURES")
    groups_to_render = range(0, 4) if page == 0 else range(4, 8)
    
    content = []
    content.append(f"Showing Groups {chr(ord('A') + groups_to_render[0])}-{chr(ord('A') + groups_to_render[-1])}  |  Use {CYAN}← / → Arrows{RESET} to switch pages.")
    content.append(f"Press {CYAN}Enter{RESET} to exit to main menu.")
    content.append("")
    
    for g in groups_to_render:
        content.append(f"{BOLD}{GOLD}GROUP {chr(ord('A') + g)} Fixtures:{RESET}")
        local_idx = 1
        for f in fixtures:
            if f['group'] != g:
                continue
            nameA = algo_names[f['a']][:24]
            nameB = algo_names[f['b']][:24]
            content.append(f"  {local_idx}. {nameA:<24} vs {nameB:<24}")
            local_idx += 1
        content.append("")
        
    box = draw_box("TOURNAMENT FIXTURES", content, width=76, color=BLUE)
    write_screen(header + "\n" + box)

def render_rating_board(ratings_list, page=0):
    """Renders the ELO rating board, paginated (16 algorithms per page)."""
    header = draw_trophy_header("WORLD RATING BOARD")
    
    content = []
    content.append(f"Rankings by ELO Rating  |  Page {page+1}/2  |  Use {CYAN}← / → Arrows{RESET} to switch pages.")
    content.append(f"Press {CYAN}Enter{RESET} to exit to main menu.")
    content.append("")
    
    col_header = f"  {FG_MUTED}{'Rank':<5} {'Algorithm':<20} {'ELO':>8} {'Played':>7} {'Wins':>6} {'Losses':>7} {'Avg Time':>11}{RESET}"
    content.append(col_header)
    content.append("  " + "─" * 68)
    
    start_idx = page * 16
    end_idx = min(start_idx + 16, len(ratings_list))
    
    for idx in range(start_idx, end_idx):
        item = ratings_list[idx]
        rank = idx + 1
        name = item['name'][:18]
        elo = f"{item['elo']:.1f}"
        played = item['played']
        won = item['won']
        lost = item['lost']
        
        if item['total_sorted_rounds'] > 0:
            avg_ns = item['total_sorted_time_ns'] / item['total_sorted_rounds']
            avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s"
        else:
            avg_time_str = "0.0000s"
            
        row = f"  {rank:<5} {GREEN if rank <= 3 else (AMBER if rank <= 8 else RESET)}{name:<20}{RESET} {BOLD}{elo:>8}{RESET} {played:>7} {won:>6} {lost:>7} {avg_time_str:>11}"
        content.append(row)
        
    content.append("  " + "─" * 68)
    box = draw_box("ELO RATING SUMMARY", content, width=76, color=GOLD)
    write_screen(header + "\n" + box)

def render_consolidated_standings(current_stands, all_time_stands, page=0):
    """Renders a consolidated standings table for all 32 algorithms."""
    is_all_time = page >= 2
    title = "ALL-TIME CONSOLIDATED POINTS TABLE" if is_all_time else "CURRENT SEASON CONSOLIDATED TABLE"
    header = draw_trophy_header(title)
    
    content = []
    content.append(f"Rankings 1-32  |  Page {page+1}/4  |  Use {CYAN}← / → Arrows{RESET} to switch pages.")
    content.append(f"Press {CYAN}Enter{RESET} to exit to main menu.")
    content.append("")
    
    col_header = f"  {FG_MUTED}{'Rank':<5} {'Algorithm':<20} {'P':>3} {'Pts':>4} {'W':>3} {'D':>3} {'L':>3} {'Diff':>5} {'AvgTime':>10}{RESET}"
    content.append(col_header)
    content.append("  " + "─" * 64)
    
    stands = all_time_stands if is_all_time else current_stands
    local_page = page % 2
    start_idx = local_page * 16
    end_idx = min(start_idx + 16, len(stands))
    
    for idx in range(start_idx, end_idx):
        s = stands[idx]
        rank = idx + 1
        name = s['name'][:18]
        played = s['played']
        points = s['points']
        wins = s['matchWins']
        draws = s['matchDraws']
        losses = s['matchLosses']
        diff = s['roundWins'] - s['roundLosses']
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        
        if is_all_time:
            if s['total_sorted_rounds'] > 0:
                avg_ns = s['total_sorted_time_ns'] / s['total_sorted_rounds']
                avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s"
            else:
                avg_time_str = "0.0000s"
        else:
            avg_ns = s['ns'] / played if played > 0 else 0
            avg_time_str = f"{avg_ns / 1_000_000_000:.4f}s" if played > 0 else "0.0000s"
            
        color_row = GREEN if rank <= 8 else RESET
        row = f"  {rank:<5} {color_row}{name:<20}{RESET} {played:>3} {BOLD}{points:>4}{RESET} {wins:>3} {draws:>3} {losses:>3} {diff_str:>5} {avg_time_str:>10}"
        content.append(row)
        
    content.append("  " + "─" * 64)
    box = draw_box("CONSOLIDATED POINTS SUMMARY", content, width=76, color=GREEN if not is_all_time else BLUE)
    write_screen(header + "\n" + box)

def render_archives_years_list(years, selected_idx):
    """Renders the list of archived tournament seasons for selection."""
    header = draw_trophy_header("TOURNAMENT HISTORY ARCHIVES")
    
    content = []
    content.append("Browse completed tournament records from past years.")
    content.append(f"Use {CYAN}Up/Down Arrows{RESET} to select, and press {CYAN}Enter{RESET} to open.")
    content.append("")
    
    if not years:
        content.append(f"  {RED}No archived seasons found.{RESET}")
        content.append("  Archives are created automatically when a tournament season completes.")
        content.append("")
        content.append("  Select 'Back to Main Menu' below.")
    else:
        for idx, (year, champion) in enumerate(years):
            cursor = f"{CYAN}▶ {BOLD}" if idx == selected_idx else "  "
            line = f"{cursor}Season Year {year:<6} | Champion: {GOLD}{champion:<24}{RESET}"
            content.append(line)
            
    content.append("")
    back_cursor = f"{CYAN}▶ {BOLD}" if selected_idx == len(years) else "  "
    content.append(f"{back_cursor}Back to Main Menu{RESET}")
    content.append("")
    
    box = draw_box("YEAR ARCHIVES", content, width=76, color=BLUE)
    write_screen(header + "\n" + box)

def render_archive_details_menu(year, champion, selected_idx):
    """Renders the option menu for a selected archived year."""
    header = draw_trophy_header(f"ARCHIVE - YEAR {year}")
    
    opts = [
        "1. View Group Stage Points Table",
        "2. View Knockout Bracket",
        "3. Back to Years Selection"
    ]
    
    content = []
    content.append(f"Archived details for Season Year {year}.")
    content.append(f"Champion: {GOLD}{champion}{RESET}")
    content.append("")
    
    for idx, opt in enumerate(opts):
        cursor = f"{CYAN}▶ {BOLD}" if idx == selected_idx else "  "
        content.append(f"{cursor}{opt}{RESET}")
        
    content.append("")
    box = draw_box("ARCHIVE VIEWS", content, width=76, color=VIOLET)
    write_screen(header + "\n" + box)

    

