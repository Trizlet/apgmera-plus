#!/usr/bin/env python3
"""
🧬 APGMERA LIVE SEARCH DASHBOARD & PATTERN VIEWER
=================================================
A flicker-free, dual-mode terminal dashboard for apgluxe featuring:
  - Mode 1: Side-by-side (live textual apgluxe output + TinyLife half-block viewer)
  - Mode 2: Fullscreen visualization
  - Clean dynamic resizing (SIGWINCH)
  - Auto-updates & switches to newly discovered patterns
  - Dynamic header colors matching apgluxe output (Green, Red, Cyan, White)
  - TinyLife rainbow-age heatmap where cell color evolves with cell longevity
  - Atomic, zero-flicker terminal rendering
"""

import sys
import os
import re
import time
import pty
import select
import signal
import termios
import tty
import shutil
import threading
from collections import deque

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Base36 character map for apgcode decoding
CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"
ANSI_REGEX = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Color palettes (TrueColor & ANSI)
PALETTES = [
    {"name": "white",   "mode": "static",  "color": "\033[38;5;255m",         "rgb": (255, 255, 255), "label": "White"},
    {"name": "age",     "mode": "age",     "color": "age",                    "rgb": None,            "label": "Age Heatmap (TinyLife)"},
    {"name": "rainbow", "mode": "rainbow", "color": "rainbow",                "rgb": None,            "label": "Rainbow Wave"},
    {"name": "cyan",    "mode": "static",  "color": "\033[38;2;0;229;255m",   "rgb": (0, 229, 255),   "label": "Cyan (TinyLife)"},
    {"name": "green",   "mode": "static",  "color": "\033[38;2;80;250;123m",  "rgb": (80, 250, 123),  "label": "Phosphor Green"},
    {"name": "amber",   "mode": "static",  "color": "\033[38;2;255;184;108m", "rgb": (255, 184, 108), "label": "Amber CRT"},
    {"name": "pink",    "mode": "static",  "color": "\033[38;2;255;121;198m", "rgb": (255, 121, 198), "label": "Neon Pink"}
]

CLR_RESET  = "\033[0m"
CLR_BOLD   = "\033[1m"
CLR_DIM    = "\033[2m"
CLR_BORDER = "\033[38;5;240m"
CLR_GRAY   = "\033[38;5;245m"
CLR_WHITE  = "\033[38;5;255m"
CLR_GREEN  = "\033[1;32m"
CLR_RED    = "\033[1;31m"
CLR_CYAN   = "\033[1;36m"
CLR_AMBER  = "\033[38;2;255;184;108m"
CLR_PINK   = "\033[38;2;255;121;198m"

def get_age_color(age):
    """TinyLife cell longevity heatmap: newborn cyan -> green -> yellow -> orange -> crimson red."""
    if age <= 1:   return "\033[96m"        # Electric Cyan (newborn)
    if age <= 3:   return "\033[94m"        # Sky Blue
    if age <= 6:   return "\033[92m"        # Lime Green (adolescent)
    if age <= 10:  return "\033[93m"        # Bright Yellow (mature)
    if age <= 18:  return "\033[38;5;208m"  # Warm Orange (established)
    if age <= 30:  return "\033[95m"        # Magenta (elder)
    return "\033[91m"                       # Crimson Red (ancient still-life)

def to_bg_color(fg):
    """Converts ANSI foreground color to background color for dual-age half-blocks."""
    return fg.replace('\033[9', '\033[10', 1).replace('\033[38;', '\033[48;', 1)

def get_rainbow_color(y, x, gen):
    """TinyLife traveling rainbow wave."""
    hue = (y * 8 + x * 5 + gen * 6) % 360
    h_prime = hue / 60.0
    val = int(255 * (1 - abs(h_prime % 2 - 1)))
    if h_prime < 1:   return f"\033[38;2;255;{val};0m"
    elif h_prime < 2: return f"\033[38;2;{val};255;0m"
    elif h_prime < 3: return f"\033[38;2;0;255;{val}m"
    elif h_prime < 4: return f"\033[38;2;0;{val};255m"
    elif h_prime < 5: return f"\033[38;2;{val};0;255m"
    else:             return f"\033[38;2;255;0;{val}m"

