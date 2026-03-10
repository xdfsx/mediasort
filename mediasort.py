#!/usr/bin/env python3
"""
mediasort - Interactive TUI media file organizer
github.com/xdfsx/mediasort
"""

import os
import sys
import re
import shutil
import json
import argparse
import curses
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
#  Detection patterns
# ─────────────────────────────────────────────

TV_PATTERNS = [
    r'[Ss]\d{1,2}[Ee]\d{1,2}',           # S01E01
    r'\d{1,2}x\d{2}',                      # 1x01
    r'[Ss]eason\s*\d+',                    # Season 1 / season1
    r'\bS\d{2}\b',                         # S01 alone
    r'Complete.Series',                     # Complete Series
    r'COMPLETE',                            # COMPLETE pack
    r'TV.Shows?',                           # TV Show/Shows
]

MOVIE_PATTERNS = [
    r'\((?:19|20)\d{2}\)',                  # (1999) or (2024)
    r'(?:19|20)\d{2}\.(?:1080|2160|720)',  # 2024.1080p
    r'\b(?:1080p|2160p|4K|BluRay|WEBRip|WEB-DL|HDTV)\b',
]

MUSIC_PATTERNS = [
    r'Mp3|FLAC|AAC|Album|Discography|OST|Soundtrack',
    r'\bmp3\b|\bflac\b',
]

SKIP_NAMES = {
    'movies', 'tv', 'music', 'downloads', 'omvbackup',
    'wedding pics', 'Data', 'Stuff', 'Movies1_backup',
    'lost+found', '.recycle', '@eaDir', '#recycle',
}

SKIP_EXTENSIONS = {'.part', '.tmp', '.!qb', '.crdownload'}


# ─────────────────────────────────────────────
#  Auto-detection
# ─────────────────────────────────────────────

def detect_category(name: str) -> tuple[str, float]:
    """Returns (category, confidence) where confidence is 0.0-1.0"""
    # Check music first (most specific)
    for pat in MUSIC_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            return 'music', 0.9

    # Check TV
    tv_score = 0
    for pat in TV_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            tv_score += 1
    if tv_score >= 2:
        return 'tv', 0.95
    if tv_score == 1:
        return 'tv', 0.80

    # Check movie
    movie_score = 0
    for pat in MOVIE_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            movie_score += 1
    if movie_score >= 2:
        return 'movies', 0.90
    if movie_score == 1:
        return 'movies', 0.65

    return 'unknown', 0.0


def should_skip(name: str, path: Path) -> bool:
    if name in SKIP_NAMES:
        return True
    if name.startswith('.'):
        return True
    if path.is_file():
        if path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        # Only process media files
        media_ext = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.wmv',
                     '.flac', '.mp3', '.m4a', '.aac', '.wav'}
        if path.suffix.lower() not in media_ext and path.is_file():
            # Allow files without extension (rare) but skip obvious non-media
            non_media = {'.iso', '.exe', '.zip', '.rar', '.7z', '.nfo',
                        '.txt', '.jpg', '.png', '.srt', '.sub', '.idx',
                        '.pub', '.sh', '.py', '.json', '.xml'}
            if path.suffix.lower() in non_media:
                return True
    return False


# ─────────────────────────────────────────────
#  Undo log
# ─────────────────────────────────────────────

class UndoLog:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries = []
        if log_path.exists():
            with open(log_path) as f:
                self.entries = json.load(f)

    def record(self, src: str, dst: str):
        self.entries.append({
            'src': src,
            'dst': dst,
            'time': datetime.now().isoformat(),
        })
        self._save()

    def undo_last(self) -> tuple[bool, str]:
        if not self.entries:
            return False, "Nothing to undo."
        entry = self.entries.pop()
        src = entry['dst']  # reverse: dst becomes src
        dst = entry['src']
        if not Path(src).exists():
            return False, f"File no longer exists: {src}"
        try:
            shutil.move(src, dst)
            self._save()
            return True, f"Restored: {Path(dst).name}"
        except Exception as e:
            return False, str(e)

    def _save(self):
        with open(self.log_path, 'w') as f:
            json.dump(self.entries, f, indent=2)


# ─────────────────────────────────────────────
#  Move logic
# ─────────────────────────────────────────────

def do_move(src: Path, dest_dir: Path, undo_log: UndoLog, dry_run: bool) -> tuple[bool, str]:
    dest = dest_dir / src.name
    if dest.exists():
        return False, f"Already exists at destination"
    if dry_run:
        return True, f"[DRY RUN] Would move to {dest_dir.name}/"
    try:
        shutil.move(str(src), str(dest))
        undo_log.record(str(src), str(dest))
        return True, f"Moved to {dest_dir.name}/"
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
#  TUI
# ─────────────────────────────────────────────

# Colors
C_TITLE   = 1
C_ITEM    = 2
C_TV      = 3
C_MOVIE   = 4
C_MUSIC   = 5
C_UNKNOWN = 6
C_SUCCESS = 7
C_ERROR   = 8
C_DIM     = 9
C_HEADER  = 10

