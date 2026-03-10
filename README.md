# mediasort

An interactive TUI tool for sorting media files into organized folders — movies, TV shows, music, and downloads.

Built for homelabbers running Plex/Jellyfin + the *arr stack who want a fast way to clean up a messy media directory.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Interactive TUI** — arrow-key friendly, color-coded interface
- **Auto-detection** — recognizes TV episodes, movies, and music from filename patterns
- **Confidence scoring** — shows how certain the detection is before you confirm
- **Undo log** — every move is recorded; press `Z` to undo the last move
- **Dry-run mode** — preview all moves without touching anything
- **`--auto` flag** — auto-moves high-confidence matches (≥80%), prompts only on ambiguous ones
- **Custom destinations** — point movies/tv/music/downloads at any path

---

## Install

```bash
git clone https://github.com/xdfsx/mediasort
cd mediasort
chmod +x mediasort.py
```

No dependencies beyond Python 3.10+ standard library (`curses` is built in).

Optionally symlink for system-wide use:
```bash
sudo ln -s $(pwd)/mediasort.py /usr/local/bin/mediasort
```

---

## Usage

```bash
# Basic — sort everything in your media folder interactively
mediasort /your/media/folder

# Dry run — preview without moving anything
mediasort /your/media/folder --dry-run

# Auto-move confident matches, prompt on uncertain ones
mediasort /your/media/folder --auto

# Custom destination folders
mediasort /your/media/folder \
  --movies /your/media/folder/movies \
  --tv /your/media/folder/tv \
  --music /your/media/folder/music \
  --downloads /your/media/folder/downloads
```

### Keyboard controls

| Key     | Action                          |
|---------|---------------------------------|
| `T`     | Move to `/tv`                   |
| `M`     | Move to `/movies`               |
| `U`     | Move to `/music`                |
| `D`     | Move to `/downloads`            |
| `S`     | Skip this item                  |
| `↵`     | Accept auto-detected suggestion |
| `Z`     | Undo last move                  |
| `Q`     | Quit                            |

---

## Detection logic

mediasort scores each filename against known patterns:

**TV** — matches: `S01E01`, `1x01`, `Season 1`, `S01`, `COMPLETE`, `Complete Series`  
**Movies** — matches: `(2024)`, `2024.1080p`, `BluRay`, `WEBRip`, `WEB-DL`, `4K`  
**Music** — matches: `Mp3`, `FLAC`, `Album`, `Discography`, `Soundtrack`

Confidence is shown as a progress bar. Items scoring ≥80% can be auto-moved with `--auto`.

---

## Undo log

All moves are recorded in `.mediasort_log.json` in the source directory (or specify with `--log`).

Press `Z` during a session to undo the last move. To undo manually:

```bash
cat /Family/.mediasort_log.json
```

---

## Use case

Perfect after setting up a new Plex/Jellyfin library or after migrating from a flat media folder to a structured one. Pairs well with Sonarr, Radarr, and qBittorrent.

---

## License

MIT