def visible_length(s):
    """Calculates visible character length of string excluding ANSI escape codes."""
    return len(ANSI_REGEX.sub('', s))

def fit_to_width(s, width):
    """Truncates or pads string `s` so its visible terminal width is EXACTLY `width`."""
    vis_len = visible_length(s)
    if vis_len == width:
        return s
    elif vis_len < width:
        return s + (" " * (width - vis_len))
    else:
        out = []
        cur_len = 0
        idx = 0
        while idx < len(s) and cur_len < width:
            m = ANSI_REGEX.match(s, idx)
            if m:
                out.append(m.group(0))
                idx = m.end()
            else:
                out.append(s[idx])
                cur_len += 1
                idx += 1
        out.append(CLR_RESET)
        return "".join(out)

def decode_apg(code):
    """
    Decodes an apgcode string into a set of (x, y) coordinates.
    Direct implementation of the Catagolue decodeCanon algorithm.
    """
    clean_code = ANSI_REGEX.sub('', code).strip()
    i = clean_code.find('_') + 1 if '_' in clean_code else 0
    blank, x, y, plane = 0, 0, 0, 0
    cells = set()
    for c in clean_code[i:]:
        if blank:
            if c in CHARS:
                x += CHARS.index(c)
            blank = 0
        elif c == 'y':
            x += 4
            blank = 1
        elif c == 'x':
            x += 3
        elif c == 'w':
            x += 2
        elif c == 'z':
            x = 0
            y += 5
        elif c == '_':
            x = 0
            y = 0
            plane += 1
        else:
            if c not in CHARS:
                continue
            v = CHARS.index(c)
            for j in range(5):
                if v & (1 << j):
                    cells.add((x, y + j))
            x += 1
    return cells

class LifeEngine:
    """Toroidal Life-like CA grid simulation with age tracking and period detection."""
    def __init__(self, width=60, height=30, rule="b3s23"):
        self.width = max(6, width)
        self.height = max(6, height)
        self.grid = [[0] * self.width for _ in range(self.height)]
        self.age_grid = [[0] * self.width for _ in range(self.height)]
        self.gen = 0
        self.pop = 0
        self.hash_history = deque(maxlen=64)
        self.period = 0
        self.raw_cells = []
        self.rule_string = "b3s23"
        self.birth = {3}
        self.survive = {2, 3}
        self.is_hex = False
        self.set_rule(rule)

    def set_rule(self, rule_str):
        if not rule_str:
            return
        clean = rule_str.split('/')[0].strip().lower()
        if not clean:
            return
        self.rule_string = clean
        self.is_hex = clean.endswith('h')
        rc = clean[:-1] if self.is_hex else clean

        b_match = re.search(r'b(\d*)', rc)
        s_match = re.search(r's(\d*)', rc)

        if b_match or s_match:
            self.birth = {int(d) for d in b_match.group(1)} if b_match else set()
            self.survive = {int(d) for d in s_match.group(1)} if s_match else set()
        else:
            self.birth = {3}
            self.survive = {2, 3}

    def resize(self, width, height):
        width = max(6, width)
        height = max(6, height)
        if width == self.width and height == self.height:
            return
        self.width = width
        self.height = height
        self.load_cells(self.raw_cells, reset_gen=False)

    def load_cells(self, cells, reset_gen=True):
        self.raw_cells = list(cells)
        self.grid = [[0] * self.width for _ in range(self.height)]
        self.age_grid = [[0] * self.width for _ in range(self.height)]
        if reset_gen:
            self.gen = 0
            self.hash_history.clear()
            self.period = 0
        self.pop = 0
        if not cells:
            return

        min_x = min(x for x, y in cells)
        max_x = max(x for x, y in cells)
        min_y = min(y for x, y in cells)
        max_y = max(y for x, y in cells)
        pat_w = max_x - min_x + 1
        pat_h = max_y - min_y + 1

        offset_x = (self.width - pat_w) // 2 - min_x
        offset_y = (self.height - pat_h) // 2 - min_y

        for x, y in cells:
            gx = (x + offset_x) % self.width
            gy = (y + offset_y) % self.height
            self.grid[gy][gx] = 1
            self.age_grid[gy][gx] = 1
            self.pop += 1

    def step(self):
        w = self.width
        h = self.height
        grid = self.grid
        age_grid = self.age_grid
        new_grid = [[0] * w for _ in range(h)]
        new_age_grid = [[0] * w for _ in range(h)]
        new_pop = 0
        birth = self.birth
        survive = self.survive
        is_hex = self.is_hex

        for r in range(h):
            r_up = (r - 1) % h
            r_down = (r + 1) % h
            row = grid[r]
            row_up = grid[r_up]
            row_down = grid[r_down]
            new_row = new_grid[r]
            new_age_row = new_age_grid[r]
            cur_age_row = age_grid[r]

            for c in range(w):
                c_left = (c - 1) % w
                c_right = (c + 1) % w

                if is_hex:
                    # Hexagonal 6-neighbor lattice (omitting up-right and down-left diagonals)
                    neighbors = (
                        row_up[c_left] + row_up[c] +
                        row[c_left]                + row[c_right] +
                                         row_down[c] + row_down[c_right]
                    )
                else:
                    # Standard square Moore 8-neighbor lattice
                    neighbors = (
                        row_up[c_left] + row_up[c] + row_up[c_right] +
                        row[c_left]                + row[c_right] +
                        row_down[c_left] + row_down[c] + row_down[c_right]
                    )

                if row[c]:
                    if neighbors in survive:
                        new_row[c] = 1
                        new_age_row[c] = min(65535, cur_age_row[c] + 1)
                        new_pop += 1
                else:
                    if neighbors in birth:
                        new_row[c] = 1
                        new_age_row[c] = 1
                        new_pop += 1

        self.grid = new_grid
        self.age_grid = new_age_grid
        self.pop = new_pop
        self.gen += 1

        # Period detection
        hval = hash(tuple(tuple(r) for r in self.grid))
        if hval in self.hash_history:
            idx = self.hash_history.index(hval)
            self.period = len(self.hash_history) - idx
        else:
            self.hash_history.append(hval)