CATEGORY_COLORS = {
    'tv':      C_TV,
    'movies':  C_MOVIE,
    'music':   C_MUSIC,
    'unknown': C_UNKNOWN,
}

CATEGORY_LABELS = {
    'tv':      ' TV ',
    'movies':  'MOV ',
    'music':   'MUS ',
    'unknown': ' ?  ',
}


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE,   curses.COLOR_CYAN,    -1)
    curses.init_pair(C_ITEM,    curses.COLOR_WHITE,   -1)
    curses.init_pair(C_TV,      curses.COLOR_GREEN,   -1)
    curses.init_pair(C_MOVIE,   curses.COLOR_BLUE,    -1)
    curses.init_pair(C_MUSIC,   curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_UNKNOWN, curses.COLOR_YELLOW,  -1)
    curses.init_pair(C_SUCCESS, curses.COLOR_GREEN,   -1)
    curses.init_pair(C_ERROR,   curses.COLOR_RED,     -1)
    curses.init_pair(C_DIM,     curses.COLOR_BLACK,   -1)
    curses.init_pair(C_HEADER,  curses.COLOR_CYAN,    -1)


def draw_header(stdscr, source_dir: Path, dry_run: bool, done: int, total: int):
    h, w = stdscr.getmaxyx()
    stdscr.attron(curses.color_pair(C_TITLE) | curses.A_BOLD)
    title = " mediasort "
    stdscr.addstr(0, (w - len(title)) // 2, title)
    stdscr.attroff(curses.color_pair(C_TITLE) | curses.A_BOLD)

    stdscr.attron(curses.color_pair(C_DIM))
    src_str = f" Source: {source_dir} "
    stdscr.addstr(1, 0, src_str[:w-1])
    stdscr.attroff(curses.color_pair(C_DIM))

    if dry_run:
        stdscr.attron(curses.color_pair(C_UNKNOWN) | curses.A_BOLD)
        stdscr.addstr(1, w - 14, " [DRY RUN] ")
        stdscr.attroff(curses.color_pair(C_UNKNOWN) | curses.A_BOLD)

    progress = f" {done}/{total} sorted "
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(2, 0, "─" * (w - 1))
    stdscr.attroff(curses.color_pair(C_DIM))
    stdscr.attron(curses.color_pair(C_TITLE))
    stdscr.addstr(2, 2, progress)
    stdscr.attroff(curses.color_pair(C_TITLE))


def draw_item(stdscr, row: int, name: str, category: str, confidence: float, w: int):
    cat_color = CATEGORY_COLORS.get(category, C_UNKNOWN)
    cat_label = CATEGORY_LABELS.get(category, ' ?  ')

    # Badge
    stdscr.attron(curses.color_pair(cat_color) | curses.A_BOLD)
    stdscr.addstr(row, 2, f"[{cat_label}]")
    stdscr.attroff(curses.color_pair(cat_color) | curses.A_BOLD)

    # Confidence bar
    conf_pct = int(confidence * 10)
    conf_str = f" {'█' * conf_pct}{'░' * (10 - conf_pct)} {int(confidence*100):3d}%"
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, 10, conf_str)
    stdscr.attroff(curses.color_pair(C_DIM))

    # Filename (truncated)
    max_name = w - 30
    display_name = name if len(name) <= max_name else name[:max_name - 3] + "..."
    stdscr.attron(curses.color_pair(C_ITEM))
    stdscr.addstr(row + 1, 2, display_name)
    stdscr.attroff(curses.color_pair(C_ITEM))


def draw_controls(stdscr, h: int, w: int, category: str):
    row = h - 4
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(row, 0, "─" * (w - 1))
    stdscr.attroff(curses.color_pair(C_DIM))

    controls = [
        ("T", "tv",       C_TV),
        ("M", "movies",   C_MOVIE),
        ("U", "music",    C_MUSIC),
        ("D", "downloads",C_DIM),
        ("S", "skip",     C_DIM),
        ("Z", "undo",     C_UNKNOWN),
        ("Q", "quit",     C_ERROR),
    ]

    x = 2
    row += 1
    for key, label, color in controls:
        stdscr.attron(curses.color_pair(color) | curses.A_BOLD)
        stdscr.addstr(row, x, f" {key} ")
        stdscr.attroff(curses.color_pair(color) | curses.A_BOLD)
        stdscr.attron(curses.color_pair(C_ITEM))
        stdscr.addstr(row, x + 3, f"{label}  ")
        stdscr.attroff(curses.color_pair(C_ITEM))
        x += len(label) + 6

    # Hint: Enter = accept suggestion
    if category != 'unknown':
        hint = f"  ↵ accept suggestion [{category}]"
        stdscr.attron(curses.color_pair(C_DIM))
        stdscr.addstr(row + 1, 2, hint)
        stdscr.attroff(curses.color_pair(C_DIM))


def draw_status(stdscr, h: int, w: int, msg: str, is_error: bool = False):
    color = C_ERROR if is_error else C_SUCCESS
    stdscr.attron(curses.color_pair(color))
    stdscr.addstr(h - 1, 2, msg[:w - 4])
    stdscr.attroff(curses.color_pair(color))


