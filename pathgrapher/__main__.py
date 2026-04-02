"""Entry point: python -m pathgrapher [path]"""

import configparser
import sys
from pathlib import Path

from .gui import App
from .scanner import start_scan

SETTINGS_FILE = Path(__file__).parent.parent / "settings.ini"


def _load_config() -> tuple[frozenset[str], int, float, float]:
    config = configparser.RawConfigParser(allow_no_value=True)
    config.optionxform = lambda optionstr: optionstr  # preserve original case
    config.read(SETTINGS_FILE)

    if "ignore-paths" in config:
        ignore_names = frozenset(key for key in config["ignore-paths"])
    else:
        ignore_names = frozenset()

    try:
        min_font_size = int(config["fonts"]["min_size"])
    except (KeyError, ValueError):
        min_font_size = 8

    try:
        cache_ttl = float(config["cache"]["ttl_seconds"])
    except (KeyError, ValueError):
        cache_ttl = 300.0

    try:
        min_pct = float(config["display"]["min_pct"])
    except (KeyError, ValueError):
        min_pct = 1.0

    return ignore_names, min_font_size, cache_ttl, min_pct


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    ignore_names, min_font_size, cache_ttl, min_pct = _load_config()
    q = start_scan(root, ignore_names=ignore_names)
    app = App(
        root, q,
        ignore_names=ignore_names,
        min_font_size=min_font_size,
        cache_ttl=cache_ttl,
        min_pct=min_pct,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