class DashboardState:
    def __init__(self):
        self.lock = threading.Lock()
        self.raw_logs = deque(maxlen=500)
        self.discoveries = [] # (apcode, type_str, cells, color_code)
        self.seen_codes = set()
        self.current_disc_index = 0
        self.is_running = True
        self.paused = False

        # Telemetry metrics
        self.rule = "b3s23/C1"
        try:
            params_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "includes", "params.h")
            if os.path.exists(params_file):
                with open(params_file, "r") as pf:
                    p_txt = pf.read()
                    r_m = re.search(r'#define\s+RULESTRING\s+"([^"]+)"', p_txt)
                    s_m = re.search(r'#define\s+SYMMETRY\s+"([^"]+)"', p_txt)
                    if r_m and s_m:
                        self.rule = f"{r_m.group(1)}/{s_m.group(1)}"
                    elif r_m:
                        self.rule = r_m.group(1)
        except Exception:
            pass
        self.seed = "initializing..."
        self.soups_completed = 0
        self.target_soups = 20000000
        self.current_rate = 0.0
        self.overall_rate = 0.0
        self.total_hauls = 0

        # Starter demo pattern (Pentadecathlon in Electric Cyan)
        starter = "xp15_4r4z4r4"
        self.discoveries.append((starter, "Oscillator", decode_apg(starter), CLR_CYAN))
        self.seen_codes.add(starter)

        self.status_msg = ""
        self.status_time = 0.0

    def set_status(self, msg, duration=3.0):
        with self.lock:
            self.status_msg = msg
            self.status_time = time.time() + duration

    def append_raw_line(self, line):
        clean = line.rstrip('\r\n')
        if not clean:
            return
        with self.lock:
            self.raw_logs.append(clean)
        self.parse_line(clean)

    def parse_line(self, line_clean):
        plain = ANSI_REGEX.sub('', line_clean)

        m_cfg = re.search(r'configured for ([^./]+)/([^.]+)', plain)
        if m_cfg:
            with self.lock:
                self.rule = f"{m_cfg.group(1)}/{m_cfg.group(2)}"

        m_tgt = re.search(r'Running (\d+) soups per haul', plain)
        if m_tgt:
            with self.lock:
                self.target_soups = int(m_tgt.group(1))

        m_seed = re.search(r'Using seed (\S+)', plain)
        if m_seed:
            with self.lock:
                self.seed = m_seed.group(1)

        m_prog = re.search(r': (\d+) soups completed \((\d+\.?\d*) soups/second current,\s*(\d+\.?\d*) overall\)', plain)
        if m_prog:
            with self.lock:
                self.soups_completed = int(m_prog.group(1))
                self.current_rate = float(m_prog.group(2))
                self.overall_rate = float(m_prog.group(3))

        # Capture detection type & match terminal color output from apgluxe
        if "Linear-growth pattern detected:" in plain:
            code = plain.split("Linear-growth pattern detected:")[-1].strip()
            self.add_discovery(code, "Linear-Growth", CLR_GREEN)
        elif "Rare oscillator detected:" in plain:
            code = plain.split("Rare oscillator detected:")[-1].strip()
            self.add_discovery(code, "Rare Oscillator", CLR_RED)
        elif "Rare spaceship detected:" in plain:
            code = plain.split("Rare spaceship detected:")[-1].strip()
            self.add_discovery(code, "Rare Spaceship", CLR_CYAN)
        elif "Chaotic-growth pattern detected:" in plain:
            code = plain.split("Chaotic-growth pattern detected:")[-1].strip()
            self.add_discovery(code, "Chaotic Growth", CLR_GREEN)
        elif "Connection was successful" in plain:
            with self.lock:
                self.total_hauls += 1

    def add_discovery(self, apcode, type_str, color_code=CLR_GREEN):
        clean = ANSI_REGEX.sub('', apcode).strip()
        cells = decode_apg(clean)
        if not cells:
            return
        with self.lock:
            if clean in self.seen_codes:
                # If seen before, switch viewport to this discovery if not already on it
                for idx, (code, _, _, _) in enumerate(self.discoveries):
                    if code == clean:
                        self.current_disc_index = idx
                        break
                return
            self.seen_codes.add(clean)
            self.discoveries.append((clean, type_str, cells, color_code))
            self.current_disc_index = len(self.discoveries) - 1