def tui_main(stdscr, items, dest_dirs, dry_run, undo_log, auto_mode):
    curses.curs_set(0)
    init_colors()

    total = len(items)
    done = 0
    status_msg = ""
    status_err = False

    for i, (path, category, confidence) in enumerate(items):
        name = path.name

        # Auto mode: move confident matches without prompting
        if auto_mode and confidence >= 0.80 and category != 'unknown':
            dest = dest_dirs.get(category)
            if dest:
                ok, msg = do_move(path, dest, undo_log, dry_run)
                done += 1
                status_msg = f"AUTO: {name[:40]} → {msg}"
                status_err = not ok
            continue

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()

            draw_header(stdscr, path.parent, dry_run, done, total)
            draw_item(stdscr, 4, name, category, confidence, w)
            draw_controls(stdscr, h, w, category)
            if status_msg:
                draw_status(stdscr, h, w, status_msg, status_err)

            stdscr.refresh()
            key = stdscr.getch()

            action = None
            if key in (ord('t'), ord('T')):
                action = 'tv'
            elif key in (ord('m'), ord('M')):
                action = 'movies'
            elif key in (ord('u'), ord('U')):
                action = 'music'
            elif key in (ord('d'), ord('D')):
                action = 'downloads'
            elif key in (ord('s'), ord('S')):
                action = 'skip'
            elif key in (ord('z'), ord('Z')):
                ok, msg = undo_log.undo_last()
                status_msg = msg
                status_err = not ok
                if ok:
                    done = max(0, done - 1)
                continue
            elif key in (ord('q'), ord('Q')):
                return
            elif key in (10, 13):  # Enter = accept suggestion
                if category != 'unknown':
                    action = category
                else:
                    status_msg = "No suggestion to accept — pick manually"
                    status_err = True
                    continue

            if action == 'skip':
                status_msg = f"Skipped: {name[:50]}"
                status_err = False
                break
            elif action in dest_dirs:
                dest = dest_dirs[action]
                ok, msg = do_move(path, dest, undo_log, dry_run)
                status_msg = f"{name[:40]} → {msg}"
                status_err = not ok
                if ok:
                    done += 1
                break

    # Done screen
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    msg = f"  All done! {done}/{total} items sorted."
    if dry_run:
        msg += " (dry run — nothing actually moved)"
    stdscr.attron(curses.color_pair(C_SUCCESS) | curses.A_BOLD)
    stdscr.addstr(h // 2, max(0, (w - len(msg)) // 2), msg)
    stdscr.attroff(curses.color_pair(C_SUCCESS) | curses.A_BOLD)
    stdscr.attron(curses.color_pair(C_DIM))
    stdscr.addstr(h // 2 + 1, (w - 20) // 2, "  Press any key to exit  ")
    stdscr.attroff(curses.color_pair(C_DIM))
    stdscr.refresh()
    stdscr.getch()


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='mediasort — Interactive TUI media organizer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mediasort /Family
  mediasort /Family --dry-run
  mediasort /Family --auto
  mediasort /Family --movies /data/movies --tv /data/tv
        """
    )
    parser.add_argument('source', help='Directory to sort')
    parser.add_argument('--movies',   default=None, help='Movies destination (default: source/movies)')
    parser.add_argument('--tv',       default=None, help='TV destination (default: source/tv)')
    parser.add_argument('--music',    default=None, help='Music destination (default: source/music)')
    parser.add_argument('--downloads',default=None, help='Downloads destination (default: source/downloads)')
    parser.add_argument('--dry-run',  action='store_true', help='Preview moves without doing anything')
    parser.add_argument('--auto',     action='store_true', help='Auto-move high-confidence matches, prompt on rest')
    parser.add_argument('--log',      default=None, help='Path to undo log (default: source/.mediasort_log.json)')
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"Error: {source} is not a directory", file=sys.stderr)
        sys.exit(1)

    dest_dirs = {
        'movies':    Path(args.movies)    if args.movies    else source / 'movies',
        'tv':        Path(args.tv)        if args.tv        else source / 'tv',
        'music':     Path(args.music)     if args.music     else source / 'music',
        'downloads': Path(args.downloads) if args.downloads else source / 'downloads',
    }

    # Create dest dirs if missing
    for d in dest_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    log_path = Path(args.log) if args.log else source / '.mediasort_log.json'
    undo_log = UndoLog(log_path)

    # Collect items
    items = []
    for entry in sorted(source.iterdir()):
        if should_skip(entry.name, entry):
            continue
        category, confidence = detect_category(entry.name)
        items.append((entry, category, confidence))

    if not items:
        print("Nothing to sort — all items are already organized or skipped.")
        sys.exit(0)

    print(f"Found {len(items)} items to sort.")
    if args.dry_run:
        print("DRY RUN MODE — nothing will be moved.\n")

    curses.wrapper(tui_main, items, dest_dirs, args.dry_run, undo_log, args.auto)


if __name__ == '__main__':
    main()
