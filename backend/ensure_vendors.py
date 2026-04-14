"""
backend/ensure_vendors.py

Automatically downloads front-end vendor assets on first run (or when they are
missing).  This keeps the repository free of large binary blobs while still
allowing the app to work fully offline after the first startup.

Vendor files managed
--------------------
  vendor/css/bootstrap.min.css            – Bootstrap 5.3.3 CSS
  vendor/css/bootstrap-icons.css          – Bootstrap Icons 1.10.5 CSS
  vendor/css/fonts/bootstrap-icons.woff2  – Bootstrap Icons font (woff2)
  vendor/css/fonts/bootstrap-icons.woff   – Bootstrap Icons font (woff)
  vendor/js/bootstrap.bundle.min.js       – Bootstrap 5.3.3 JS bundle
  vendor/js/vue.global.prod.js            – Vue 3.5.13 production build
  vendor/js/plotly-2.35.2.min.js          – Plotly 2.35.2

Usage
-----
Called automatically by app.py at startup:

    from backend.ensure_vendors import ensure_vendors
    ensure_vendors()

Can also be run directly:

    python -m backend.ensure_vendors
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – vendor root relative to this file's package root
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent  # backend/
_REPO = _HERE.parent  # project root
_VENDOR = _REPO / "frontend" / "static" / "vendor"

_BOOTSTRAP_VERSION = "5.3.3"
_BOOTSTRAP_ICONS_VERSION = "1.10.5"
_VUE_VERSION = "3.5.13"
_PLOTLY_VERSION = "2.35.2"

# (local_relative_path, download_url)
_ASSETS: list[tuple[str, str]] = [
    (
        "css/bootstrap.min.css",
        f"https://cdn.jsdelivr.net/npm/bootstrap@{_BOOTSTRAP_VERSION}/dist/css/bootstrap.min.css",
    ),
    (
        "css/bootstrap-icons.css",
        f"https://cdn.jsdelivr.net/npm/bootstrap-icons@{_BOOTSTRAP_ICONS_VERSION}/font/bootstrap-icons.css",
    ),
    (
        # Fonts must live at vendor/css/fonts/ so the @font-face url("./fonts/…")
        # reference in bootstrap-icons.css resolves correctly.
        "css/fonts/bootstrap-icons.woff2",
        f"https://cdn.jsdelivr.net/npm/bootstrap-icons@{_BOOTSTRAP_ICONS_VERSION}/font/fonts/bootstrap-icons.woff2",
    ),
    (
        "css/fonts/bootstrap-icons.woff",
        f"https://cdn.jsdelivr.net/npm/bootstrap-icons@{_BOOTSTRAP_ICONS_VERSION}/font/fonts/bootstrap-icons.woff",
    ),
    (
        "js/bootstrap.bundle.min.js",
        f"https://cdn.jsdelivr.net/npm/bootstrap@{_BOOTSTRAP_VERSION}/dist/js/bootstrap.bundle.min.js",
    ),
    (
        "js/vue.global.prod.js",
        f"https://unpkg.com/vue@{_VUE_VERSION}/dist/vue.global.prod.js",
    ),
    (
        f"js/plotly-{_PLOTLY_VERSION}.min.js",
        f"https://cdn.plot.ly/plotly-{_PLOTLY_VERSION}.min.js",
    ),
]


# ---------------------------------------------------------------------------
# Core downloader
# ---------------------------------------------------------------------------


def _download(url: str, dest: Path) -> None:
    """Download *url* to *dest*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s …", url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; hospital-operations-system/1.0; "
            "+https://github.com/placeholder)"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
        content: bytes = response.read()
    dest.write_bytes(content)
    size_kb = len(content) // 1024
    logger.info("  → saved %s (%d KB)", dest.relative_to(_REPO), size_kb)


def ensure_vendors(force: bool = False) -> None:
    """
    Check every vendor asset; download any that are missing (or all if *force*
    is True).

    Parameters
    ----------
    force:
        Re-download every asset even if already present.  Useful for
        updating dependencies.
    """
    missing = []
    for rel, url in _ASSETS:
        dest = _VENDOR / rel
        if force or not dest.exists():
            missing.append((rel, url))

    if not missing:
        logger.debug("All vendor assets already present – skipping download.")
        return

    print(
        f"[ensure_vendors] Downloading {len(missing)} missing vendor "
        f"asset(s) – this only happens on first startup …"
    )
    for rel, url in missing:
        dest = _VENDOR / rel
        try:
            _download(url, dest)
            print(f"  ✓  {rel}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to download %s: %s", url, exc)
            print(f"  ✗  {rel}  (ERROR: {exc})")
            # Continue with remaining assets; the app may still work if only
            # some are missing (e.g., fonts are non-critical for functionality).

    print("[ensure_vendors] Done.\n")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_vendors(force="--force" in __import__("sys").argv)