def apg_reader_thread(pipe_fd, state):
    buf = ""
    try:
        while state.is_running:
            r, _, _ = select.select([pipe_fd], [], [], 0.05)
            if not r:
                continue
            try:
                data = os.read(pipe_fd, 4096)
                if not data:
                    break
                buf += data.decode('utf-8', errors='replace')
                while '\n' in buf or '\r' in buf:
                    parts = re.split(r'[\r\n]', buf, maxsplit=1)
                    line = parts[0]
                    buf = parts[1] if len(parts) > 1 else ""
                    if line:
                        state.append_raw_line(line)
            except OSError:
                break
    finally:
        with state.lock:
            state.is_running = False

def render_halfblocks_row(engine, r, grid_w, palette, gen):
    """Renders 1 terminal row representing 2 vertical grid rows via half-blocks with age/rainbow support."""
    top_y = r * 2
    bot_y = r * 2 + 1
    row_chars = []
    mode = palette["mode"]
    static_color = palette.get("color", CLR_WHITE)

    for c in range(grid_w):
        t_cell = engine.grid[top_y][c] if top_y < engine.height else 0
        b_cell = engine.grid[bot_y][c] if bot_y < engine.height else 0

        if t_cell or b_cell:
            if mode == "age":
                t_col = get_age_color(engine.age_grid[top_y][c]) if t_cell else ""
                b_col = get_age_color(engine.age_grid[bot_y][c]) if b_cell else ""
            elif mode == "rainbow":
                t_col = get_rainbow_color(top_y, c, gen) if t_cell else ""
                b_col = get_rainbow_color(bot_y, c, gen) if b_cell else ""
            else:
                t_col = static_color
                b_col = static_color

            if t_cell and b_cell:
                if t_col == b_col:
                    row_chars.append(f"{t_col}█{CLR_RESET}")
                else:
                    b_bg = to_bg_color(b_col)
                    row_chars.append(f"{t_col}{b_bg}▀{CLR_RESET}")
            elif t_cell:
                row_chars.append(f"{t_col}▀{CLR_RESET}")
            else:
                row_chars.append(f"{b_col}▄{CLR_RESET}")
        else:
            row_chars.append(" ")

    return "".join(row_chars)

def get_cell_rgb(palette, age=1, x=0, y=0, gen=0):
    """Maps cell longevity, coordinates, or static palette to exact RGB tuple."""
    mode = palette.get("mode", "static") if palette else "static"
    if mode == "age":
        if age <= 1:   return (0, 240, 255)    # Electric Cyan (newborn)
        if age <= 3:   return (60, 140, 255)   # Sky Blue
        if age <= 6:   return (80, 250, 123)   # Lime Green (adolescent)
        if age <= 10:  return (245, 240, 60)   # Bright Yellow (mature)
        if age <= 18:  return (255, 136, 0)    # Warm Orange (established)
        if age <= 30:  return (255, 100, 200)  # Magenta (elder)
        return (255, 60, 60)                   # Crimson Red (ancient)
    elif mode == "rainbow":
        hue = (y * 8 + x * 5 + gen * 6) % 360
        h_prime = hue / 60.0
        val = int(255 * (1 - abs(h_prime % 2 - 1)))
        if h_prime < 1:   return (255, val, 0)
        elif h_prime < 2: return (val, 255, 0)
        elif h_prime < 3: return (0, 255, val)
        elif h_prime < 4: return (0, val, 255)
        elif h_prime < 5: return (val, 0, 255)
        else:             return (255, 0, val)
    else:
        if palette and palette.get("rgb"):
            return palette["rgb"]
        return (255, 255, 255)

def export_pattern_gif(apcode, rule_str='b3s23', palette=None, out_dir="exports"):
    """Simulates 1 exact period cycle and exports a seamless looping pixel-art GIF."""
    if not HAS_PIL:
        return None, "Pillow library not installed"

    try:
        os.makedirs(out_dir, exist_ok=True)
        cells = decode_apg(apcode)
        if not cells:
            return None, "Failed to decode apgcode"

        # Determine period from apcode
        p_m = re.match(r'x[pq](\d+)_', apcode)
        yl_m = re.match(r'yl(\d+)_', apcode)
        if p_m:
            period = int(p_m.group(1))
        elif yl_m:
            period = min(120, int(yl_m.group(1)))
        elif apcode.startswith('xs'):
            period = 1
        else:
            period = 30

        period = min(240, max(1, period))

        temp_engine = LifeEngine(80, 80, rule=rule_str)
        temp_engine.load_cells(cells)

        # Warm up 1 cycle so ages stabilize
        if period > 1:
            for _ in range(period):
                temp_engine.step()

        history = []
        all_x, all_y = [], []
        for _ in range(period):
            active = []
            for r in range(temp_engine.height):
                for c in range(temp_engine.width):
                    if temp_engine.grid[r][c]:
                        active.append((c, r, temp_engine.age_grid[r][c]))
                        all_x.append(c)
                        all_y.append(r)
            history.append(active)
            temp_engine.step()

        if not all_x:
            return None, "Pattern vanished"

        pad = 3
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        grid_w = max(6, max_x - min_x + 1 + pad * 2)
        grid_h = max(6, max_y - min_y + 1 + pad * 2)

        scale = 12
        img_w = grid_w * scale
        img_h = grid_h * scale

        pal_name = palette.get('name', 'white') if palette else 'white'

        frames = []
        for gen, active in enumerate(history):
            im = Image.new('RGB', (img_w, img_h), (18, 20, 26))
            draw = ImageDraw.Draw(im)

            for c, r, age in active:
                gx = c - min_x + pad
                gy = r - min_y + pad
                col = get_cell_rgb(palette, age, c, r, gen)

                x0 = gx * scale + 1
                y0 = gy * scale + 1
                x1 = (gx + 1) * scale - 2
                y1 = (gy + 1) * scale - 2
                draw.rectangle([x0, y0, x1, y1], fill=col)

            frames.append(im)

        dur = 120 if period <= 4 else (100 if period <= 15 else (80 if period <= 40 else 50))
        clean_code = re.sub(r'[^\w\-_.]', '_', apcode)
        out_name = f"{clean_code}_{pal_name}.gif"
        out_path = os.path.join(out_dir, out_name)

        if len(frames) == 1:
            frames = [frames[0], frames[0]]

        frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=dur, loop=0)
        return out_path, None
    except Exception as e:
        return None, str(e)

def format_pattern_header(cur_color, cur_type, cur_code, engine, max_width):
    """Formats clean, compact header with white type label and colored apcode."""
    p_str = f"P:{CLR_AMBER}{engine.period}{CLR_RESET}" if engine.period > 0 else f"P:{CLR_WHITE}...{CLR_RESET}"
    stats_suffix = f" {CLR_BORDER}│{CLR_RESET} {CLR_WHITE}G:{CLR_AMBER}{engine.gen}{CLR_RESET} {CLR_WHITE}Pop:{CLR_AMBER}{engine.pop}{CLR_RESET} {CLR_WHITE}{p_str} "
    vis_suffix_len = visible_length(stats_suffix)

    avail_for_name = max(10, max_width - vis_suffix_len - 2)
    type_prefix = f"{cur_type}: "
    avail_for_code = max(4, avail_for_name - len(type_prefix))

    code_part = cur_code
    if len(code_part) > avail_for_code:
        if avail_for_code > 12:
            code_part = code_part[:avail_for_code - 6] + ".." + code_part[-4:]
        else:
            code_part = code_part[:avail_for_code]

    header_str = f" {CLR_BOLD}{CLR_WHITE}{type_prefix}{CLR_RESET}{cur_color}{code_part}{CLR_RESET}{stats_suffix}"
    return fit_to_width(header_str, max_width)

def main():
    args = sys.argv[1:]
    mode = "side"

    cmd = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--mode", "-M") and i + 1 < len(args):
            mode = "vis" if "vis" in args[i+1].lower() else "side"
            i += 2
        elif a in ("--vis", "--fullscreen", "-f"):
            mode = "vis"
            i += 1
        elif a in ("--side", "-s"):
            mode = "side"
            i += 1
        else:
            cmd.append(a)
            i += 1

    if not cmd:
        default_key = os.environ.get("PAYOSHA_KEY", "QNh1WemIRtdxNuyVDz5ZkL50CxGICmC4")
        cmd = ["./apgluxe", "-n", "20000000", "-p", "8", "-k", default_key, "-L", "1"]

    state = DashboardState()
    engine = LifeEngine(60, 30, rule=state.rule)
    palette_idx = 0

    # SIGWINCH resize handling
    resized = True
    def handle_sigwinch(signum, frame):
        nonlocal resized
        resized = True
    signal.signal(signal.SIGWINCH, handle_sigwinch)

    # Spawn apgluxe via PTY
    master_fd, slave_fd = pty.openpty()
    proc_pid = os.fork()

    if proc_pid == 0:
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        try:
            os.execvp(cmd[0], cmd)
        except Exception as e:
            sys.stderr.write(f"Failed to exec {cmd[0]}: {e}\n")
            sys.exit(1)

    os.close(slave_fd)

    # Start reader thread
    t = threading.Thread(target=apg_reader_thread, args=(master_fd, state), daemon=True)
    t.start()

    # Terminal raw mode & alternate screen buffer, disable auto-wrap (\033[?7l)
    old_term_attr = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    sys.stdout.write("\033[?1049h\033[?25l\033[?7l")
    sys.stdout.flush()

    active_disc_id = -1

    try:
        while state.is_running:
            # Handle resize
            if resized:
                term_cols, term_lines = shutil.get_terminal_size((80, 24))
                term_cols = max(60, term_cols)
                term_lines = max(18, term_lines)
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
                resized = False

            term_cols, term_lines = shutil.get_terminal_size((80, 24))
            term_cols = max(60, term_cols)
            term_lines = max(18, term_lines)

            # Check for rule/symmetry updates from apgluxe
            with state.lock:
                cur_rule_full = state.rule
            cur_rule_name = cur_rule_full.split('/')[0]
            if cur_rule_name != engine.rule_string:
                engine.set_rule(cur_rule_name)
                if engine.raw_cells:
                    engine.load_cells(engine.raw_cells, reset_gen=False)

            # Check for newly discovered pattern
            with state.lock:
                cur_idx = state.current_disc_index
                if cur_idx != active_disc_id and cur_idx < len(state.discoveries):
                    active_disc_id = cur_idx
                    code, t_str, cells, _ = state.discoveries[cur_idx]
                    engine.load_cells(cells)

            # Step Life simulation
            if not state.paused:
                engine.step()

            # Snapshot state
            with state.lock:
                raw_logs_copy = list(state.raw_logs)
                if state.discoveries and active_disc_id < len(state.discoveries):
                    cur_code, cur_type, _, cur_color = state.discoveries[active_disc_id]
                else:
                    cur_code, cur_type, cur_color = "None", "None", CLR_WHITE
                rate = state.current_rate
                soups = state.soups_completed
                tgt = state.target_soups
                rule = state.rule

            current_palette = PALETTES[palette_idx]

            # =========================================================================
            # RENDER: MODE 1 (SIDE-BY-SIDE)
            # =========================================================================
            if mode == "side":
                content_rows = term_lines - 2
                left_w = max(30, (term_cols - 3) // 2)
                right_w = term_cols - left_w - 3

                grid_w = right_w
                grid_h = content_rows * 2
                engine.resize(grid_w, grid_h)

                # Top border: ╭─────┬─────╮
                rule_tag = f" [{rule}]" if left_w >= len(f" apgluxe viewer [{rule}] ") + 2 else ""
                t_l = fit_to_width(f" {CLR_BOLD}{CLR_WHITE}apgluxe viewer{rule_tag}{CLR_RESET} ", left_w)
                t_r = format_pattern_header(cur_color, cur_type, cur_code, engine, right_w)
                top_line = f"{CLR_BORDER}╭{t_l}{CLR_BORDER}┬{t_r}{CLR_BORDER}╮{CLR_RESET}"

                # Bottom controls: ╰─────┴─────╯
                pal_lbl = current_palette['label'][:8]
                now = time.time()
                with state.lock:
                    status_text = state.status_msg if now < state.status_time else ""

                if status_text:
                    b_l = fit_to_width(f" {CLR_BOLD}{CLR_GREEN}✓ {status_text}{CLR_RESET}", left_w)
                else:
                    b_l = fit_to_width(f" {CLR_GRAY}[Tab] Fullscreen  [c] {pal_lbl}  [g] GIF{CLR_RESET}", left_w)
                b_r = fit_to_width(f" {CLR_GRAY}[q] Quit  [n/p] Pattern  [space] Pause  [r] Reset{CLR_RESET} ", right_w)
                bot_line = f"{CLR_BORDER}╰{b_l}{CLR_BORDER}┴{b_r}{CLR_BORDER}╯{CLR_RESET}"

                body_lines = []
                log_slice = raw_logs_copy[-content_rows:] if len(raw_logs_copy) >= content_rows else raw_logs_copy
                log_padded = [""] * (content_rows - len(log_slice)) + log_slice

                for r in range(content_rows):
                    log_text = log_padded[r] if r < len(log_padded) else ""
                    left_cell = fit_to_width(log_text, left_w)
                    right_cell = render_halfblocks_row(engine, r, grid_w, current_palette, engine.gen)

                    row_str = f"{CLR_BORDER}│{CLR_RESET}{left_cell}{CLR_BORDER}│{CLR_RESET}{right_cell}{CLR_BORDER}│{CLR_RESET}"
                    body_lines.append(row_str)

                all_lines = [top_line] + body_lines + [bot_line]
                sys.stdout.write("\033[H" + "\n".join(all_lines))
                sys.stdout.flush()

            # =========================================================================
            # RENDER: MODE 2 (JUST VISUALIZATION / FULLSCREEN)
            # =========================================================================
            else:
                content_rows = term_lines - 3
                grid_w = term_cols - 2
                grid_h = content_rows * 2
                engine.resize(grid_w, grid_h)

                t_str = format_pattern_header(cur_color, cur_type, cur_code, engine, term_cols - 2)
                top_line = f"{CLR_BORDER}╭{t_str}{CLR_BORDER}╮{CLR_RESET}"

                pct = (soups / tgt) * 100 if tgt > 0 else 0
                pct = min(100.0, pct)
                stats_str = fit_to_width(f" Search: {rule} | Rate: {rate:,.0f} soups/s | Haul: {pct:5.1f}% ({soups:,}/{tgt:,}) | Total Hauls: {state.total_hauls}", term_cols - 2)
                stats_line = f"{CLR_BORDER}│{CLR_BOLD}{CLR_AMBER}{stats_str}{CLR_RESET}{CLR_BORDER}│{CLR_RESET}"

                pal_lbl = current_palette['label'][:8]
                now = time.time()
                with state.lock:
                    status_text = state.status_msg if now < state.status_time else ""

                if status_text:
                    b_str = fit_to_width(f" {CLR_BOLD}{CLR_GREEN}✓ {status_text}{CLR_RESET}", term_cols - 2)
                else:
                    b_str = fit_to_width(f" {CLR_GRAY}[Tab] Side-by-side  [q] Quit  [c] {pal_lbl}  [g] GIF  [n/p] Pattern  [space] Pause  [r] Reset{CLR_RESET} ", term_cols - 2)
                bot_line = f"{CLR_BORDER}╰{b_str}{CLR_BORDER}╯{CLR_RESET}"

                body_lines = []
                for r in range(content_rows):
                    vis_cell = render_halfblocks_row(engine, r, grid_w, current_palette, engine.gen)
                    body_lines.append(f"{CLR_BORDER}│{CLR_RESET}{vis_cell}{CLR_BORDER}│{CLR_RESET}")

                all_lines = [top_line, stats_line] + body_lines + [bot_line]
                sys.stdout.write("\033[H" + "\n".join(all_lines))
                sys.stdout.flush()

            # Non-blocking input handling (~30 FPS delay)
            r_keys, _, _ = select.select([sys.stdin], [], [], 0.033)
            if r_keys:
                ch = sys.stdin.read(1)
                if ch in ('q', 'Q', '\x03'):
                    break
                elif ch in ('\t', 'm', 'M'):
                    mode = "vis" if mode == "side" else "side"
                    resized = True
                elif ch in ('c', 'C'):
                    palette_idx = (palette_idx + 1) % len(PALETTES)
                elif ch in ('g', 'G'):
                    def do_export(code, r_str, pal):
                        out_path, err = export_pattern_gif(code, r_str, pal)
                        if out_path:
                            state.set_status(f"Saved: {out_path}", 3.5)
                        else:
                            state.set_status(f"Export failed: {err}", 3.5)

                    with state.lock:
                        if state.discoveries and active_disc_id < len(state.discoveries):
                            code_to_export = state.discoveries[active_disc_id][0]
                        else:
                            code_to_export = None
                        r_curr = state.rule.split('/')[0]

                    if code_to_export:
                        active_pal = PALETTES[palette_idx]
                        state.set_status("Exporting GIF...", 2.0)
                        threading.Thread(target=do_export, args=(code_to_export, r_curr, active_pal), daemon=True).start()
                elif ch in ('n', 'N'):
                    with state.lock:
                        if state.discoveries:
                            state.current_disc_index = (state.current_disc_index + 1) % len(state.discoveries)
                elif ch in ('p', 'P'):
                    with state.lock:
                        if state.discoveries:
                            state.current_disc_index = (state.current_disc_index - 1) % len(state.discoveries)
                elif ch == ' ':
                    state.paused = not state.paused
                elif ch in ('r', 'R'):
                    with state.lock:
                        if state.discoveries and active_disc_id < len(state.discoveries):
                            _, _, cells, _ = state.discoveries[active_disc_id]
                            engine.load_cells(cells)

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?1049l\033[?25h\033[?7h")
        sys.stdout.flush()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term_attr)

        print("\n\033[1;33m[apg_dashboard] Interrupt received. Gracefully shutting down apgluxe...\033[0m")
        try:
            os.kill(proc_pid, signal.SIGINT)
            for _ in range(12):
                pid, status = os.waitpid(proc_pid, os.WNOHANG)
                if pid != 0:
                    break
                time.sleep(0.5)
        except OSError:
            pass

        print("\033[1;32m[apg_dashboard] Clean exit completed.\033[0m\n")

if __name__ == "__main__":
    main()
