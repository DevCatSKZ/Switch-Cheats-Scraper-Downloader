#!/usr/bin/env python3
"""
CheatSlips.com Scraper

Scrapes Nintendo Switch cheat codes from https://www.cheatslips.com/.

Modes:
  - metadata : Scrape all games, their title IDs, build IDs and cheat names
               (no login required, no reCAPTCHA).
  - download : Log in with a browser and download the actual cheat code text
               (login + reCAPTCHA required by the site).

Usage:
    python scraper.py metadata --output ./metadata
    python scraper.py download --output ./cheats --headless

After starting the download mode, a browser window opens. You must log in to
CheatSlips.com and solve the reCAPTCHA manually. The script then continues
automatically and scrapes all cheat files.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from tqdm import tqdm

from bs4 import BeautifulSoup

# --- Application identity --------------------------------------------------
APP_NAME = "Switch Cheats Scraper & Downloader"
APP_VERSION = "1.3"
APP_AUTHOR = "DevCatSKZ"

BASE_URL = "https://www.cheatslips.com"

# --- Prebuilt data hosted by the maintainer (so users need not scrape) -------
# A dedicated GitHub release (tag DEVCAT_DATA_TAG) holds two assets: the full
# cheats archive (DEVCAT_CHEATS_ASSET) and the complete GUI database
# (DEVCAT_DB_ASSET). The app can download either or both from there.
DEVCAT_REPO = "DevCatSKZ/Switch-Cheats-Scraper-Downloader"
DEVCAT_DATA_TAG = "data"
DEVCAT_CHEATS_ASSET = "switch-cheats.zip"
DEVCAT_DB_ASSET = "database.db"

# Columns holding third-party PUBLISHER text (Nintendo eShop marketing copy).
# They are nice to have LOCALLY (fetch anytime via "Get Descriptions"), but must
# not be part of the REDISTRIBUTED database — republishing that text would be a
# copyright concern. Cheat descriptions/credits are community content and stay.
SHARED_DB_STRIP_COLUMNS = ("game_description", "intro")


def export_shared_db(src_db, dst_db, strip_publisher_text: bool = True) -> dict:
    """Write a redistribution-ready copy of *src_db* to *dst_db*.

    With ``strip_publisher_text`` (default), the publisher eShop text columns
    (see SHARED_DB_STRIP_COLUMNS) are cleared and the copy is VACUUMed so the
    shared database carries only facts, cheat metadata and community notes.
    Returns {column: rows_cleared, "_before": bytes, "_after": bytes}.
    """
    import shutil
    src, dst = Path(src_db), Path(dst_db)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Consistent copy via sqlite's online backup (safe even if src is in use).
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    s.close(); d.close()
    result = {"_before": src.stat().st_size}
    if strip_publisher_text:
        con = sqlite3.connect(str(dst))
        try:
            existing = {r[1] for r in con.execute("PRAGMA table_info(builds)")}
            for col in SHARED_DB_STRIP_COLUMNS:
                if col not in existing:
                    continue
                n = con.execute(
                    f"SELECT COUNT(*) FROM builds WHERE {col} IS NOT NULL "
                    f"AND {col}<>''").fetchone()[0]
                con.execute(f"UPDATE builds SET {col}=NULL")
                result[col] = n
            con.commit()
            con.execute("VACUUM")
            # Ship a single self-contained file: checkpoint and leave WAL mode so
            # no -wal/-shm sidecars linger next to the redistributed database.db
            # (the source may be in WAL mode, which the backup copies over).
            con.execute("PRAGMA journal_mode=DELETE")
        finally:
            con.close()
    else:
        # Full 1:1 copy: normalise the journal mode too, so a shared copy is a
        # clean single file regardless of the source's journal mode.
        con = sqlite3.connect(str(dst))
        try:
            con.execute("PRAGMA journal_mode=DELETE")
        finally:
            con.close()
    result["_after"] = dst.stat().st_size
    return result

# --- Self-update (program build hosted on the same repo's latest release) -----
# The "latest" GitHub release carries the installer (and optional portable zip).
# The updater compares versions AND asset upload times, so a re-upload of the
# same version (a fix without a version bump) is detected too.
GITHUB_API = "https://api.github.com"
PROGRAM_SETUP_ASSET = "SwitchCheatsScraper-Setup.exe"
PROGRAM_PORTABLE_ASSET = "SwitchCheatsScraper-portable.zip"

# --- Switch homebrew app (the on-console counterpart of this tool) -----------
# A fixed-tag release ("nro") always carries the LATEST .nro build; its version
# lives in the release *title* (e.g. "v1.2.0") because the tag never changes.
# On the SD card the app belongs into /switch/ so hbmenu can launch it.
NRO_RELEASE_TAG = "nro"
NRO_ASSET = "SwitchCheatsDownloader.nro"
NRO_SD_DIR = "switch"


def devcat_asset_url(asset: str) -> str:
    """Public download URL of a maintainer-hosted data asset."""
    return (f"https://github.com/{DEVCAT_REPO}/releases/download/"
            f"{DEVCAT_DATA_TAG}/{asset}")


def parse_version(v) -> tuple:
    """Turn a version string like 'v1.2.3' into a comparable tuple (1, 2, 3)."""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums) if nums else (0,)


def version_is_newer(candidate, current) -> bool:
    """True when *candidate* is a strictly higher version than *current*."""
    return parse_version(candidate) > parse_version(current)


def github_iso_to_epoch(s) -> float:
    """Parse a GitHub ISO-8601 timestamp ('2026-07-05T12:34:56Z') to epoch secs.

    Returns 0.0 on anything unparseable, so callers can compare safely.
    """
    if not s:
        return 0.0
    try:
        txt = str(s).strip().replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(txt).timestamp()
    except Exception:
        try:
            return datetime.datetime.strptime(
                str(s)[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=datetime.timezone.utc).timestamp()
        except Exception:
            return 0.0


def fetch_github_release(tag: Optional[str] = None, repo: str = DEVCAT_REPO,
                         timeout: int = 15) -> dict:
    """Fetch and normalise a GitHub release.

    ``tag=None`` fetches ``/releases/latest`` (the program build); a tag string
    fetches ``/releases/tags/<tag>`` (e.g. the ``data`` release). Raises on
    network/HTTP error. The returned dict is normalised to::

        {
          "tag": str, "version": str, "name": str, "html_url": str,
          "body": str, "published_at": str,
          "published_epoch": float,      # release publish time
          "newest_epoch": float,         # newest asset upload time (or publish)
          "assets": [ {name, updated_at, epoch, size, url}, ... ],
        }
    """
    import requests

    url = f"{GITHUB_API}/repos/{repo}/releases/"
    url += f"tags/{tag}" if tag else "latest"
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": f"{APP_NAME}/{APP_VERSION}",
               "X-GitHub-Api-Version": "2022-11-28"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    assets = []
    for a in data.get("assets") or []:
        when = a.get("updated_at") or a.get("created_at")
        assets.append({
            "name": a.get("name", ""),
            "updated_at": when,
            "epoch": github_iso_to_epoch(when),
            "size": a.get("size", 0),
            "url": a.get("browser_download_url"),
            # GitHub publishes a content digest per asset ("sha256:<hex>") —
            # the self-updater verifies downloads against it before installing.
            "digest": a.get("digest") or "",
        })
    published = data.get("published_at") or data.get("created_at")
    pub_epoch = github_iso_to_epoch(published)
    newest = max([a["epoch"] for a in assets] + [pub_epoch]) if assets else pub_epoch
    tag_name = data.get("tag_name") or ""
    return {
        "tag": tag_name,
        "version": tag_name.lstrip("vV") or APP_VERSION,
        "name": data.get("name") or tag_name,
        "html_url": data.get("html_url"),
        "body": data.get("body") or "",
        "published_at": published,
        "published_epoch": pub_epoch,
        "newest_epoch": newest,
        "assets": assets,
    }


def find_release_asset(release: dict, name: str) -> Optional[dict]:
    """Return the asset dict whose file name matches *name* (case-insensitive)."""
    for a in release.get("assets", []):
        if (a.get("name") or "").lower() == name.lower():
            return a
    return None


def download_file(url: str, dest, progress_cb=None, should_stop=None,
                  chunk: int = 262144) -> int:
    """Stream a URL to *dest*, reporting (bytes_done, total_or_0) via progress_cb.

    Returns the number of bytes written. Raises on HTTP/network error. Writes to
    a .part file first and renames on success so a partial download never leaves
    a truncated final file.
    """
    import requests

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    written = 0
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        with open(part, "wb") as f:
            for block in r.iter_content(chunk_size=chunk):
                if should_stop and should_stop():
                    raise RuntimeError("Stopped by user.")
                if not block:
                    continue
                f.write(block)
                written += len(block)
                if progress_cb:
                    progress_cb(written, total)
    part.replace(dest)
    return written


def fetch_switch_app_info(timeout: int = 15) -> dict:
    """Version + download URL of the latest Switch homebrew app (.nro).

    Reads the fixed-tag ``nro`` release; the app version is carried in the
    release *title* (e.g. ``v1.2.0``) — the tag itself never changes, so the
    same URL always yields the newest build. Raises on network error or when
    the release/asset is missing.
    """
    rel = fetch_github_release(NRO_RELEASE_TAG, timeout=timeout)
    asset = find_release_asset(rel, NRO_ASSET)
    if not asset or not asset.get("url"):
        raise RuntimeError(
            f"Asset '{NRO_ASSET}' not found in the '{NRO_RELEASE_TAG}' release.")
    version = str(rel.get("name") or "").strip() or rel.get("tag") or "?"
    return {
        "version": version.lstrip("vV") or "?",
        "url": asset["url"],
        "size": int(asset.get("size") or 0),
        "updated_at": asset.get("updated_at"),
    }


def download_switch_app(dest, progress_cb=None, should_stop=None) -> dict:
    """Download the latest Switch homebrew app (.nro) to *dest*.

    Always fetches the CURRENT build (see fetch_switch_app_info). The file is
    validated via the NRO magic ("NRO0" at offset 0x10) so a truncated
    download or an HTML error page is never handed to the user. Returns the
    info dict from fetch_switch_app_info() plus ``path``.
    """
    info = fetch_switch_app_info()
    dest = Path(dest)
    download_file(info["url"], dest, progress_cb=progress_cb,
                  should_stop=should_stop)
    with open(dest, "rb") as f:
        head = f.read(0x14)
    if len(head) < 0x14 or head[0x10:0x14] != b"NRO0":
        try:
            dest.unlink()
        except Exception:
            pass
        raise RuntimeError("Downloaded file is not a valid NRO (bad magic).")
    info["path"] = str(dest)
    return info


def copy_nro_to_sd(nro_path, sd_root) -> str:
    """Place a downloaded .nro onto a Switch SD card as /switch/<NRO_ASSET>.

    ``sd_root`` must look like a Switch SD root (CFW marker folder present) —
    the same validation the cheats SD export uses. Returns the target path.
    """
    root = Path(sd_root)
    if not looks_like_sd_root(root):
        raise RuntimeError(
            f"'{sd_root}' does not look like a Switch SD card root "
            "(no atmosphere/switch/Nintendo folder found).")
    target = root / NRO_SD_DIR / NRO_ASSET
    target.parent.mkdir(parents=True, exist_ok=True)
    # Copy via temp + replace so a yanked card never leaves a truncated app.
    tmp = target.with_suffix(target.suffix + ".part")
    shutil.copyfile(nro_path, tmp)
    tmp.replace(target)
    return str(target)

# Sentinel returned by the browser download path when a build conclusively has
# no downloadable codes on cheatslips (a codeless "names-only" upload, or a
# "no cheat available" page). Such builds are marked in the DB (source column
# prefixed with this value) so future download runs skip them.
BUILD_UNAVAILABLE = "__BUILD_UNAVAILABLE__"
UNAVAILABLE_SOURCE_PREFIX = "unavailable"


def looks_like_closed_browser(exc: Exception) -> bool:
    """True when an exception from the browser-download callback means the
    Playwright page/context/browser was closed (window closed, crash, …).

    The browser code (playwright_scrape) lives in a module that imports THIS
    one, so we cannot import its exception type here without a cycle — we match
    the message instead. Keep the markers in sync with
    playwright_scrape.is_session_closed_error()."""
    s = str(exc).lower()
    return ("has been closed" in s
            or "target page, context or browser" in s
            or "target closed" in s
            or "browser session was closed" in s)


def check_cheatslips_online(timeout: int = 10) -> bool:
    """Return True when cheatslips.com is reachable and serving pages.

    Any HTTP response below 500 counts as online (403/404 still prove the
    server is up); connection errors, timeouts and 5xx count as offline.
    """
    import requests
    try:
        r = requests.get(BASE_URL, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code < 500
    except Exception:
        return False


def normalize_slug(name: str) -> str:
    """Convert a game title to a URL slug matching CheatSlips.com style."""
    result = []
    prev_dash = False
    for ch in name:
        if ch == " ":
            if result and not prev_dash:
                result.append("-")
                prev_dash = True
        elif ch in "®™":
            prev_dash = False
        elif ch.lower() in "éèêë":
            result.append("e")
            prev_dash = False
        elif ch.isalnum() or ch == "-":
            low = ch.lower()
            if low == "-" and (not result or prev_dash):
                continue
            result.append(low)
            prev_dash = low == "-"
    if result and result[-1] == "-":
        result.pop()
    return "".join(result)


# Bevorzugt lxml (schnell); faellt aber automatisch auf Pythons eingebauten
# html.parser zurueck, falls lxml nicht installiert ist – so laeuft das Programm
# auch bei einer frischen Installation ohne Zusatzpaket.
try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except Exception:
    _HTML_PARSER = "html.parser"


def parse_html(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, _HTML_PARSER)


def extract_version(text: str) -> Optional[str]:
    """Pull a semantic version (e.g. 1.4.0) out of a source-card header line."""
    if not text:
        return None
    # Preferred: the version that sits right before the "TID:" marker.
    m = re.search(r"(\d+(?:\.\d+)+)\s*TID:", text)
    if m:
        return m.group(1)
    # Fallback: first version-looking token (optionally prefixed with v).
    m = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", text)
    if m:
        return m.group(1)
    return None


class StateManager:
    """Persistent SQLite-based resume and failure tracking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._ensure_tables()

    def _ensure_tables(self):
        with self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS completed_slugs (
                    slug TEXT PRIMARY KEY
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS completed_sources (
                    slug TEXT,
                    source_id TEXT,
                    build_id TEXT,
                    PRIMARY KEY (slug, source_id)
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS failed_downloads (
                    slug TEXT,
                    source_id TEXT,
                    build_id TEXT,
                    error TEXT,
                    retries INTEGER DEFAULT 0,
                    PRIMARY KEY (slug, source_id)
                )"""
            )

    def is_slug_done(self, slug: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM completed_slugs WHERE slug = ?", (slug,)
        ).fetchone()
        return row is not None

    def is_source_done(self, slug: str, source_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM completed_sources WHERE slug = ? AND source_id = ?",
            (slug, source_id),
        ).fetchone()
        return row is not None

    def mark_slug_done(self, slug: str):
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO completed_slugs (slug) VALUES (?)", (slug,)
            )

    def mark_source_done(self, slug: str, source_id: str, build_id: str = ""):
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO completed_sources (slug, source_id, build_id) VALUES (?, ?, ?)",
                (slug, source_id, build_id),
            )

    def mark_failed(self, slug: str, source_id: str, build_id: str, error: str):
        with self._conn:
            self._conn.execute(
                """INSERT INTO failed_downloads (slug, source_id, build_id, error, retries)
                   VALUES (?, ?, ?, ?, 0)
                   ON CONFLICT(slug, source_id) DO UPDATE SET
                       error = excluded.error,
                       retries = retries + 1""",
                (slug, source_id, build_id, error),
            )

    def clear_failed(self, slug: str, source_id: str):
        with self._conn:
            self._conn.execute(
                "DELETE FROM failed_downloads WHERE slug = ? AND source_id = ?",
                (slug, source_id),
            )

    def get_failed(self) -> List[Tuple[str, str, str, int]]:
        return self._conn.execute(
            "SELECT slug, source_id, build_id, retries FROM failed_downloads"
        ).fetchall()

    def stats(self) -> Dict[str, int]:
        return {
            "completed_slugs": self._conn.execute(
                "SELECT COUNT(*) FROM completed_slugs"
            ).fetchone()[0],
            "completed_sources": self._conn.execute(
                "SELECT COUNT(*) FROM completed_sources"
            ).fetchone()[0],
            "failed_downloads": self._conn.execute(
                "SELECT COUNT(*) FROM failed_downloads"
            ).fetchone()[0],
        }

    def close(self):
        self._conn.close()


CSV_COLUMNS = [
    "game_title", "region", "version", "version_date", "title_id", "build_id",
    "upload_date", "cheat_count", "credits", "description",
    "publisher", "developer", "category", "release_date", "players",
    "size_bytes", "rating", "game_description",
    "slug", "source_id", "cheat_id", "image", "banner", "cheat_names", "source",
]


SCAN_CACHE_NAME = ".scan_cache.json"


def _load_scan_cache(out: Path) -> Dict:
    """Per-file validity cache for scan_downloaded_build_ids.
    Maps relative path -> [mtime, size, is_valid] so unchanged files never
    need to be re-read and re-parsed on later scans."""
    try:
        data = json.loads((out / SCAN_CACHE_NAME).read_text(encoding="utf-8"))
        files = data.get("files", {})
        return files if isinstance(files, dict) else {}
    except Exception:
        return {}


def _save_scan_cache(out: Path, files: Dict) -> None:
    try:
        (out / SCAN_CACHE_NAME).write_text(
            json.dumps({"files": files}), encoding="utf-8")
    except Exception:
        pass  # cache is best-effort only


def scan_downloaded_build_ids(output_dir, modified_since: Optional[float] = None) -> set:
    """Return the set of build IDs that already have a valid .txt file on disk.

    Reconciles against what was actually downloaded (titles/.../cheats/*.txt
    and by_bid/*.txt), so the UI can show what is present vs. missing.
    Files that only contain a quota/placeholder message, are empty, or
    otherwise contain no real cheat codes are ignored.

    A per-file (mtime, size) cache in ``.scan_cache.json`` skips re-reading and
    re-parsing files that have not changed since the previous scan, so repeat
    scans only stat() each file instead of reading it.

    If ``modified_since`` is given, only files whose ``mtime`` is >= this
    timestamp are considered (useful for incremental cache updates after a
    download run).
    """
    out = Path(output_dir)
    found = set()
    if not out.exists():
        return found
    cache = _load_scan_cache(out)
    seen: Dict = {}
    cache_dirty = False
    for sub in ("titles", "by_bid"):
        base = out / sub
        if not base.exists():
            continue
        for txt in base.rglob("*.txt"):
            try:
                st = txt.stat()
            except Exception:
                continue
            if modified_since is not None and st.st_mtime < modified_since:
                continue
            rel = str(txt.relative_to(out))
            entry = cache.get(rel)
            if entry and entry[0] == st.st_mtime and entry[1] == st.st_size:
                valid = bool(entry[2])
            else:
                try:
                    content = txt.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                # Only count a build as downloaded when its file has REAL cheats
                # (code lines) — empty, quota/placeholder and codeless "preview"
                # files do not count, so they stay listed under "not downloaded".
                valid = not cheat_file_is_empty(content)
                cache_dirty = True
            seen[rel] = [st.st_mtime, st.st_size, valid]
            if valid:
                found.add(txt.stem.upper())
    # Persist the pruned cache only on FULL scans: an incremental scan
    # (modified_since) skips most files, so pruning there would drop them.
    if modified_since is None and (cache_dirty or set(seen) != set(cache)):
        _save_scan_cache(out, seen)
    return found


class _Tee:
    """Duplicate writes to several streams (used to mirror stdout into a log).

    None streams are dropped and any per-stream write/flush error is swallowed,
    so logging never crashes the app. This matters in a PyInstaller *windowed*
    build (console=False), where ``sys.stdout``/``sys.__stdout__`` are ``None`` —
    without this guard the first ``print()`` would raise
    ``'NoneType' object has no attribute 'write'``.
    """

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


LOG_MAX_BYTES = 5 * 1024 * 1024   # rotate once the log grows past 5 MB
LOG_KEEP_BYTES = 1 * 1024 * 1024  # ...keeping only the most recent 1 MB


def _rotate_log(path: Path) -> None:
    """Truncate an oversized log file to its most recent LOG_KEEP_BYTES."""
    try:
        if not path.exists() or path.stat().st_size <= LOG_MAX_BYTES:
            return
        data = path.read_bytes()[-LOG_KEEP_BYTES:]
        # Cut at the first newline so the kept part starts with a whole line.
        nl = data.find(b"\n")
        if nl != -1:
            data = data[nl + 1:]
        path.write_bytes(b"===== log truncated (rotation) =====\n" + data)
    except Exception:
        pass  # rotation is best-effort; never block logging


def enable_file_logging(path):
    """Mirror everything printed to stdout into a log file. Returns the file.

    The log is size-capped: past LOG_MAX_BYTES it is truncated down to the most
    recent LOG_KEEP_BYTES on the next start, so it never grows unbounded.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log(path)
    f = open(path, "a", encoding="utf-8")
    f.write(f"\n===== run started {datetime.datetime.now().isoformat(timespec='seconds')} =====\n")
    f.flush()
    original_stdout = sys.__stdout__

    class _TeeWithClose(_Tee):
        def close(self):
            for st in self.streams:
                if hasattr(st, 'close') and st != original_stdout:
                    try:
                        st.close()
                    except Exception:
                        pass

    sys.stdout = _TeeWithClose(original_stdout, f)
    return sys.stdout


def export_rows_csv(rows, dest: Path) -> int:
    """Write database rows (sqlite3.Row or dict-like) to a UTF-8 CSV file."""
    import csv

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel opens special characters correctly.
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in rows:
            writer.writerow([r[col] for col in CSV_COLUMNS])
    return len(rows)


# ---------------------------------------------------------------------------
# Lokale Ergaenzungs-Datenbank: build_id -> (title_id, version, name)
#
# Die exakte Version zu einer Build-ID (plus Spielname) ist ONLINE nicht
# verfuegbar. Diese Daten werden offline aus den installierten Spielen
# extrahiert (main-NSO-Build-ID) und lokal in ``buildid_map.csv`` gepflegt
# (neben cheats.db bzw. neben dem Programm; ";"-getrennt, Spalten
# build_id;title_id;version;name). Liefert eine Cheat-Quelle beim Scrapen/
# Downloaden keine Version/keinen Namen, fuellt diese Map das per Build-ID auf.
# ---------------------------------------------------------------------------
BUILDID_MAP_FILE = "buildid_map.csv"


def load_buildid_map(*dirs) -> Dict[str, Dict[str, str]]:
    """Liest buildid_map.csv aus den gegebenen Verzeichnissen (erste Fundstelle
    pro build_id gewinnt) und liefert {BUILD_ID: {title_id, version, name}}."""
    import csv as _csv
    out: Dict[str, Dict[str, str]] = {}
    for d in dirs:
        if not d:
            continue
        fp = Path(d)
        if fp.is_dir():
            fp = fp / BUILDID_MAP_FILE
        if not fp.exists():
            continue
        try:
            with open(fp, encoding="utf-8-sig", newline="") as f:
                for row in _csv.DictReader(f, delimiter=";"):
                    bid = (row.get("build_id") or "").strip().upper()
                    if len(bid) != 16:
                        continue
                    # source: "extracted" = selbst aus der Datei gelesen
                    # (autoritativ, darf überschreiben) | "db"/sonst = archiviert
                    # (nur Fallback, füllt nur Leeres).
                    src = (row.get("source") or "extracted").strip().lower()
                    out.setdefault(bid, {
                        "title_id": (row.get("title_id") or "").strip().upper(),
                        "version": (row.get("version") or "").strip(),
                        "name": (row.get("name") or "").strip(),
                        "source": src,
                    })
        except Exception as e:
            print(f"buildid_map: Fehler beim Lesen von {fp}: {e}")
    return out


class GameDatabase:
    """Persistent SQLite database of every scraped game/build for lookup.

    Maintained additionally to the JSON exports. Re-running `metadata` upserts
    rows so the database stays current without losing previously known values.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the connection can be read from the
        # download worker threads (api_download_from_db runs a thread pool that
        # calls get_game_info). Writes stay on the main thread.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL lets the GUI read while a worker writes (no "database is locked"),
        # and the busy timeout makes concurrent writers wait instead of failing.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass  # e.g. read-only medium — the DB still works without WAL
        # Optional set of title ids that enrichment may modify. When set (via
        # set_write_restrict), all game-level writes and the "which titles are
        # missing X" queries are limited to these ids — so a context-menu
        # "Get Names/Region/…" on selected rows only touches the selection.
        self._write_restrict = None
        self._ensure_tables()
        # Lokale Versions-Datenbank (build_id -> title_id/version/name): neben
        # cheats.db (Schreibort) und als Fallback neben dem Programm. Wird beim
        # Scrapen/Downloaden gelesen (auffuellen/korrigieren) UND geschrieben
        # (neue externe + manuelle Versionen werden archiviert).
        # Schreibort ist IMMER der beschreibbare Datenordner neben cheats.db.
        self._buildid_map_path = self.db_path.parent / BUILDID_MAP_FILE
        try:
            here = Path(__file__).resolve().parent
            # Lese-Quellen (erste gewinnt): Datenordner, Programmordner und – im
            # gepackten .exe – das eingebettete Bundle (sys._MEIPASS).
            search = [self._buildid_map_path, self.db_path.parent, here]
            bundled = getattr(sys, "_MEIPASS", None)
            if bundled:
                search.append(Path(bundled))
            self._buildid_map = load_buildid_map(*search)
        except Exception:
            self._buildid_map = {}

    # ------------------------------------------------------------- version-DB
    def _write_buildid_map(self) -> None:
        """Schreibt die lokale Versions-DB (self._buildid_map) nach
        buildid_map.csv (build_id;title_id;version;name;source)."""
        import csv as _csv
        try:
            with open(self._buildid_map_path, "w", newline="", encoding="utf-8-sig") as f:
                w = _csv.writer(f, delimiter=";")
                w.writerow(["build_id", "title_id", "version", "name", "source"])
                for bid, rec in sorted(self._buildid_map.items(),
                                       key=lambda kv: (kv[1].get("name") or "").lower()):
                    w.writerow([bid, rec.get("title_id", ""), rec.get("version", ""),
                                rec.get("name", ""), rec.get("source", "extracted")])
        except Exception as e:
            print(f"buildid_map schreiben fehlgeschlagen: {e}")

    def record_buildid(self, build_id, title_id, version=None, name=None,
                       source="manual", write=True) -> bool:
        """Traegt einen build_id->title_id/version/name-Eintrag in die lokale
        Versions-DB ein bzw. aktualisiert ihn.

        - source='manual'/'extracted' = autoritativ (z.B. GUI-Eingabe): setzt
          Version/Name immer.
        - source='db' (aus externer Quelle archiviert): ergaenzt NUR, wenn noch
          kein (autoritativer) Eintrag existiert - unsere DB gewinnt.
        write=False sammelt nur im RAM (fuer Massen-Import); dann einmal
        _write_buildid_map() aufrufen.
        """
        bid = (build_id or "").strip().upper()
        if len(bid) != 16:
            return False
        tid = (title_id or "").strip().upper()
        ver = (version or "").strip()
        nm = (name or "").strip()
        cur = self._buildid_map.get(bid)
        authoritative = source in ("manual", "extracted")
        if cur:
            if not authoritative:
                # Unsere DB gewinnt: bestehenden Eintrag NICHT durch externen
                # ueberschreiben. Nur fehlende Felder auffuellen.
                if cur.get("source") in ("manual", "extracted"):
                    return False
                if cur.get("version") and not (ver and not cur.get("version")):
                    # hat schon eine Version -> nichts tun
                    if not (nm and not cur.get("name")):
                        return False
            merged = {
                "title_id": tid or cur.get("title_id", ""),
                "version": ver or cur.get("version", ""),
                "name": nm or cur.get("name", ""),
                "source": source if authoritative else cur.get("source", source),
            }
        else:
            if not ver:
                return False  # ohne Version keine sinnvolle Zuordnung
            merged = {"title_id": tid, "version": ver, "name": nm, "source": source}
        if merged == cur:
            return False
        self._buildid_map[bid] = merged
        if write:
            self._write_buildid_map()
        return True

    def set_write_restrict(self, title_ids) -> None:
        """Limit subsequent enrichment writes/queries to these title ids
        (uppercased). Pass None/empty to clear (process the whole database)."""
        self._write_restrict = ({t.upper() for t in title_ids}
                                if title_ids else None)

    def _restricted(self, title_id) -> bool:
        """True if a write to this title id is currently blocked by the restrict."""
        return (self._write_restrict is not None
                and (title_id or "").upper() not in self._write_restrict)

    def _apply_restrict(self, tids):
        """Filter an iterable of title ids by the active write-restrict."""
        if self._write_restrict is None:
            return list(tids)
        return [t for t in tids if (t or "").upper() in self._write_restrict]

    # All columns; extra ones beyond the originals are added via migration.
    COLUMNS = [
        "build_id", "title_id", "slug", "game_title", "version", "source_id",
        "upload_date", "cheat_count", "cheat_names", "last_updated",
        # Wann zuletzt NEUE Cheats in UNSERE DB kamen (Insert bzw. echte
        # Aenderung der Cheat-Liste). Re-Scrapes ohne Aenderung ruehren den
        # Wert NICHT an — im Gegensatz zu last_updated (= Scrape-Zeit, wird
        # jedes Mal ueberschrieben). Basis der "Zuletzt aktualisiert"-Anzeige.
        "cheats_added_at",
        # API-provided fields:
        "credits", "description", "image", "banner", "cheat_id",
        # origin of the entry: "cheatslips" or "gbatemp"
        "source",
    ]

    def _ensure_tables(self):
        with self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS builds (
                    build_id TEXT,
                    title_id TEXT,
                    slug TEXT,
                    game_title TEXT,
                    version TEXT,
                    source_id TEXT,
                    upload_date TEXT,
                    cheat_count INTEGER,
                    cheat_names TEXT,
                    last_updated TEXT,
                    credits TEXT,
                    description TEXT,
                    image TEXT,
                    banner TEXT,
                    cheat_id INTEGER,
                    source TEXT,
                    PRIMARY KEY (build_id, title_id)
                )"""
            )
            # Migrate older databases: add any missing columns.
            existing = {r[1] for r in self._conn.execute("PRAGMA table_info(builds)")}
            extra_cols = (
                "credits", "description", "image", "banner", "cheat_id", "source",
                # NutDB/titledb extras:
                "publisher", "developer", "category", "game_description",
                "release_date", "players", "size_bytes", "rating", "version_date",
                # Extended titledb metadata:
                "screenshots", "languages", "nsu_id", "intro", "rating_content", "is_demo",
                "region",
            )
            for col in extra_cols:
                if col not in existing:
                    self._conn.execute(f"ALTER TABLE builds ADD COLUMN {col} TEXT")
            # "Zuletzt aktualisiert"-Zeitstempel (2026-07-18): wann kamen
            # zuletzt NEUE Cheats in DIESE DB. Einmaliger Backfill beim
            # Anlegen der Spalte: bestehende Zeilen bekommen das QUELL-
            # Upload-Datum als ISO — die lokale Scrape-Zeit (last_updated)
            # waere falsch, sie wird bei jedem Re-Scrape ueberschrieben.
            # Zeilen ohne upload_date bleiben ehrlich NULL (Hinzufuege-Zeit
            # unbekannt) und erscheinen nicht als "neu".
            if "cheats_added_at" not in existing:
                self._conn.execute(
                    "ALTER TABLE builds ADD COLUMN cheats_added_at TEXT")
                import datetime as _dt
                upd = []
                for rid, up in self._conn.execute(
                        "SELECT rowid, upload_date FROM builds "
                        "WHERE upload_date IS NOT NULL AND upload_date <> ''"):
                    for f in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
                        try:
                            upd.append((_dt.datetime.strptime(up.strip(), f)
                                        .strftime("%Y-%m-%dT00:00:00"), rid))
                            break
                        except ValueError:
                            pass
                self._conn.executemany(
                    "UPDATE builds SET cheats_added_at = ? WHERE rowid = ?", upd)
            # The PK is (build_id, title_id), so plain "WHERE title_id = ?"
            # lookups (get_game_info, update_game_fields — called thousands of
            # times during enrichment) would full-scan without this index.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_builds_title ON builds(title_id)")

    # Game-level columns that may be filled from titledb (whitelist for updates).
    _GAME_FIELDS = {
        "game_title", "slug", "image", "banner", "publisher", "developer",
        "category", "game_description", "release_date", "players", "size_bytes",
        "rating", "region",
        # Extended titledb metadata:
        "screenshots", "languages", "nsu_id", "intro", "rating_content", "is_demo",
    }

    def update_game_fields(self, title_id: str, fields: Dict) -> int:
        """COALESCE-update game-level fields for all rows of a title id.

        game_title is overwritten when it is empty OR when it currently equals the
        raw title_id (so that placeholder ids never block a real name update).
        """
        if self._restricted(title_id):
            return 0
        cols = [c for c in fields if c in self._GAME_FIELDS and fields[c] not in (None, "")]
        if not cols:
            return 0
        sets = []
        params = []
        for c in cols:
            if c == "game_title":
                # Keep the existing name (with its original casing) unless it is
                # empty or just the raw title id; only then use the new value.
                sets.append(
                    f"{c} = CASE WHEN {c} IS NULL OR {c} = '' "
                    f"OR UPPER({c}) = UPPER(title_id) THEN ? ELSE {c} END")
            else:
                sets.append(f"{c} = COALESCE({c}, ?)")
            params.append(fields[c])
        params.append(title_id)
        with self._conn:
            cur = self._conn.execute(
                f"UPDATE builds SET {', '.join(sets)} WHERE title_id = ?", params)
            return cur.rowcount

    def set_build_version(self, title_id: str, build_id: str,
                         version: str = None, version_date: str = None) -> int:
        """Fill version and/or version_date for a build (keeps existing values)."""
        if self._restricted(title_id):
            return 0
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET version = COALESCE(version, ?), "
                "version_date = COALESCE(version_date, ?) "
                "WHERE title_id = ? AND build_id = ?",
                (version, version_date, title_id, build_id),
            )
            return cur.rowcount

    def set_build_cheats(self, title_id: str, build_id: str,
                         count: int, names: List[str]) -> int:
        """Overwrite cheat_count + cheat_names for a build (e.g. recounted from disk)."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET cheat_count = ?, cheat_names = ? "
                "WHERE title_id = ? AND build_id = ?",
                (count, json.dumps(names, ensure_ascii=False), title_id, build_id),
            )
            return cur.rowcount

    def set_build_source(self, title_id: str, build_id: str, source: str) -> int:
        """Set the origin (cheatslips/gbatemp/titledb/disk) of a build's cheat codes."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET source = ? WHERE title_id = ? AND build_id = ?",
                (source, title_id, build_id),
            )
            return cur.rowcount

    def mark_build_unavailable(self, title_id: str, build_id: str,
                               reason: str = "codeless") -> int:
        """Flag a build as having no downloadable codes on cheatslips so future
        download runs skip it (see builds_for_download). ``reason`` is stored for
        reference, e.g. 'codeless' (names-only upload) or 'missing' (not on site).
        """
        value = f"{UNAVAILABLE_SOURCE_PREFIX}:{reason}"
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET source = ? WHERE title_id = ? AND build_id = ?",
                (value, title_id, build_id),
            )
            return cur.rowcount

    def clear_unavailable(self) -> int:
        """Clear every 'unavailable' mark so those builds are retried again.
        Returns the number of builds reset."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET source = NULL "
                "WHERE source LIKE ? || '%'", (UNAVAILABLE_SOURCE_PREFIX,),
            )
            return cur.rowcount

    def count_unavailable(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM builds WHERE source LIKE ? || '%'",
            (UNAVAILABLE_SOURCE_PREFIX,),
        ).fetchone()
        return row[0] if row else 0

    def upsert_build(self, row: Dict):
        # Fill any missing keys with None so the named query always binds.
        full = {c: row.get(c) for c in self.COLUMNS}
        # Neu-/Aenderungs-Stempel: greift beim INSERT direkt, beim UPDATE nur,
        # wenn die Cheat-Liste sich wirklich geaendert hat (CASE oben).
        if not full.get("cheats_added_at"):
            full["cheats_added_at"] = full.get("last_updated")
        # Ungueltige/Platzhalter-Build-IDs (all-zeros/-ones/-F, title==build) sind
        # Fehl-Uploads (nicht ladbar) und wuerden sonst bei jedem Scrape wieder als
        # nicht-downloadbare Zeile auftauchen -> gar nicht erst speichern.
        if (is_blocked_pair(full.get("title_id"), full.get("build_id"))
                or is_placeholder_build_id(full.get("build_id"), full.get("title_id"))):
            return
        # Respect an active enrichment restrict (e.g. API refresh of selected rows).
        if self._restricted(full.get("title_id")):
            return
        # Never store the raw title_id as the game_title placeholder.
        if full.get("game_title") and full.get("title_id"):
            if full["game_title"].upper() == full["title_id"].upper():
                full["game_title"] = None
        override = TITLE_NAME_OVERRIDES.get((full.get("title_id") or "").upper())
        if override:
            full["game_title"] = override
        # Lokale Ergaenzungs-DB: fehlende Version/Name per build_id auffuellen -
        # greift genau dann, wenn die Cheat-Quelle diese Daten nicht liefert.
        # Nur wenn die Title-ID der Map zur eingefuegten Title-ID passt (dieselbe
        # Build-ID darf nicht einen fremden Titel mit-befuellen).
        supp = self._buildid_map.get((full.get("build_id") or "").upper())
        if supp and supp.get("title_id") == (full.get("title_id") or "").upper():
            auth = supp.get("source", "extracted") in ("extracted", "manual")
            # Autoritative (eigene) Version gewinnt und ueberschreibt die der
            # Quelle; sonst (archiviert) nur fehlende Version auffuellen.
            if supp.get("version") and (auth or not full.get("version")):
                full["version"] = supp["version"]
            if not full.get("game_title") and supp.get("name"):
                full["game_title"] = supp["name"]
        with self._conn:
            self._conn.execute(
                """INSERT INTO builds
                    (build_id, title_id, slug, game_title, version, source_id,
                     upload_date, cheat_count, cheat_names, last_updated,
                     cheats_added_at,
                     credits, description, image, banner, cheat_id, source)
                   VALUES
                    (:build_id, :title_id, :slug, :game_title, :version, :source_id,
                     :upload_date, :cheat_count, :cheat_names, :last_updated,
                     :cheats_added_at,
                     :credits, :description, :image, :banner, :cheat_id, :source)
                   ON CONFLICT(build_id, title_id) DO UPDATE SET
                       slug = COALESCE(excluded.slug, builds.slug),
                       game_title = COALESCE(excluded.game_title, builds.game_title),
                       version = COALESCE(excluded.version, builds.version),
                       source_id = COALESCE(excluded.source_id, builds.source_id),
                       upload_date = COALESCE(excluded.upload_date, builds.upload_date),
                       -- A re-scrape that yields 0/NULL cheats (cheatslips
                       -- sometimes reports an empty build even though codes
                       -- exist) must never wipe a real count we already have.
                       cheat_count = CASE
                           WHEN excluded.cheat_count IS NULL OR excluded.cheat_count = 0
                           THEN builds.cheat_count
                           ELSE excluded.cheat_count END,
                       cheat_names = CASE
                           WHEN excluded.cheat_count IS NULL OR excluded.cheat_count = 0
                           THEN builds.cheat_names
                           ELSE excluded.cheat_names END,
                       last_updated = excluded.last_updated,
                       -- Nur bei ECHTER Aenderung der Cheat-Liste neu stempeln
                       -- (und nie beim 0/NULL-Wipe-Fall): Re-Scrapes ohne neue
                       -- Cheats lassen "cheats_added_at" unberuehrt.
                       cheats_added_at = CASE
                           WHEN excluded.cheat_count IS NULL OR excluded.cheat_count = 0
                               THEN builds.cheats_added_at
                           WHEN builds.cheat_names IS NOT NULL
                                AND excluded.cheat_names = builds.cheat_names
                               THEN builds.cheats_added_at
                           ELSE COALESCE(excluded.cheats_added_at,
                                         builds.cheats_added_at) END,
                       credits = COALESCE(excluded.credits, builds.credits),
                       description = COALESCE(excluded.description, builds.description),
                       image = COALESCE(excluded.image, builds.image),
                       banner = COALESCE(excluded.banner, builds.banner),
                       cheat_id = COALESCE(excluded.cheat_id, builds.cheat_id),
                       source = COALESCE(excluded.source, builds.source)""",
                full,
            )

    def upsert_game(self, info: Dict, source: Optional[str] = None):
        """Store every source of a scraped game-details dict."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for src in info.get("sources", []):
            bid = src.get("build_id")
            if not bid:
                continue
            names = src.get("cheat_names") or []
            self.upsert_build({
                "build_id": bid,
                "title_id": src.get("title_id") or info.get("title_id") or "",
                "slug": info.get("slug"),
                "game_title": info.get("title"),
                "version": src.get("version"),
                "source_id": src.get("source_id"),
                "upload_date": src.get("upload_date"),
                "cheat_count": src.get("cheat_count", len(names)),
                "cheat_names": json.dumps(names, ensure_ascii=False),
                "last_updated": now,
                "credits": src.get("credits"),
                "description": src.get("description"),
                "image": info.get("image"),
                "banner": info.get("banner"),
                "cheat_id": src.get("cheat_id"),
                "source": src.get("source") or source,
            })

    def get_game_info(self, title_id: str) -> Optional[Dict]:
        """Reconstruct an info dict (with all builds) for a title id from the DB."""
        rows = self._conn.execute(
            "SELECT * FROM builds WHERE title_id = ?", (title_id,)
        ).fetchall()
        if not rows:
            return None
        sources = []
        title = slug = image = banner = None
        for r in rows:
            title = title or r["game_title"]
            slug = slug or r["slug"]
            image = image or r["image"]
            banner = banner or r["banner"]
            try:
                names = json.loads(r["cheat_names"] or "[]")
            except Exception:
                names = []
            sources.append({
                "build_id": r["build_id"], "title_id": r["title_id"],
                "source_id": r["source_id"], "version": r["version"],
                "upload_date": r["upload_date"], "cheat_count": r["cheat_count"],
                "cheat_names": names, "credits": r["credits"],
                "description": r["description"], "cheat_id": r["cheat_id"],
            })
        return {"title_id": title_id, "title": title, "slug": slug,
                "image": image, "banner": banner, "sources": sources}

    def search(
        self,
        term: Optional[str] = None,
        build_id: Optional[str] = None,
        title_id: Optional[str] = None,
        in_cheats: bool = False,
    ) -> List[sqlite3.Row]:
        query = (
            "SELECT game_title, version, title_id, build_id, upload_date, "
            "cheat_count, slug, source_id, cheat_names, credits, description, "
            "image, banner, cheat_id, source, publisher, developer, category, "
            "game_description, release_date, players, size_bytes, rating, version_date, "
            "screenshots, languages, nsu_id, intro, rating_content, is_demo, region "
            "FROM builds"
        )
        clauses, params = [], []
        # Hide placeholder builds where the build id equals the title id.
        clauses.append("UPPER(build_id) <> UPPER(title_id)")
        for btid, bbid in BLOCKED_BUILD_PAIRS:
            clauses.append("NOT (title_id = ? AND build_id = ?)")
            params.extend([btid, bbid])
        if build_id:
            clauses.append("build_id LIKE ?")
            params.append(f"%{build_id.upper()}%")
        if title_id:
            clauses.append("title_id LIKE ?")
            params.append(f"%{title_id.upper()}%")
        if term:
            # Match the free-text term against the game name AND both ids, so
            # typing a title id or build id into the search box works too.
            # With in_cheats=True the term ALSO matches the cheat names (the
            # cheat_names column is a JSON list stored as text), so searching
            # "inf health" finds every game that has such a cheat.
            like = "(game_title LIKE ? OR UPPER(title_id) LIKE ? OR UPPER(build_id) LIKE ?"
            params.append(f"%{term}%")
            params.append(f"%{term.upper()}%")
            params.append(f"%{term.upper()}%")
            if in_cheats:
                like += " OR cheat_names LIKE ? COLLATE NOCASE"
                params.append(f"%{term}%")
            clauses.append(like + ")")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY game_title COLLATE NOCASE, version"
        return self._conn.execute(query, params).fetchall()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]

    def count_games(self) -> int:
        """Return the number of distinct base games in the database.

        A base game is identified by zeroing the last three hex digits of the
        title id, which groups updates and DLCs with their parent application.
        """
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT substr(title_id, 1, 13) || '000') "
            "FROM builds WHERE title_id IS NOT NULL AND length(title_id) = 16"
        ).fetchone()
        return row[0] if row else 0

    def purge_invalid(self) -> int:
        """Delete rows whose title_id is not a valid 16-char id (e.g. old 'NONE'),
        plus any row matching the permanent build-pair blocklist."""
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM builds WHERE title_id IS NULL OR length(title_id) <> 16"
            )
            removed = cur.rowcount
            # Placeholder builds where the build id equals the title id.
            cur3 = self._conn.execute(
                "DELETE FROM builds WHERE UPPER(build_id) = UPPER(title_id)"
            )
            removed += cur3.rowcount
            # Platzhalter-Build-IDs (all-zeros/-ones/-F etc.) = Fehl-Uploads.
            if _PLACEHOLDER_BUILD_IDS:
                ph = list(_PLACEHOLDER_BUILD_IDS)
                cur4 = self._conn.execute(
                    "DELETE FROM builds WHERE UPPER(build_id) IN (%s)"
                    % ",".join("?" * len(ph)),
                    [p.upper() for p in ph],
                )
                removed += cur4.rowcount
            for btid, bbid in BLOCKED_BUILD_PAIRS:
                cur2 = self._conn.execute(
                    "DELETE FROM builds WHERE title_id = ? AND build_id = ?", (btid, bbid)
                )
                removed += cur2.rowcount
            return removed

    def clear(self) -> int:
        """Delete all rows. Returns how many were removed."""
        with self._conn:
            cur = self._conn.execute("DELETE FROM builds")
            return cur.rowcount

    def delete_build(self, build_id: str, title_id: str) -> int:
        """Delete a single (build_id, title_id) entry."""
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM builds WHERE build_id = ? AND title_id = ?",
                (build_id, title_id),
            )
            return cur.rowcount

    def update_build_ids(self, old_build_id: str, old_title_id: str,
                         new_build_id: str, new_title_id: str) -> bool:
        """Change the build id / title id of an entry. Returns False on conflict."""
        with self._conn:
            exists = self._conn.execute(
                "SELECT 1 FROM builds WHERE build_id = ? AND title_id = ?",
                (new_build_id, new_title_id),
            ).fetchone()
            if exists and (new_build_id, new_title_id) != (old_build_id, old_title_id):
                return False
            self._conn.execute(
                "UPDATE builds SET build_id = ?, title_id = ? "
                "WHERE build_id = ? AND title_id = ?",
                (new_build_id, new_title_id, old_build_id, old_title_id),
            )
            return True

    def title_ids_missing_version(self) -> List[str]:
        """Title ids that have at least one build without a game version."""
        rows = self._conn.execute(
            "SELECT DISTINCT title_id FROM builds "
            "WHERE (version IS NULL OR version = '') "
            "AND title_id IS NOT NULL AND length(title_id) = 16"
        ).fetchall()
        return self._apply_restrict([r[0] for r in rows])

    def builds_missing_version(self) -> List[Tuple[str, str]]:
        """(title_id, build_id) pairs that have no game version yet."""
        rows = self._conn.execute(
            "SELECT title_id, build_id FROM builds "
            "WHERE (version IS NULL OR version = '') "
            "AND title_id IS NOT NULL AND build_id IS NOT NULL"
        ).fetchall()
        if self._write_restrict is not None:
            return [(r[0], r[1]) for r in rows
                    if (r[0] or "").upper() in self._write_restrict]
        return [(r[0], r[1]) for r in rows]

    def title_id_for_build(self, build_id: str) -> Optional[str]:
        """Return a 16-char title id that owns this build id, or None."""
        row = self._conn.execute(
            "SELECT title_id FROM builds "
            "WHERE UPPER(build_id) = ? AND length(title_id) = 16 LIMIT 1",
            ((build_id or "").upper(),)).fetchone()
        return row[0] if row else None

    def set_version(self, title_id: str, build_id: str, version: str) -> int:
        """Set the version of a build (only if it is currently empty)."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET version = ? "
                "WHERE title_id = ? AND build_id = ? AND (version IS NULL OR version = '')",
                (version, title_id, build_id),
            )
            return cur.rowcount

    def title_ids_missing_meta(self) -> List[str]:
        """Title ids that are missing a real game name or a cover image.

        A game_title that is just the raw title_id counts as missing too.
        """
        rows = self._conn.execute(
            "SELECT DISTINCT title_id FROM builds "
            "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id) "
            "     OR image IS NULL OR image = '') "
            "AND title_id IS NOT NULL AND length(title_id) = 16"
        ).fetchall()
        return self._apply_restrict([r[0] for r in rows])

    def fill_game_meta(self, title_id: str, name: str = None, image: str = None,
                       banner: str = None) -> int:
        """Fill name/cover/banner for all rows of a title id (keeps existing)."""
        if self._restricted(title_id):
            return 0
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET "
                "game_title = COALESCE(game_title, ?), "
                "image = COALESCE(image, ?), "
                "banner = COALESCE(banner, ?) "
                "WHERE title_id = ?",
                (name, image, banner, title_id),
            )
            return cur.rowcount

    def set_game_meta(self, title_id: str, slug: str = None, game_title: str = None) -> int:
        """Fill slug/title for all rows of a title id (keeps existing values)."""
        with self._conn:
            cur = self._conn.execute(
                "UPDATE builds SET "
                "slug = COALESCE(slug, ?), game_title = COALESCE(game_title, ?) "
                "WHERE title_id = ?",
                (slug, game_title, title_id),
            )
            return cur.rowcount

    def zero_cheat_title_ids(self) -> List[str]:
        """Title ids that have at least one build with 0 (or unknown) cheats."""
        rows = self._conn.execute(
            "SELECT DISTINCT title_id FROM builds "
            "WHERE (cheat_count IS NULL OR cheat_count = 0) "
            "AND title_id IS NOT NULL AND length(title_id) = 16"
        ).fetchall()
        return [r[0] for r in rows]

    def all_slugs(self) -> List[str]:
        """Distinct game slugs already in the database (games with cheats)."""
        rows = self._conn.execute(
            "SELECT DISTINCT slug FROM builds WHERE slug IS NOT NULL "
            "ORDER BY slug COLLATE NOCASE"
        ).fetchall()
        return [r[0] for r in rows]

    def all_title_ids(self) -> List[str]:
        """Distinct valid title ids in the database (for API downloads)."""
        rows = self._conn.execute(
            "SELECT DISTINCT title_id FROM builds "
            "WHERE title_id IS NOT NULL AND length(title_id) = 16 "
            "ORDER BY title_id"
        ).fetchall()
        return [r[0] for r in rows]

    def all_build_ids(self) -> set:
        """Every (title_id, build_id) pair currently stored (for change detection)."""
        rows = self._conn.execute(
            "SELECT title_id, build_id FROM builds WHERE build_id IS NOT NULL"
        ).fetchall()
        return {(r[0], r[1]) for r in rows}

    def builds_for_download(self) -> List[Tuple[str, str, str, str]]:
        """Every downloadable build as (title_id, build_id, slug, source_id).

        Used by the auto-reset download loop, which needs the slug/source_id to
        fall back to a direct browser download when the API stays rate-limited.
        """
        rows = self._conn.execute(
            "SELECT title_id, build_id, slug, source_id FROM builds "
            "WHERE build_id IS NOT NULL AND build_id != '' "
            "AND title_id IS NOT NULL AND length(title_id) = 16 "
            # Skip builds previously confirmed to have no codes on cheatslips.
            "AND (source IS NULL OR source NOT LIKE '" + UNAVAILABLE_SOURCE_PREFIX + "%')"
        ).fetchall()
        return [(r[0], r[1], r[2] or "", r[3] or "") for r in rows]

    def close(self):
        self._conn.close()


class CheatslipsMetadataScraper:
    """Scrapes game/build metadata without needing a login."""

    def __init__(self, base_url: str = BASE_URL, delay: float = 0.3, retries: int = 5,
                 max_concurrent: int = 4):
        self.base_url = base_url
        self.delay = delay
        self.retries = retries
        # Global cap on simultaneous requests across ALL worker threads, so the
        # server is not flooded (avoids 503 "Service Unavailable" throttling).
        self._sem = threading.Semaphore(max(1, max_concurrent))
        # When the server throttles us (503/429), pause all requests a bit.
        self._throttle_until = 0.0
        self._throttle_lock = threading.Lock()
        self.session = self._create_session(retries)

    @staticmethod
    def _create_session(retries: int = 5) -> "requests.Session":
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        })

        retry_kwargs = dict(
            total=retries,
            backoff_factor=2,  # 2s, 4s, 8s, ... between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )
        # backoff_jitter (urllib3 >= 2) spreads retries so threads don't sync up.
        try:
            retry_strategy = Retry(backoff_jitter=1.0, **retry_kwargs)
        except TypeError:
            retry_strategy = Retry(**retry_kwargs)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get(self, path: str, session: Optional["requests.Session"] = None) -> str:
        url = urljoin(self.base_url, path)
        sess = session or self.session
        # Respect a global cool-down if the server recently throttled us.
        wait = self._throttle_until - time.time()
        if wait > 0:
            time.sleep(min(wait, 30))
        with self._sem:
            try:
                resp = sess.get(url, timeout=30)
                resp.raise_for_status()
            except Exception:
                # Back off globally for a few seconds on any failure (likely 503).
                with self._throttle_lock:
                    self._throttle_until = time.time() + 5
                raise
            time.sleep(self.delay)
            return resp.text

    def _last_page_number(self, text: str) -> int:
        soup = parse_html(text)
        page_links = []
        for a in soup.select("ul.pagination a.page-link"):
            href = a.get("href", "")
            # /games?page=N
            m = re.search(r"[?&]page=(\d+)", href)
            if m:
                page_links.append(int(m.group(1)))
                continue
            # /entry/N
            m = re.match(r"/entry/(\d+)", href)
            if m:
                page_links.append(int(m.group(1)))
        if page_links:
            return max(page_links)
        return 1

    def _game_cards_from_page(self, text: str) -> List[Tuple[str, str]]:
        soup = parse_html(text)
        games = []
        for card in soup.select("div.card-columns a[href^='/game/']"):
            href = card.get("href", "")
            slug = href.replace("/game/", "").strip("/")
            title = card.get_text(strip=True)
            if slug and title:
                games.append((slug, title))
        return games

    def list_all_games(self, max_pages: Optional[int] = None, workers: int = 8,
                        progress_cb=None) -> List[Tuple[str, str]]:
        """List every game. `progress_cb(done, total)` is called as pages finish."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        first_page = self._get("/games")
        total_pages = self._last_page_number(first_page)
        if max_pages:
            total_pages = min(total_pages, max_pages)

        all_games = self._game_cards_from_page(first_page)
        print(f"Found {total_pages} game list pages")

        if total_pages <= 1:
            seen = set()
            unique = []
            for slug, title in all_games:
                if slug not in seen:
                    seen.add(slug)
                    unique.append((slug, title))
            return unique

        pages = list(range(2, total_pages + 1))
        results: Dict[int, List[Tuple[str, str]]] = {1: all_games}
        done = 0

        def report():
            if progress_cb:
                try:
                    progress_cb(done, len(pages))
                except Exception:
                    pass

        if workers > 1 and len(pages) > 1:
            print(f"  scanning {len(pages)} pages with {workers} parallel workers")
            with ThreadPoolExecutor(max_workers=workers) as executor:
                def fetch_page(page: int) -> Tuple[int, List[Tuple[str, str]]]:
                    session = self._create_session(self.retries)
                    try:
                        text = self._get(f"/games?page={page}", session=session)
                        return page, self._game_cards_from_page(text)
                    finally:
                        session.close()

                future_to_page = {executor.submit(fetch_page, page): page for page in pages}
                iterator = as_completed(future_to_page)
                if progress_cb is None:
                    iterator = tqdm(iterator, total=len(pages), desc="Game pages", unit="page")
                for future in iterator:
                    try:
                        page, games = future.result()
                        results[page] = games
                    except Exception as exc:
                        print(f"  ERROR page {future_to_page[future]}: {exc}")
                        results[future_to_page[future]] = []
                    done += 1
                    report()
        else:
            for page in pages:
                print(f"  listing page {page}/{total_pages}")
                text = self._get(f"/games?page={page}")
                results[page] = self._game_cards_from_page(text)
                done += 1
                report()

        all_games = []
        for page in sorted(results.keys()):
            all_games.extend(results[page])

        # de-duplicate while preserving order
        seen = set()
        unique = []
        for slug, title in all_games:
            if slug not in seen:
                seen.add(slug)
                unique.append((slug, title))
        return unique

    def entry_page_slugs(self, page: int) -> List[str]:
        """Return game slugs from the latest-cheat-codes entry page."""
        # Each call uses a fresh session to allow parallel scraping safely.
        session = self._create_session(self.retries)
        try:
            text = self._get(f"/entry/{page}", session=session)
            soup = parse_html(text)
            slugs = []
            for a in soup.find_all("a", href=re.compile(r"^/game/")):
                href = a.get("href", "")
                m = re.match(r"/game/([^/]+)", href)
                if m and m.group(1) not in slugs:
                    slugs.append(m.group(1))
            return slugs
        finally:
            session.close()

    def all_entry_slugs(self, max_pages: Optional[int] = None, workers: int = 4,
                        progress_cb=None, should_stop=None) -> List[str]:
        """Iterate entry pages and collect all game slugs with cheat codes.

        If `should_stop()` becomes true mid-scan, returns the slugs collected so
        far (partial result) instead of aborting empty-handed.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        text = self._get("/entry/1")
        total_pages = self._last_page_number(text) or 1
        pages = list(range(1, total_pages + 1))
        if max_pages is not None:
            pages = list(range(1, min(max_pages, total_pages) + 1))

        results: Dict[int, List[str]] = {}
        print(f"  scanning {len(pages)} entry pages with {workers} parallel workers")
        done = 0
        executor = ThreadPoolExecutor(max_workers=workers)
        future_to_page = {executor.submit(self.entry_page_slugs, page): page for page in pages}
        try:
            iterator = as_completed(future_to_page)
            if progress_cb is None:
                iterator = tqdm(iterator, total=len(pages), desc="Entry pages", unit="page")
            for future in iterator:
                if should_stop and should_stop():
                    print("  stop requested - using entry pages collected so far")
                    break
                page = future_to_page[future]
                try:
                    results[page] = future.result()
                except Exception as exc:
                    print(f"  ERROR entry page {page}: {exc}")
                    results[page] = []
                done += 1
                if progress_cb:
                    try:
                        progress_cb(done, len(pages))
                    except Exception:
                        pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # Preserve order and de-duplicate
        all_slugs: List[str] = []
        for page in pages:
            for slug in results.get(page, []):
                if slug not in all_slugs:
                    all_slugs.append(slug)
        return all_slugs

    def _entry_slugs_from_text(self, text: str) -> List[str]:
        soup = parse_html(text)
        slugs = []
        for a in soup.find_all("a", href=re.compile(r"^/game/")):
            m = re.match(r"/game/([^/]+)", a.get("href", ""))
            if m and m.group(1) not in slugs:
                slugs.append(m.group(1))
        return slugs

    def scrape_all_streaming(
        self,
        on_game,
        entry_only: bool = True,
        max_pages: Optional[int] = None,
        list_workers: int = 3,
        detail_workers: int = 4,
        page_cb=None,
        game_cb=None,
        should_stop=None,
        skip_slugs=None,
    ):
        """Scrape game details while the page listing is still running.

        Detail scraping begins as soon as the first listing page arrives, so
        there is no long idle wait before work starts. `on_game(info)` is called
        (in this thread) for every game that has cheat sources.
        `page_cb(done, total)` reports listing progress, `game_cb(done, total)`
        reports detail progress. `should_stop()` can abort early.
        """
        import queue as _queue
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if entry_only:
            first = self._get("/entry/1")
            total_pages = self._last_page_number(first) or 1
            first_games = [(s, s) for s in self._entry_slugs_from_text(first)]

            def fetch_page(p):
                return [(s, s) for s in self.entry_page_slugs(p)]
        else:
            first = self._get("/games")
            total_pages = self._last_page_number(first)
            first_games = self._game_cards_from_page(first)

            def fetch_page(p):
                session = self._create_session(self.retries)
                try:
                    return self._game_cards_from_page(self._get(f"/games?page={p}", session=session))
                finally:
                    session.close()

        if max_pages:
            total_pages = min(total_pages, max_pages)
        pages = list(range(2, total_pages + 1))
        print(f"Scanning {total_pages} {'entry' if entry_only else 'game'} pages; "
              f"detail scraping starts immediately.")

        seen = set(skip_slugs) if skip_slugs else set()  # pre-seed to skip known games
        skipped_known = len(seen)
        results_q: "_queue.Queue" = _queue.Queue()
        counters = {"submitted": 0, "done": 0}
        detail_pool = ThreadPoolExecutor(max_workers=detail_workers)
        if skipped_known:
            print(f"Incremental: skipping {skipped_known} games already in the database.")

        def submit(games):
            for slug, title in games:
                if slug in seen:
                    continue
                seen.add(slug)
                counters["submitted"] += 1
                fut = detail_pool.submit(self.scrape_game_details, slug)
                fut.add_done_callback(lambda f, s=slug, t=title: results_q.put((s, t, f)))

        failed = []  # (slug, title) of games whose detail fetch errored

        def process_one(item):
            slug, title, fut = item
            try:
                info = fut.result()
                if info:
                    info["title"] = info.get("title") or title
                    on_game(info)
            except Exception as exc:
                print(f"  ERROR {slug}: {exc}")
                failed.append((slug, title))
            counters["done"] += 1
            if game_cb:
                game_cb(counters["done"], counters["submitted"])

        def drain_available():
            while True:
                try:
                    item = results_q.get_nowait()
                except _queue.Empty:
                    break
                process_one(item)

        try:
            submit(first_games)
            pages_done = 1
            if page_cb:
                page_cb(pages_done, total_pages)

            list_pool = ThreadPoolExecutor(max_workers=list_workers)
            page_futures = {list_pool.submit(fetch_page, p): p for p in pages}
            try:
                for fut in as_completed(page_futures):
                    if should_stop and should_stop():
                        break
                    try:
                        submit(fut.result())
                    except Exception as exc:
                        print(f"  ERROR listing page {page_futures[fut]}: {exc}")
                    pages_done += 1
                    if page_cb:
                        page_cb(pages_done, total_pages)
                    # Process detail results that finished during listing.
                    drain_available()
            finally:
                # Cancel pending page fetches immediately so Stop is responsive.
                list_pool.shutdown(wait=False, cancel_futures=True)

            # Safety net: the site's pagination can under-report the last page, and
            # the /entry list clamps out-of-range pages to the newest entries. After
            # the detected pages, keep probing forward until 3 consecutive pages
            # yield no NEW games (empty or all-duplicate) — so we never stop short of
            # the real last page. Bounded so a misbehaving site can't loop forever.
            if not max_pages and not (should_stop and should_stop()):
                page = total_pages + 1
                empty_streak = 0
                while empty_streak < 3 and page <= total_pages + 1500:
                    if should_stop and should_stop():
                        break
                    try:
                        extra = fetch_page(page)
                    except Exception:
                        break
                    before = counters["submitted"]
                    submit(extra)
                    if counters["submitted"] == before:
                        empty_streak += 1
                    else:
                        empty_streak = 0
                        print(f"  page {page} had new games beyond the reported "
                              f"{total_pages} pages — continuing.")
                    drain_available()
                    page += 1

            # Wait for remaining detail results. On stop, still save the ones
            # that already finished (don't throw away completed work).
            while counters["done"] < counters["submitted"]:
                if should_stop and should_stop():
                    drain_available()
                    break
                try:
                    item = results_q.get(timeout=1)
                except _queue.Empty:
                    continue
                process_one(item)

            # Retry games that failed (usually transient 503/timeout) so no data
            # is silently lost. One sequential, gentle pass.
            if failed and not (should_stop and should_stop()):
                retry_list = list(failed)
                failed.clear()
                print(f"Retrying {len(retry_list)} game(s) that failed...")
                for r_idx, (slug, title) in enumerate(retry_list, 1):
                    if should_stop and should_stop():
                        break
                    try:
                        info = self.scrape_game_details(slug)
                        if info:
                            info["title"] = info.get("title") or title
                            on_game(info)
                    except Exception as exc:
                        print(f"  ERROR (retry) {slug}: {exc}")
                    if game_cb:
                        game_cb(r_idx, len(retry_list))
                print(f"Retry done ({len(retry_list)} game(s)).")
            return counters["submitted"]
        finally:
            detail_pool.shutdown(wait=False, cancel_futures=True)

    def resolve_build_id_sources(self, slug: str, build_id: str) -> List[str]:
        """Fetch the build-id page and return the numeric source IDs linked on it."""
        session = self._create_session(self.retries)
        try:
            text = self._get(f"/game/{slug}/{build_id}", session=session)
            soup = parse_html(text)
            source_ids = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                m = re.match(rf"/game/{re.escape(slug)}/(\d+)", href)
                if m:
                    sid = m.group(1)
                    if sid not in source_ids:
                        source_ids.append(sid)
            return source_ids
        finally:
            session.close()

    def scrape_game_details(self, slug: str) -> Optional[Dict]:
        session = self._create_session(self.retries)
        try:
            url = f"/game/{slug}"
            text = self._get(url, session=session)
            soup = parse_html(text)

            # Clean display title from the page heading (falls back to slug later).
            h1 = soup.find("h1")
            page_title = h1.get_text(strip=True) if h1 else None

            # Title ID from the sidebar - but only accept a real 16-hex id.
            # (Some pages show a "Title ID: None" placeholder in the first span.)
            title_id = None
            for tag in soup.select("li.list-group-item span.text-uppercase"):
                candidate = tag.get_text(strip=True).upper()
                if re.fullmatch(r"[A-F0-9]{16}", candidate):
                    title_id = candidate
                    break
            if not title_id:
                for card in soup.select("div.card"):
                    tid_match = re.search(r"Title Id\s*[:\-]?\s*([A-Fa-f0-9]{16})", card.get_text(" "), re.IGNORECASE)
                    if tid_match:
                        title_id = tid_match.group(1).upper()
                        break

            sources = []
            seen_bids = set()

            def add_source(
                bid: str,
                sid: Optional[str],
                tid: Optional[str],
                names: List[str] = None,
                version: Optional[str] = None,
                upload_date: Optional[str] = None,
                cheat_count: Optional[int] = None,
            ):
                bid = bid.upper()
                if bid in seen_bids:
                    return
                seen_bids.add(bid)
                names = names or []
                # Cheat count ignores the header line and --SectionStart/End-- markers.
                counted = sum(1 for n in names if n and not n.strip().startswith("--"))
                # Table-layout builds carry no cheat names in the HTML, only the
                # "Available cheats" number. Use that count when we couldn't parse
                # individual names.
                if not counted and cheat_count:
                    counted = cheat_count
                # A build that cheatslips lists on the game page HAS cheats to
                # download, even when it reports 0 / we can't read a reliable
                # count. Never store a misleading 0 from cheatslips — store None
                # ("unknown / not verified") instead, so the build is still shown
                # and downloaded; the real count comes from the downloaded file
                # (parse_valid_cheats / recount_cheats_from_disk).
                cheat_count = counted if counted and counted > 0 else None
                sources.append({
                    "source_id": sid,
                    "build_id": bid,
                    "title_id": tid.upper() if tid else title_id,
                    "version": version,
                    "upload_date": upload_date,
                    "cheat_count": cheat_count,
                    "cheat_names": names,
                })

            # Cards (common layout)
            for card in soup.select("div.card"):
                card_text = card.get_text(" ")
                bid_match = re.search(r"Build Id\s*[:\-]?\s*([A-Fa-f0-9]{16})", card_text, re.IGNORECASE)
                tid_match = re.search(r"Title Id\s*[:\-]?\s*([A-Fa-f0-9]{16})", card_text, re.IGNORECASE)
                if not bid_match:
                    continue

                bid = bid_match.group(1).upper()
                card_tid = tid_match.group(1).upper() if tid_match else title_id

                # find the source details link: e.g. /game/slug/1234 (numeric source id)
                source_id = None
                for a in card.select("a[href^='/game/']"):
                    href = a.get("href", "")
                    parts = href.strip("/").split("/")
                    if len(parts) >= 3 and parts[0] == "game" and parts[-1].isdigit():
                        source_id = parts[-1]
                        break

                # cheat names in the card; the first <li> is a header containing the version
                li_items = card.select("ul.list-unstyled li")
                cheat_names = []
                for idx, li in enumerate(li_items):
                    txt = li.get_text(strip=True)
                    if idx == 0 and ("TID:" in txt or "BID:" in txt):
                        continue  # version/header line, not an actual cheat
                    if txt:
                        cheat_names.append(txt)

                # version: e.g. "... Ivalice Chronicles 1.4.0 TID: ... BID: ..."
                version = extract_version(li_items[0].get_text(" ", strip=True)) if li_items else None

                # upload date: e.g. "uploaded: 19 Jun 2026"
                upload_date = None
                um = re.search(r"uploaded:\s*(\d{1,2}\s+\w+\s+\d{4})", card_text)
                if um:
                    upload_date = um.group(1).strip()

                add_source(bid, source_id, card_tid, cheat_names, version, upload_date)

            # Table layout (e.g. Jump Force / "Game releases") where each row is a build/version
            for table in soup.find_all("table"):
                headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
                if "build id" not in headers:
                    continue
                # Column that holds the per-build cheat count (e.g. "Available cheats").
                avail_idx = next(
                    (i for i, h in enumerate(headers) if "available" in h and "cheat" in h),
                    None,
                )
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if not tds:
                        continue
                    bid_match = re.search(r"([A-Fa-f0-9]{16})", tds[0].get_text(" "), re.IGNORECASE)
                    if not bid_match:
                        continue
                    bid = bid_match.group(1).upper()
                    if bid in seen_bids:
                        continue
                    # "Latest cheats" column often holds an upload date.
                    table_date = None
                    dm = re.search(r"\d{1,2}\s+\w+\s+\d{4}", tds[-1].get_text(" "))
                    if dm:
                        table_date = dm.group(0)
                    # "Available cheats" column: the number of cheats cheatslips
                    # lists for this build. Captured so the build shows its real
                    # count instead of 0 even when the API doesn't return it.
                    avail_count = None
                    if avail_idx is not None and avail_idx < len(tds):
                        cm = re.search(r"\d+", tds[avail_idx].get_text(" "))
                        if cm:
                            avail_count = int(cm.group(0))
                    # The API download works by title id + build id, so we no
                    # longer resolve numeric source pages (saves a request each).
                    add_source(bid, None, title_id, upload_date=table_date,
                               cheat_count=avail_count)

            if not sources:
                return None

            return {
                "slug": slug,
                "title": page_title,
                "title_id": title_id,
                "sources": sources,
            }
        finally:
            session.close()


class CheatslipsAPI:
    """Official CheatSlips REST API (https://www.cheatslips.com/api/v1).

    Cheat *content* requires an API token (obtained from your account, or via
    POST /token with email+password). Metadata (names, build ids, credits) is
    available without a token. This replaces the browser/reCAPTCHA download flow.
    """

    API_BASE = "https://www.cheatslips.com/api/v1"
    PLACEHOLDER = "Please register and send APIToken"

    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SwitchCheatsScraper/1.0",
            "Accept": "application/json",
        })
        retry = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        if token:
            self.session.headers["X-API-TOKEN"] = token

    def get_token(self, email: str, password: str) -> str:
        """Exchange email+password for an API token (POST /token)."""
        resp = self.session.post(
            f"{self.API_BASE}/token",
            json={"email": email, "password": password},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            token = (resp.json() or {}).get("token")
            if token:
                self.token = token
                self.session.headers["X-API-TOKEN"] = token
                return token
        if resp.status_code in (401, 404):
            raise RuntimeError("Login failed - wrong email/password for cheatslips.com.")
        raise RuntimeError(f"Token request failed (HTTP {resp.status_code}).")

    def count(self) -> int:
        resp = self.session.get(f"{self.API_BASE}/cheats/count", timeout=self.timeout)
        resp.raise_for_status()
        return (resp.json() or {}).get("count", 0)

    def get_game(self, title_id: str) -> Dict:
        """All cheats for a title id (each cheat has buildid, content, credits)."""
        resp = self.session.get(f"{self.API_BASE}/cheats/{title_id}", timeout=self.timeout)
        if resp.status_code in (401, 403):
            # Surface auth errors as data so callers can detect a bad token.
            try:
                return resp.json()
            except Exception:
                return {"message": "Invalid token"}
        if resp.status_code == 404:
            # Title not on cheatslips (e.g. a GBAtemp-only game). Not an error.
            return {"message": "not found", "cheats": []}
        resp.raise_for_status()
        return resp.json()

    def get_build(self, title_id: str, build_id: str) -> Dict:
        resp = self.session.get(
            f"{self.API_BASE}/cheats/{title_id}/{build_id}", timeout=self.timeout
        )
        if resp.status_code in (401, 403):
            try:
                return resp.json()
            except Exception:
                return {"message": "Invalid token"}
        resp.raise_for_status()
        return resp.json()

    def token_works(self) -> bool:
        """Verify the token returns real content (not the register placeholder)."""
        try:
            data = self.get_game("010038B015560000")  # Final Fantasy Tactics
        except Exception:
            return False
        if "invalid token" in str(data.get("message", "")).lower():
            return False
        cheats = (data or {}).get("cheats") or []
        if not cheats:
            return True  # nothing to compare; assume ok
        content = cheats[0].get("content") or ""
        return self.PLACEHOLDER not in content


def enrich_info_with_api(info: Dict, api: "CheatslipsAPI") -> Dict:
    """Merge all API-provided fields into an HTML-scraped game info dict.

    Adds game image/banner and, per build, credits/description/cheat id and the
    authoritative cheat-name list. Title id + version + upload date come from the
    HTML scrape (the API does not expose version/date).
    """
    tid = info.get("title_id")
    if not tid or len(tid) != 16:
        return info
    try:
        data = api.get_game(tid)
    except Exception:
        return info
    info["image"] = data.get("image") or info.get("image")
    info["banner"] = data.get("banner")
    if data.get("name") and not info.get("title"):
        info["title"] = data.get("name")
    if data.get("slug") and not info.get("slug"):
        info["slug"] = data.get("slug")

    by_bid = {}
    for c in (data.get("cheats") or []):
        b = (c.get("buildid") or "").upper()
        if b:
            by_bid[b] = c

    existing_bids = {(s.get("build_id") or "").upper() for s in info.get("sources", [])}

    # Enrich the builds we already found via HTML. ``content`` is captured too
    # (transient, not stored in the DB) so a token-authenticated scrape can save
    # the cheat files in the same pass without a second API round-trip.
    for src in info.get("sources", []):
        c = by_bid.get((src.get("build_id") or "").upper())
        if not c:
            continue
        src["credits"] = c.get("credits")
        src["description"] = c.get("description")
        src["cheat_id"] = c.get("id")
        src["content"] = c.get("content")
        titles = c.get("titles")
        if not titles and c.get("content"):
            # Table-layout builds have no cheat names in the HTML, and the API
            # sometimes returns them without a ``titles`` list. Parse the real
            # cheat names from the content so the count is accurate and the
            # build is not dropped by the "cheats only" filter.
            titles = parse_cheat_names_from_content(c["content"])
        if titles:
            src["cheat_names"] = titles
            src["cheat_count"] = len(titles)

    # Add builds the API knows about but the HTML scrape missed (union).
    for bid, c in by_bid.items():
        if bid in existing_bids:
            continue
        titles = c.get("titles") or []
        if not titles and c.get("content"):
            titles = parse_cheat_names_from_content(c["content"])
        info.setdefault("sources", []).append({
            "build_id": bid,
            "title_id": tid,
            "source_id": None,
            "version": None,
            "upload_date": None,
            # Unknown (None) rather than a misleading 0 — the real count comes
            # from the downloaded file.
            "cheat_count": len(titles) or None,
            "cheat_names": titles,
            "credits": c.get("credits"),
            "description": c.get("description"),
            "cheat_id": c.get("id"),
            "content": c.get("content"),
        })
    return info


def refresh_titles_from_api(api: "CheatslipsAPI", db: "GameDatabase",
                            title_ids: List[str], progress_cb=None, should_stop=None) -> int:
    """Rebuild DB rows for the given title ids from authoritative API data.

    Fixes entries that ended up with 0 cheats by pulling the real build list,
    cheat names, credits and descriptions from the API. Existing version/upload
    date (HTML-only) are preserved.
    """
    total = len(title_ids)
    updated = 0
    print(f"Refreshing {total} game(s) from the API...")
    for i, tid in enumerate(title_ids, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        try:
            data = api.get_game(tid)
        except Exception as exc:
            print(f"  ERROR {tid}: {exc}")
            if progress_cb:
                progress_cb(i, total)
            continue
        sources = []
        for c in (data.get("cheats") or []):
            bid = (c.get("buildid") or "").upper()
            if not bid:
                continue
            titles = c.get("titles") or []
            sources.append({
                "build_id": bid, "title_id": tid, "source_id": None,
                "version": None, "upload_date": None,
                "cheat_count": len(titles), "cheat_names": titles,
                "credits": c.get("credits"), "description": c.get("description"),
                "cheat_id": c.get("id"),
            })
        if sources:
            db.upsert_game({
                "slug": data.get("slug"), "title": data.get("name"),
                "title_id": tid, "image": data.get("image"),
                "banner": data.get("banner"), "sources": sources,
            })
            updated += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"Refresh finished: {updated} game(s) updated.")
    return updated


def api_download_from_db(api: "CheatslipsAPI", db: "GameDatabase", output_dir,
                         title_ids: Optional[List[str]] = None,
                         resume: bool = True, flat_output: bool = False,
                         progress_cb=None, should_stop=None, max_workers: int = 1,
                         stats: Optional[dict] = None, pause: float = 0.15) -> int:
    """Download cheat files for the given title ids (or all in the DB) via the API.

    No browser/reCAPTCHA. Writes titles/{titleId}/cheats/{buildId}.txt. Returns
    the number of newly written files.

    Requests run ONE at a time with a small ``pause`` between them: cheatslips'
    cheat-content API throttles aggressively when hit with several requests at
    once, so a single paced request stream trips the limit far less often than a
    parallel pool did (``max_workers`` is kept only for backward compatibility
    and no longer parallelises).

    If ``stats`` (a dict) is passed it is filled with the run counters plus a
    ``quota_hit`` flag, so callers can tell whether cheatslips rate-limited the
    download and decide to fall back to the browser.
    """
    out = Path(output_dir)
    if title_ids is None:
        title_ids = db.all_title_ids()
    downloaded = scan_downloaded_build_ids(out) if resume else set()
    total = len(title_ids)

    # Thread-safe counters and locks
    lock = threading.Lock()
    counters = {"saved": 0, "skipped": 0, "notfound": 0, "done": 0, "quota": 0,
                "consec_quota": 0}
    saved_pairs = []  # (title_id, build_id) of files actually downloaded this run
    quota_pairs = []  # (title_id, build_id) that returned a quota message
    quota_hit = threading.Event()  # set once cheatslips reports the download quota

    print(f"API download: {total} game(s) to check "
          f"(sequential, {pause:g}s pause between requests).")

    def download_game(tid):
        """Download a single game's cheats. Returns (saved_count, skip, notfound)."""
        if should_stop and should_stop():
            return 0, 0, 0
        # Once the account's download quota is exhausted every further request just
        # returns the quota message, so stop hitting the API for the rest.
        if quota_hit.is_set():
            with lock:
                counters["done"] += 1
            return 0, 0, 0

        local_saved = 0
        local_skipped = 0
        local_notfound = 0

        try:
            # Check resume status
            if resume:
                info = db.get_game_info(tid)
                if info and info["sources"]:
                    bids = {(s["build_id"] or "").upper() for s in info["sources"] if s["build_id"]}
                    with lock:
                        if bids and bids <= downloaded:
                            local_skipped = 1
                            counters["done"] += 1
                            return 0, 1, 0

            # Fetch game from API
            game = api.get_game(tid)
            msg = str(game.get("message", "")) if isinstance(game, dict) else ""
            if "invalid token" in msg.lower():
                raise RuntimeError("API token was rejected (invalid/expired).")

            if not (game.get("cheats") or []):
                local_notfound = 1
                with lock:
                    counters["done"] += 1
                return 0, 0, 1

            # Collect valid cheat contents grouped by build id. The API can list
            # several cheat uploads for the SAME build id with different codes —
            # we merge them into one file so no cheat is lost.
            bid_contents: Dict[str, List[str]] = {}
            for cheat in (game.get("cheats") or []):
                bid = (cheat.get("buildid") or "").upper()
                if not bid:
                    continue
                content = cheat.get("content") or ""
                if CheatslipsAPI.PLACEHOLDER in content:
                    raise RuntimeError("API token invalid/missing - cannot read cheat content.")

                # Skip invalid content, but never let one build abort the whole
                # batch. Log exactly what came back so the cause is visible.
                if not is_valid_cheat_content(content):
                    snippet = content.strip().replace("\n", " ")[:70]
                    if is_quota_message(content):
                        with lock:
                            counters["quota"] += 1
                            counters["consec_quota"] += 1
                            cq = counters["consec_quota"]
                            quota_pairs.append((tid, bid))
                        print(f"  QUOTA {tid}/{bid}: short quota message from the API "
                              f"(len={len(content.strip())}: {snippet!r})")
                        # The API's per-window limit is exhausted. Once several
                        # builds IN A ROW return the quota message, stop hammering it
                        # (nothing more will download without a reset) — do NOT churn
                        # through the whole remaining list. Only a quota reset refills
                        # it, which the reset loop does automatically.
                        if cq >= 8 and not quota_hit.is_set():
                            quota_hit.set()
                            print("  ⚠ API limit reached (several 'quota exceeded' in a "
                                  "row) — stopping. Turn on 'Auto reset API limit' to "
                                  "reset the quota and continue automatically.")
                        continue  # skip only this build; keep trying the rest
                    print(f"  SKIP {tid}/{bid}: empty/invalid content "
                          f"(len={len(content.strip())}: {snippet!r})")
                    continue

                bid_contents.setdefault(bid, []).append(content)

            for bid, contents in bid_contents.items():
                save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
                save_path = save_dir / f"{bid}.txt"

                with lock:
                    if resume and (bid in downloaded or save_path.exists()):
                        continue
                    # Save outside lock (only stat-checks under lock)

                merged = merge_cheat_contents(*contents)
                if not merged.strip():
                    continue
                # save_cheat_merged also unions with any existing file on disk.
                save_cheat_merged(save_path, merged)

                with lock:
                    downloaded.add(bid)
                    local_saved += 1
                    counters["saved"] += 1
                    counters["consec_quota"] = 0    # progress -> reset the streak
                    saved_pairs.append((tid, bid))

            with lock:
                counters["done"] += 1

        except Exception as exc:
            print(f"  ERROR {tid}: {exc}")
            with lock:
                counters["done"] += 1

        return local_saved, local_skipped, local_notfound

    # Download ONE game at a time with a small pause between requests. Spreading
    # the requests out (instead of firing 4 at once) trips the API's throttle far
    # less often, so we need far fewer quota resets.
    n = len(title_ids)
    for idx, tid in enumerate(title_ids):
        if (should_stop and should_stop()) or quota_hit.is_set():
            break
        download_game(tid)
        if progress_cb:
            with lock:
                progress_cb(counters["done"], total)
        if pause and idx + 1 < n:
            time.sleep(pause)

    # Mark every downloaded build as coming from cheatslips (main thread).
    for tid, bid in saved_pairs:
        try:
            db.set_build_source(tid, bid, "cheatslips")
        except Exception:
            pass

    print(f"API download finished: {counters['saved']} new file(s) written, "
          f"{counters['skipped']} already complete, {counters['notfound']} not on cheatslips.")
    if counters["quota"]:
        quota_file = out / "quota_skipped.txt"
        try:
            lines = [f"{tid} {bid}" for tid, bid in quota_pairs]
            quota_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"⚠ {counters['quota']} build(s) returned a 'quota exceeded' message from "
                  f"cheatslips and were skipped. List written to: {quota_file}")
        except Exception as exc:
            print(f"⚠ {counters['quota']} build(s) returned a 'quota exceeded' message from "
                  f"cheatslips and were skipped (could not write list: {exc}).")
    if stats is not None:
        stats.update(counters)
        stats["quota_hit"] = quota_hit.is_set()
    return counters["saved"]


def download_build_list(api: "CheatslipsAPI", db: "GameDatabase", output_dir,
                        pairs: List[tuple], flat_output: bool = False,
                        progress_cb=None, should_stop=None) -> int:
    """Download specific (title_id, build_id) pairs via the API only (no reset,
    no browser). Used for a quick API-only retry of previously-skipped builds.

    cheatslips' per-BUILD endpoint returns empty, so this delegates to the
    per-TITLE engine (``download_with_quota_reset`` with no reset/browser
    callbacks): one ``get_game`` per title fetches all of its builds at once.
    Returns the number of newly saved files.
    """
    return download_with_quota_reset(
        api, db, output_dir, pairs,
        reset_cb=None, browser_download_cb=None,
        flat_output=flat_output, progress_cb=progress_cb,
        should_stop=should_stop)


def missing_build_pairs(db: "GameDatabase", output_dir) -> List[Tuple[str, str, str, str]]:
    """Return (title_id, build_id, slug, source_id) for every build whose cheat
    file is NOT yet on disk. Quota-placeholder files count as missing because
    scan_downloaded_build_ids ignores them.
    """
    downloaded = scan_downloaded_build_ids(output_dir)
    pairs: List[Tuple[str, str, str, str]] = []
    seen = set()
    for tid, bid, slug, sid in db.builds_for_download():
        t = (tid or "").upper()
        b = (bid or "").upper()
        if not t or not b:
            continue
        if b in downloaded:
            continue
        if is_blocked_pair(t, b) or is_placeholder_build_id(b, t):
            continue
        key = (t, b)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((t, b, slug, sid))
    return pairs


def _fetch_and_save_build(api: "CheatslipsAPI", db: "GameDatabase", out: Path,
                          tid: str, bid: str, flat_output: bool,
                          downloaded: set, log=print) -> str:
    """Try to download one build via the API and save it.

    Returns one of: "saved", "quota", "skip", "error".
    Raises only on a fatal invalid-token condition (caller should abort).
    """
    try:
        data = api.get_build(tid, bid)
    except Exception as exc:
        log(f"  ERROR {tid}/{bid}: {exc}")
        return "error"

    if isinstance(data, dict) and data.get("message") and not data.get("content"):
        msg = str(data.get("message", "")).lower()
        if "invalid token" in msg:
            raise RuntimeError("API token invalid/expired.")
        if "quota" in msg or "limit" in msg:
            return "quota"
        log(f"  SKIP {tid}/{bid}: {data.get('message')}")
        return "skip"

    content = (data or {}).get("content") or ""
    if is_quota_message(content):
        return "quota"
    if not is_valid_cheat_content(content):
        snippet = content.strip().replace("\n", " ")[:70]
        log(f"  SKIP {tid}/{bid}: invalid content ({snippet!r})")
        return "skip"

    save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
    save_path = save_dir / f"{bid}.txt"
    save_cheat_merged(save_path, content)
    downloaded.add(bid)
    try:
        db.set_build_source(tid, bid, "cheatslips")
    except Exception:
        pass
    log(f"  SAVED {tid}/{bid}")
    return "saved"


def _api_download_title(api: "CheatslipsAPI", db: "GameDatabase", out: Path,
                        tid: str, needed_bids: set, downloaded: set,
                        flat_output: bool, reset_cb, reset_state: list,
                        max_resets: int, should_stop, log, pause: float = 0.35) -> int:
    """Download ALL cheats for one title via the per-title API endpoint.

    cheatslips' per-BUILD endpoint (``get_build``) returns empty, but the
    per-TITLE endpoint (``get_game``) returns real codes for every build of the
    title in a SINGLE request — so one call covers all of a title's builds,
    keeping the request count (and thus the rate-limit/throttle) low.

    "Limit reached" is detected as: the API answered with cheat entries but none
    carry real codes (only a short placeholder). On that, we press the quota
    reset and retry the SAME title, repeating until it succeeds or the reset
    budget is exhausted — bypassing the limit WITHOUT the browser. Returns the
    number of builds saved; whatever stays missing is left for the browser pass.
    """
    MAX_TITLE_RESETS = 8            # resets spent on one stubborn title
    title_resets = 0
    while True:
        try:
            data = api.get_game(tid)
        except Exception as exc:
            log(f"  API error for {tid}: {exc}")
            return 0
        msg = str((data or {}).get("message", "")).lower()
        if "invalid token" in msg:
            raise RuntimeError("API token invalid/expired.")
        cheats = (data or {}).get("cheats") or []

        # Group every upload's content by build id (a build can have several).
        by_bid: Dict[str, list] = {}
        any_valid = False
        for c in cheats:
            b = (c.get("buildid") or c.get("build_id") or "").upper()
            if not b:
                continue
            cont = c.get("content") or ""
            by_bid.setdefault(b, []).append(cont)
            if is_valid_cheat_content(cont):
                any_valid = True

        # Throttle / "limit reached" — the reset trigger: cheat entries present
        # but none contain real codes.
        if cheats and not any_valid:
            if (reset_cb and reset_state[0] < max_resets
                    and title_resets < MAX_TITLE_RESETS
                    and not (should_stop and should_stop())):
                reset_state[0] += 1
                title_resets += 1
                log(f"  LIMIT on {tid}: API throttled — pressing reset "
                    f"(#{reset_state[0]}) and retrying via API...")
                if not reset_cb():
                    log("  Quota reset failed — leaving the rest for the browser.")
                    return 0
                if pause:
                    time.sleep(pause)
                continue
            log(f"  LIMIT on {tid}: still throttled — will try the browser later.")
            return 0

        # Not throttled: save every needed build we actually got codes for.
        saved = 0
        for bid in list(needed_bids):
            contents = [c for c in by_bid.get(bid, []) if is_valid_cheat_content(c)]
            if not contents:
                continue           # no API codes for this build -> browser pass
            merged = "\n\n".join(contents)
            save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
            save_cheat_merged(save_dir / f"{bid}.txt", merged)
            downloaded.add(bid)
            try:
                db.set_build_source(tid, bid, "cheatslips")
            except Exception:
                pass
            saved += 1
            log(f"  SAVED (api) {tid}/{bid}")
        return saved


def download_with_quota_reset(api: "CheatslipsAPI", db: "GameDatabase", output_dir,
                              pairs: List[Tuple],
                              reset_cb: Optional[Callable[[], bool]] = None,
                              browser_download_cb: Optional[Callable] = None,
                              flat_output: bool = False,
                              progress_cb=None, should_stop=None,
                              log=print, max_resets: int = 1000) -> int:
    """Download ``pairs`` fastest-path-first, in two phases:

      PHASE A — API by title: one ``get_game`` per title fetches EVERY build of
        that title at once (few requests -> little throttling). When the API
        throttles ("limit reached"), press the quota reset and retry via the
        API, repeating so the limit is bypassed WITHOUT the browser.
      PHASE B — Browser: only for the builds the API does not serve (codes that
        exist only as a website download). Runs once, after the API pass.

    Returns the number of files saved.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    downloaded = scan_downloaded_build_ids(out)
    saved = 0
    reset_state = [0]          # total resets used (mutable so the helper shares it)
    unavailable = []           # (tid, bid) builds confirmed to have no codes

    # Group missing builds by title so ONE API request covers all its builds.
    by_title: Dict[str, dict] = {}
    for entry in pairs:
        tid = (entry[0] or "").upper()
        bid = (entry[1] or "").upper()
        if not tid or not bid or bid in downloaded:
            continue
        slot = by_title.setdefault(tid, {"needed": set(), "entries": {}})
        slot["needed"].add(bid)
        slot["entries"][bid] = entry

    total_builds = sum(len(v["needed"]) for v in by_title.values())
    total_titles = len(by_title)

    # ---------------- PHASE A: API + reset (no browser) ----------------
    log(f"API download: {total_builds} build(s) across {total_titles} title(s) — "
        f"per-title endpoint with quota resets.")
    still_missing = []
    # Small pause between titles to avoid hammering the API (the throttle is
    # count-based, ~3 requests per window, so a bigger pause would not avoid it —
    # the quota reset does the heavy lifting).
    API_PAUSE = 0.15
    for ti, (tid, slot) in enumerate(by_title.items(), 1):
        if should_stop and should_stop():
            log("Stopped by user.")
            break
        if progress_cb:
            progress_cb(ti, total_titles)
        saved += _api_download_title(api, db, out, tid, slot["needed"], downloaded,
                                     flat_output, reset_cb, reset_state, max_resets,
                                     should_stop, log)
        for bid in slot["needed"]:
            if bid not in downloaded:
                still_missing.append(slot["entries"][bid])
        if API_PAUSE and ti < total_titles:
            time.sleep(API_PAUSE)

    log(f"API pass done: {saved} file(s) saved via API, {reset_state[0]} reset(s) "
        f"used. {len(still_missing)} build(s) not available via the API.")

    # ---------------- PHASE B: browser only for API-less builds ----------------
    if browser_download_cb and still_missing and not (should_stop and should_stop()):
        n_b = len(still_missing)
        log(f"\n=== Browser pass: {n_b} build(s) only downloadable on the website ===")
        for j, entry in enumerate(still_missing, 1):
            if should_stop and should_stop():
                log("Stopped by user.")
                break
            tid = (entry[0] or "").upper()
            bid = (entry[1] or "").upper()
            slug = entry[2] if len(entry) > 2 else None
            sid = entry[3] if len(entry) > 3 else None
            if progress_cb:
                progress_cb(j, n_b)
            if not tid or not bid or bid in downloaded:
                continue
            log(f"  Browser download for {tid}/{bid}...")
            try:
                path = browser_download_cb(slug, tid, bid, sid)
            except Exception as exc:
                if looks_like_closed_browser(exc):
                    # The browser window/session is gone. Do NOT keep churning
                    # through the remaining builds (each would fail the same way,
                    # flooding the log and looking like an endless loop) — stop
                    # now. Re-running resumes where this left off.
                    log("  The browser was closed — stopping the browser download "
                        "here.")
                    log("  Re-run the download to resume; already-downloaded builds "
                        "are skipped.")
                    break
                log(f"  Browser download error for {tid}/{bid}: {exc}")
                path = None
            if path == BUILD_UNAVAILABLE:
                # Conclusively no codes on cheatslips (codeless upload or no cheat
                # page). Mark it so future runs skip it instead of retrying.
                try:
                    db.mark_build_unavailable(tid, bid, "codeless")
                except Exception:
                    pass
                unavailable.append((tid, bid))
                log(f"  UNAVAILABLE {tid}/{bid}: no codes on cheatslips — "
                    f"marked to skip in future runs.")
            elif path:
                downloaded.add(bid)
                saved += 1
                try:
                    db.set_build_source(tid, bid, "cheatslips-web")
                except Exception:
                    pass
                log(f"  SAVED (browser) {tid}/{bid}")

    log(f"Download finished: {saved} file(s) saved, {reset_state[0]} quota reset(s) used.")
    if unavailable:
        log(f"{len(unavailable)} build(s) had no codes on cheatslips and were marked "
            f"to skip next time:")
        for tid, bid in unavailable:
            log(f"    {tid}/{bid}")
        try:
            skip_file = out / "unavailable_builds.txt"
            existing = skip_file.read_text(encoding="utf-8") if skip_file.exists() else ""
            lines = {ln.strip() for ln in existing.splitlines() if ln.strip()}
            lines.update(f"{tid} {bid}" for tid, bid in unavailable)
            skip_file.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
            log(f"  Full list written to: {skip_file}")
        except Exception:
            pass
    return saved


GBATEMP_REPO = "HamletDuFromage/switch-cheats-db"


def parse_cheat_names_from_content(text: str) -> List[str]:
    """Extract cheat names from an Atmosphere cheat file ([Name] / {Name} headers)."""
    names = []
    # Some archive files start with a UTF-8 BOM which is NOT stripped by
    # str.strip() and would break header detection on the first line.
    for line in (text or "").replace("﻿", "").splitlines():
        line = line.strip()
        m = re.match(r"^[\[{](.+?)[\]}]$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def is_quota_message(text: str) -> bool:
    """True only if the content IS a cheatslips quota/limit message.

    A real Atmosphere cheat file is long (many hex code lines); the quota response
    is a short plain message. We therefore only treat it as a quota hit when the
    content is short AND mentions the quota — otherwise a perfectly valid cheat
    that merely contains the words "quota exceeded" (e.g. in a cheat name) would
    be wrongly discarded.
    """
    if not text:
        return False
    stripped = text.strip()
    return len(stripped) < 300 and "quota exceeded" in stripped.lower()


def is_valid_cheat_content(text: str) -> bool:
    """Check if cheat content is valid (not a placeholder or quota message).

    Returns False if the content is empty, a short quota message, or the API
    placeholder. A long real cheat file is always considered valid.
    """
    if not text or not text.strip():
        return False
    if is_quota_message(text):
        return False
    if CheatslipsAPI.PLACEHOLDER in text:
        return False
    return True


# A cheat "block" starts at a [Name] or {Master} header line and runs until the
# next header. Used to merge several sources of the same build id into one file.
_CHEAT_HEADER_RE = re.compile(r"^\s*[\[{].+[\]}]\s*$")

# A real cheat contains at least one code line with a standalone 8-hex-digit word
# (e.g. "04000000", "58000000"). Used to tell real cheats from codeless "preview"
# entries (names only). Deliberately lenient — some archive uploads (ibnux) have
# non-standard code formatting ("0xABCDEF", 10-digit groups) that a strict
# "two 8-hex words" pattern would miss even though real codes are present.
_CHEAT_CODE_RE = re.compile(r"\b[0-9A-Fa-f]{8}\b")


def split_cheat_blocks(text: str) -> List[str]:
    """Split an Atmosphere cheat file into normalized blocks (one per cheat).

    Each block is a header line ([Name]/{Master}) plus its code lines, with
    trailing whitespace/blank lines stripped. Content before the first header
    (if any) becomes its own leading block.
    """
    blocks: List[str] = []
    cur: List[str] = []

    def flush():
        lines = [ln.rstrip() for ln in cur]
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            blocks.append("\n".join(lines))

    # Strip a leading UTF-8 BOM (some archive .txt files have one) so it doesn't
    # break header detection on the first line.
    for line in (text or "").replace("﻿", "").splitlines():
        if _CHEAT_HEADER_RE.match(line):
            flush()
            cur = [line]
        else:
            cur.append(line)
    flush()
    return blocks


def parse_valid_cheats(text: str) -> List[str]:
    """Names of cheats that actually contain code lines — the REAL cheat count.

    Unlike parse_cheat_names_from_content (which counts every [Name]/{Name}
    header, including codeless 'preview'/placeholder entries), this only counts a
    cheat when its block has at least one hex code pair. The result therefore
    reflects usable cheats and does NOT depend on cheatslips' (sometimes wrong)
    numbers. Section markers such as "[--- Something ---]" are ignored.
    """
    names: List[str] = []
    for block in split_cheat_blocks(text or ""):
        lines = block.splitlines()
        if not lines:
            continue
        m = re.match(r"^\s*[\[{](.+?)[\]}]\s*$", lines[0])
        if not m:
            continue  # leading content before the first header
        name = m.group(1).strip()
        if name.startswith("--"):
            continue  # section marker, not a cheat
        if _CHEAT_CODE_RE.search(block):
            names.append(name)
    return names


def cheat_file_is_empty(text: str) -> bool:
    """True if a cheat file has NO usable cheats: it is empty, only a
    quota/placeholder message, or contains only codeless names (no code lines)."""
    if not is_valid_cheat_content(text):
        return True
    return not parse_valid_cheats(text)


# Eine reine Hex-Code-Zeile (nur Hex-Ziffern + Whitespace), z.B.
# "04000000 00E0F762 00000063". Atmosphère-Cheat-Codes sind gegenueber
# Groß-/Kleinschreibung UNEMPFINDLICH: "00e0f762" und "00E0F762" sind derselbe
# Code. Genau das war die Duplikat-Ursache - zwei Quellen mit unterschiedlicher
# Hex-Schreibweise galten als verschiedene Cheats.
_HEXLINE_RE = re.compile(r"^[0-9A-Fa-f]{2,}(?:\s+[0-9A-Fa-f]+)*$")


def _cheat_block_key(block: str) -> str:
    """Normalisierter Vergleichsschluessel eines Cheat-Blocks fuer die Dedup.

    - leere Zeilen weg, Zeilen getrimmt, interner Whitespace kollabiert,
    - reine Hex-CODE-Zeilen in Großbuchstaben (case-egal, wie Atmosphère),
    - Header/Namen ([Name]/{Master}) bleiben unveraendert (case-sensitiv).

    So kollabieren NUR wirklich identische Cheats; Bloecke mit anderen Codes
    (z.B. "Max HP" fuer 12 verschiedene Adressen) bleiben unangetastet.
    """
    out: List[str] = []
    for ln in block.splitlines():
        s = ln.strip()
        if not s:
            continue
        s = re.sub(r"[ \t]+", " ", s)
        if _HEXLINE_RE.match(s):
            s = s.upper()
        out.append(s)
    return "\n".join(out)


def merge_cheat_contents(*texts: str) -> str:
    """Merge several cheat files into one, keeping the UNION of distinct cheats.

    Cheat blocks that are identical UP TO hex-code case and whitespace collapse
    into one (Atmosphère treats hex case-insensitively, so two sources that only
    differ in code casing were wrongly kept as duplicates); blocks that differ in
    their actual codes (even with the same name, e.g. "Max HP" for 12 different
    addresses) are all kept, so no real cheat is ever lost. Order is preserved
    (first source first); the FIRST spelling of a duplicate is the one stored.
    """
    seen = set()
    out_blocks: List[str] = []
    for text in texts:
        if not text or not text.strip():
            continue
        for block in split_cheat_blocks(text):
            key = _cheat_block_key(block)
            if not key or key in seen:
                continue
            seen.add(key)
            out_blocks.append(block)
    return ("\n\n".join(out_blocks) + "\n") if out_blocks else ""


def save_cheat_merged(path: Path, new_content: str) -> bool:
    """Write `new_content` to `path`, merging with any existing file so that the
    result is the union of all cheats. Returns True if the file was written.

    Skips writing if the merge would not add anything new (keeps disk churn and
    timestamps stable for resume scans).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            existing = ""
    if not existing.strip():
        merged = merge_cheat_contents(new_content)
        if not merged.strip():
            return False
        path.write_text(merged, encoding="utf-8")
        return True
    merged = merge_cheat_contents(existing, new_content)
    # Compare on normalized content so we don't rewrite when nothing changed.
    def _norm(t):
        return "\n".join(ln.strip() for ln in t.splitlines() if ln.strip())
    if _norm(merged) == _norm(existing):
        return False
    path.write_text(merged, encoding="utf-8")
    return True


def recount_cheats_from_disk(db: "GameDatabase", output_dir, only_missing: bool = True,
                             progress_cb=None, should_stop=None) -> int:
    """Recompute cheat_count + cheat_names for builds from the downloaded files.

    Reads each build's file (titles/{tid}/cheats/{bid}.txt or by_bid/{bid}.txt)
    and writes back the REAL cheat count — the number of cheats that actually
    contain code lines (parse_valid_cheats), NOT cheatslips' reported number.
    Codeless/empty files therefore recount to 0. With only_missing=True only rows
    whose cheat_count is NULL are touched. Returns the number of rows updated.
    """
    out = Path(output_dir)
    where = "WHERE cheat_count IS NULL" if only_missing else ""
    rows = db._conn.execute(
        f"SELECT title_id, build_id, cheat_count, cheat_names FROM builds {where}"
    ).fetchall()
    total = len(rows)
    updated = 0
    for i, r in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid, bid = r[0], r[1]
        if bid:
            p1 = out / "titles" / (tid or "") / "cheats" / f"{bid}.txt"
            p2 = out / "by_bid" / f"{bid}.txt"
            p = p1 if p1.exists() else (p2 if p2.exists() else None)
            if p:
                try:
                    names = parse_valid_cheats(
                        p.read_text(encoding="utf-8", errors="replace"))
                    # Skip the write when the DB already matches the file, so a
                    # full recount over a big DB stays cheap (mostly reads).
                    new_json = json.dumps(names, ensure_ascii=False)
                    if r[2] == len(names) and (r[3] or "") == new_json:
                        pass
                    elif db.set_build_cheats(tid, bid, len(names), names):
                        updated += 1
                except Exception:
                    pass
        if progress_cb:
            progress_cb(i, total)
    print(f"Recounted cheats for {updated} build(s) from disk.")
    return updated


def find_empty_cheat_files(db: "GameDatabase", output_dir, progress_cb=None,
                           should_stop=None) -> List[Tuple[str, str]]:
    """Return (title_id, build_id) for every build whose .txt file exists on disk
    but has NO usable cheats (empty, quota/placeholder, or codeless names).

    These are files that look downloaded but contain nothing usable — e.g. a
    cheatslips "preview" ZIP with names only. Callers can list them, reset their
    count, or re-download them.
    """
    out = Path(output_dir)
    rows = db._conn.execute(
        "SELECT title_id, build_id FROM builds WHERE build_id IS NOT NULL"
    ).fetchall()
    total = len(rows)
    empty: List[Tuple[str, str]] = []
    for i, r in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid, bid = r[0], r[1]
        if bid:
            p1 = out / "titles" / (tid or "") / "cheats" / f"{bid}.txt"
            p2 = out / "by_bid" / f"{bid}.txt"
            p = p1 if p1.exists() else (p2 if p2.exists() else None)
            if p:
                try:
                    if cheat_file_is_empty(p.read_text(encoding="utf-8", errors="replace")):
                        empty.append((tid, bid))
                except Exception:
                    pass
        if progress_cb:
            progress_cb(i, total)
    print(f"Found {len(empty)} empty cheat file(s) on disk.")
    return empty


def cleanup_invalid_cheat_entries(db: "GameDatabase", output_dir, progress_cb=None, should_stop=None) -> int:
    """Reset cheat_count and cheat_names for builds with invalid/placeholder content.
    
    Scans downloaded cheat files and resets the database entry to cheat_count=0
    if the file content is invalid (empty, quota exceeded, or placeholder).
    Also deletes the invalid files from disk. Returns the number of entries cleaned up.
    """
    out = Path(output_dir)
    rows = db._conn.execute(
        "SELECT title_id, build_id FROM builds WHERE build_id IS NOT NULL"
    ).fetchall()
    total = len(rows)
    cleaned = 0
    deleted_files = 0
    
    for i, r in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid, bid = r[0], r[1]
        if bid:
            p1 = out / "titles" / (tid or "") / "cheats" / f"{bid}.txt"
            p2 = out / "by_bid" / f"{bid}.txt"
            p = p1 if p1.exists() else (p2 if p2.exists() else None)
            if p:
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    # Invalid = quota/placeholder message OR a codeless stub
                    # (names/ads only, not a single real code line). The DB row
                    # stays (visible with 0 cheats); only the junk file goes.
                    if not is_valid_cheat_content(content) or cheat_file_is_empty(content):
                        # Reset cheat count in database
                        if db.set_build_cheats(tid, bid, 0, []):
                            cleaned += 1
                        # Delete the invalid file
                        p.unlink()
                        deleted_files += 1
                except Exception:
                    pass
        if progress_cb:
            progress_cb(i, total)
    
    print(f"Cleaned up {cleaned} invalid cheat entries and deleted {deleted_files} invalid files.")
    return cleaned


def cleanup_titles_folder(db: "GameDatabase", output_dir, should_stop=None) -> Tuple[int, int]:
    """Remove title_id folders and cheat files that are not in the database.

    Returns (removed_title_ids, removed_files).
    """
    out = Path(output_dir)
    titles_dir = out / "titles"
    removed_tids = 0
    removed_files = 0

    rows = db._conn.execute(
        "SELECT title_id, build_id FROM builds WHERE title_id IS NOT NULL AND build_id IS NOT NULL"
    ).fetchall()
    allowed_pairs = {(tid.upper(), bid.upper()) for tid, bid in rows if tid and bid}
    allowed_tids = {tid for tid, _ in allowed_pairs}

    if titles_dir.exists():
        for tid_dir in titles_dir.iterdir():
            if should_stop and should_stop():
                print("Stopped by user.")
                break
            if not tid_dir.is_dir():
                continue
            tid = tid_dir.name.upper()
            if tid not in allowed_tids:
                try:
                    shutil.rmtree(tid_dir)
                    removed_tids += 1
                    print(f"Removed extra title folder: {tid_dir.name}")
                except Exception as exc:
                    print(f"Could not remove {tid_dir}: {exc}")
                continue

            cheats_dir = tid_dir / "cheats"
            if cheats_dir.exists():
                for txt in cheats_dir.glob("*.txt"):
                    bid = txt.stem.upper()
                    if (tid, bid) not in allowed_pairs:
                        try:
                            txt.unlink()
                            removed_files += 1
                            print(f"Removed extra cheat file: {tid}/{txt.name}")
                        except Exception as exc:
                            print(f"Could not remove {txt}: {exc}")

            # Remove now-empty directories, but keep the titles root.
            for sub in (cheats_dir, tid_dir):
                try:
                    if sub.exists() and not any(sub.iterdir()):
                        sub.rmdir()
                except Exception:
                    pass

    # Also clean the flat by_bid folder.
    by_bid_dir = out / "by_bid"
    if by_bid_dir.exists():
        for txt in by_bid_dir.glob("*.txt"):
            if should_stop and should_stop():
                print("Stopped by user.")
                break
            bid = txt.stem.upper()
            # Keep the file if this build_id exists for any title_id in the DB.
            if not any(bid == b for _, b in allowed_pairs):
                try:
                    txt.unlink()
                    removed_files += 1
                    print(f"Removed extra cheat file: by_bid/{txt.name}")
                except Exception as exc:
                    print(f"Could not remove {txt}: {exc}")
        try:
            if by_bid_dir.exists() and not any(by_bid_dir.iterdir()):
                by_bid_dir.rmdir()
        except Exception:
            pass

    return removed_tids, removed_files


def _gbatemp_latest_asset(name_candidates, repo: str = None):
    """Return (tag, download_url, size) for the first matching asset of the
    LATEST release of ``repo`` (defaults to the GBAtemp/HamletDuFromage repo)."""
    import requests
    repo = repo or GBATEMP_REPO
    r = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SwitchCheatsScraper"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    assets = {a["name"]: a for a in data.get("assets", [])}
    for name in name_candidates:
        if name in assets and assets[name].get("size", 0) > 1000:
            return data.get("tag_name"), assets[name]["browser_download_url"], assets[name].get("size")
    raise RuntimeError(f"No suitable archive asset found in the latest {repo} release.")


def download_gbatemp_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                             flat_output: bool = False, progress_cb=None, should_stop=None,
                             asset_candidates=None, source="gbatemp", label="GBAtemp",
                             repo: str = None):
    """Download the latest GBAtemp/HamletDuFromage cheat archive, extract the
    cheat files into our schema and add them to the database (source='gbatemp').

    ``asset_candidates`` chooses which release asset to pull (first match wins);
    ``source``/``label``/``repo`` let callers reuse this for other assets and
    other GitHub repos with the same titles/{tid}/cheats/{bid}.txt layout
    (e.g. sthetix/nx-cheats-db or the Breeze database). Always fetches the
    *latest* release, so the newest data is used automatically.

    If `api` is given, every imported title id is enriched with the game name,
    cover image, credits and description from the CheatSlips API for complete
    records. Returns (files_written, games).
    """
    import io
    import requests

    out = Path(output_dir)

    if asset_candidates is None:
        asset_candidates = ["contents_complete.zip", "titles_complete.zip"]
    tag, url, size = _gbatemp_latest_asset(asset_candidates, repo=repo)
    print(f"{label} archive: release {tag} ({round((size or 0) / 1e6, 1)} MB) - downloading...")
    raw = requests.get(url, timeout=180).content
    print(f"Downloaded {round(len(raw) / 1e6, 1)} MB, extracting...")

    zf = zipfile.ZipFile(io.BytesIO(raw))
    pat = re.compile(r"/([0-9A-Fa-f]{16})/cheats/([0-9A-Fa-f]{16})\.txt$")
    entries = [n for n in zf.namelist() if pat.search(n)]
    total = len(entries)
    print(f"{total} cheat files with build ids in archive.")

    games = {}  # title_id -> list of (build_id, names)
    written = 0
    stubs = 0
    for i, name in enumerate(entries, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        m = pat.search(name)
        tid, bid = m.group(1).upper(), m.group(2).upper()
        content = zf.read(name).decode("utf-8", "replace")

        # Some aggregated databases contain codeless stub files (cheat names,
        # ads like "From MAX-CHEATS.com", or junk lines without a single real
        # code). Never write those to disk: they would pollute titles/ (and
        # could merge ad headers into real cheat files) yet never count as
        # downloaded. The build still gets a DB row (visible with 0 cheats).
        names = parse_valid_cheats(content)
        if names:
            save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
            save_path = save_dir / f"{bid}.txt"
            if save_cheat_merged(save_path, content):
                written += 1
        else:
            stubs += 1

        games.setdefault(tid, []).append((bid, names))
        if progress_cb:
            progress_cb(i, total)
    if stubs:
        print(f"Skipped {stubs} codeless stub file(s) (no real code lines).")

    # Write the DB entries (source = gbatemp).
    for tid, builds in games.items():
        sources = [{
            "build_id": bid, "title_id": tid, "source_id": None,
            "version": None, "upload_date": None,
            "cheat_count": len(names), "cheat_names": names,
            "credits": None, "description": None, "cheat_id": None,
        } for bid, names in builds]
        db.upsert_game({"title_id": tid, "title": None, "slug": None,
                        "image": None, "banner": None, "sources": sources},
                       source=source)
    print(f"Integrated {written} cheat file(s) for {len(games)} game(s).")

    # Enrich the imported titles with full metadata from the CheatSlips API.
    if api is not None and games:
        print("Enriching imported games with names/covers/credits from the API...")
        tids = list(games.keys())
        for j, tid in enumerate(tids, 1):
            if should_stop and should_stop():
                break
            info = db.get_game_info(tid)
            if info:
                enrich_info_with_api(info, api)
                db.upsert_game(info)
            if progress_cb:
                progress_cb(j, len(tids))
        print("Enrichment done.")

    return written, len(games)


def download_hamlet_titledb_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                                    flat_output: bool = False, progress_cb=None, should_stop=None):
    """Download HamletDuFromage's ``titles_complete.zip`` from the LATEST release
    of switch-cheats-db and import it (source='hamlet-titledb').

    Same behaviour as ``download_gbatemp_archive`` but pinned to the TitleDB
    (``titles_complete.zip``) asset and always the newest release. Returns
    (files_written, games).
    """
    return download_gbatemp_archive(
        output_dir, db, api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop,
        asset_candidates=["titles_complete.zip"],
        source="hamlet-titledb", label="HamletDuFromage TitleDB")


def download_hamlet_60fps_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                                  flat_output: bool = False, progress_cb=None, should_stop=None):
    """Download HamletDuFromage's ``titles_60fps-res-gfx.zip`` from the LATEST
    release of switch-cheats-db and import it (source='hamlet-60fps').

    Same behaviour as ``download_gbatemp_archive`` but pinned to the 60 FPS /
    resolution / GFX cheat asset and always the newest release. Returns
    (files_written, games).
    """
    return download_gbatemp_archive(
        output_dir, db, api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop,
        asset_candidates=["titles_60fps-res-gfx.zip"],
        source="hamlet-60fps", label="HamletDuFromage 60FPS/Res/GFX")


STHETIX_REPO = "sthetix/nx-cheats-db"
BREEZE_REPO = "tomvita/NXCheatCode"


def download_sthetix_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                             flat_output: bool = False, progress_cb=None, should_stop=None):
    """Download ``titles_complete.zip`` from the LATEST sthetix/nx-cheats-db
    release and import it (source='sthetix').

    sthetix aggregates GBAtemp + graphics cheats + switch-cheats-db +
    cheatslips daily, so this is the freshest/most complete single archive
    (~141k cheats). Always fetches the newest release automatically.
    Returns (files_written, games).
    """
    return download_gbatemp_archive(
        output_dir, db, api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop,
        asset_candidates=["titles_complete.zip"],
        source="sthetix", label="Sthetix TitleDB", repo=STHETIX_REPO)


def download_breeze_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                            flat_output: bool = False, progress_cb=None, should_stop=None):
    """Download ``titles.zip`` (the Breeze/EdiZon-SE cheat database) from the
    LATEST tomvita/NXCheatCode release and import it (source='breeze').

    This is the database behind the Breeze homebrew, compiled from GBAtemp
    threads — partly a different code corpus than cheatslips. Always fetches
    the newest release automatically. Returns (files_written, games).
    """
    return download_gbatemp_archive(
        output_dir, db, api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop,
        asset_candidates=["titles.zip"],
        source="breeze", label="Breeze NXCheatCode", repo=BREEZE_REPO)


def download_repo_cheats_zip(output_dir, db: "GameDatabase", repo: str,
                             source: str, label: str,
                             api: "CheatslipsAPI" = None, flat_output: bool = False,
                             progress_cb=None, should_stop=None):
    """Import a GitHub repo's main/master-branch ZIP that contains cheats in
    the .../{title_id}/cheats/{build_id}.txt layout (no release assets needed).

    Used for live repos like ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats or
    Arch9SK7/MyNXCheats, which are always current on their default branch.
    Returns (files_written, games).
    """
    import io
    import requests

    out = Path(output_dir)
    raw = None
    for branch in ("main", "master"):
        url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
        print(f"{label}: downloading {repo}@{branch}...")
        resp = requests.get(url, timeout=300)
        if resp.status_code == 200:
            raw = resp.content
            break
    if raw is None:
        raise RuntimeError(f"Could not download {repo} (no main/master branch zip).")
    print(f"Downloaded {round(len(raw) / 1e6, 1)} MB, extracting...")

    zf = zipfile.ZipFile(io.BytesIO(raw))
    pat = re.compile(r"/([0-9A-Fa-f]{16})/cheats/([0-9A-Fa-f]{16})\.txt$")
    entries = [n for n in zf.namelist() if pat.search(n)]
    total = len(entries)
    print(f"{total} cheat files with build ids in archive.")

    games = {}  # title_id -> list of (build_id, names)
    written = 0
    stubs = 0
    for i, name in enumerate(entries, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        m = pat.search(name)
        tid, bid = m.group(1).upper(), m.group(2).upper()
        content = zf.read(name).decode("utf-8", "replace")

        # Skip codeless stub files — see download_gbatemp_archive for why.
        names = parse_valid_cheats(content)
        if names:
            save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
            save_path = save_dir / f"{bid}.txt"
            if save_cheat_merged(save_path, content):
                written += 1
        else:
            stubs += 1

        games.setdefault(tid, []).append((bid, names))
        if progress_cb:
            progress_cb(i, total)
    if stubs:
        print(f"Skipped {stubs} codeless stub file(s) (no real code lines).")

    for tid, builds in games.items():
        sources = [{
            "build_id": bid, "title_id": tid, "source_id": None,
            "version": None, "upload_date": None,
            "cheat_count": len(names), "cheat_names": names,
            "credits": None, "description": None, "cheat_id": None,
        } for bid, names in builds]
        db.upsert_game({"title_id": tid, "title": None, "slug": None,
                        "image": None, "banner": None, "sources": sources},
                       source=source)
    print(f"Integrated {written} cheat file(s) for {len(games)} game(s).")
    return written, len(games)


CHANSEY_REPO = "ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats"
MYNX_REPO = "Arch9SK7/MyNXCheats"


def download_chansey_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                             flat_output: bool = False, progress_cb=None, should_stop=None):
    """Import the LIVE ChanseyIsTheBest/NX-60FPS-RES-GFX-Cheats repo
    (source='chansey-60fps') — the ORIGINAL source of the 60 FPS / resolution /
    graphics cheats (fresher than release snapshots that mirror it)."""
    return download_repo_cheats_zip(
        output_dir, db, repo=CHANSEY_REPO,
        source="chansey-60fps", label="Chansey 60FPS/Res/GFX",
        api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop)


def download_mynx_archive(output_dir, db: "GameDatabase", api: "CheatslipsAPI" = None,
                          flat_output: bool = False, progress_cb=None, should_stop=None):
    """Import the LIVE Arch9SK7/MyNXCheats repo (source='mynxcheats') — a
    curated collection for ~50 recent big titles (TotK, Scarlet/Violet, ...)."""
    return download_repo_cheats_zip(
        output_dir, db, repo=MYNX_REPO,
        source="mynxcheats", label="MyNXCheats",
        api=api, flat_output=flat_output,
        progress_cb=progress_cb, should_stop=should_stop)


IBNUX_ARCHIVE_URL = "https://github.com/ibnux/switch-cheat/archive/refs/heads/master.zip"


def download_ibnux_archive(output_dir, db: "GameDatabase", flat_output: bool = False,
                           api: "CheatslipsAPI" = None, progress_cb=None, should_stop=None):
    """Download the latest ibnux/switch-cheat archive and integrate it.

    Extracts cheat files from ``atmosphere/titles/{title_id}/cheats/{build_id}.txt``,
    writes them into our ``titles/{title_id}/cheats/{build_id}.txt`` schema,
    parses cheat names, adds rows to the database (source='ibnux') and fills
    game names from the bundled GAMES.md. If ``api`` is given, names/covers are
    also enriched from the CheatSlips API.
    Returns (files_written, games).
    """
    import io
    import requests

    out = Path(output_dir)
    print("Downloading ibnux/switch-cheat archive...")
    resp = requests.get(IBNUX_ARCHIVE_URL, timeout=180)
    resp.raise_for_status()
    raw = resp.content
    print(f"Downloaded {round(len(raw) / 1e6, 1)} MB, extracting...")

    zf = zipfile.ZipFile(io.BytesIO(raw))
    pat = re.compile(r"switch-cheat-master/atmosphere/titles/([0-9A-Fa-f]{16})/cheats/([0-9A-Fa-f]{16})\.txt$")
    entries = [n for n in zf.namelist() if pat.search(n)]
    total = len(entries)
    print(f"{total} cheat file(s) in archive.")

    games = {}
    written = 0
    stubs = 0
    for i, name in enumerate(entries, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        m = pat.search(name)
        tid, bid = m.group(1).upper(), m.group(2).upper()
        content = zf.read(name).decode("utf-8", "replace")

        # Skip codeless stub files — see download_gbatemp_archive for why.
        names = parse_valid_cheats(content)
        if names:
            save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
            save_path = save_dir / f"{bid}.txt"
            if save_cheat_merged(save_path, content):
                written += 1
        else:
            stubs += 1

        games.setdefault(tid, []).append((bid, names))
        if progress_cb:
            progress_cb(i, total)
    if stubs:
        print(f"Skipped {stubs} codeless stub file(s) (no real code lines).")

    # Write the DB entries (source = ibnux).
    for tid, builds in games.items():
        sources = [{
            "build_id": bid, "title_id": tid, "source_id": None,
            "version": None, "upload_date": None,
            "cheat_count": len(names), "cheat_names": names,
            "credits": None, "description": None, "cheat_id": None,
        } for bid, names in builds]
        db.upsert_game({"title_id": tid, "title": None, "slug": None,
                        "image": None, "banner": None, "sources": sources},
                       source="ibnux")
    print(f"Integrated {written} cheat file(s) for {len(games)} game(s).")

    # Fill game names from the bundled GAMES.md.
    games_md_text = None
    try:
        games_md_text = zf.read("switch-cheat-master/GAMES.md").decode("utf-8", "replace")
    except Exception as exc:
        print(f"GAMES.md from archive not readable: {exc}")
    if games_md_text:
        names_map = _parse_games_md_table(games_md_text)
        if names_map:
            print(f"GAMES.md from archive: {len(names_map)} name(s).")
            for tid, name in names_map.items():
                if should_stop and should_stop():
                    break
                db.update_game_fields(tid, {"game_title": name})

    # Optional API enrichment.
    if api is not None and games:
        print("Enriching imported games with names/covers/credits from the API...")
        tids = list(games.keys())
        for j, tid in enumerate(tids, 1):
            if should_stop and should_stop():
                break
            info = db.get_game_info(tid)
            if info:
                enrich_info_with_api(info, api)
                db.upsert_game(info)
            if progress_cb:
                progress_cb(j, len(tids))
        print("Enrichment done.")

    return written, len(games)


TITLEDB_CHEATS_URL = "https://raw.githubusercontent.com/blawar/titledb/master/cheats.json"


def download_titledb_cheats(output_dir, db: "GameDatabase", flat_output: bool = False,
                            progress_cb=None, should_stop=None):
    """Import titledb's own cheat database (cheats.json) as an extra source.

    Structure: {title_id: {build_id: {hash: {source, title}}}}. Each build is
    written as titles/{tid}/cheats/{bid}.txt and added to the DB (source='titledb').
    Returns (files_written, games).
    """
    import requests

    out = Path(output_dir)
    print("Downloading titledb cheats.json (~12 MB)...")
    data = requests.get(TITLEDB_CHEATS_URL, timeout=180).json()

    items = []
    for tid, builds in data.items():
        if not isinstance(builds, dict) or len(tid) != 16:
            continue
        for bid, cheats in builds.items():
            if isinstance(cheats, dict) and len(bid) == 16:
                items.append((tid.upper(), bid.upper(), cheats))
    total = len(items)
    print(f"{total} build(s) in titledb cheats.json.")

    written = 0
    games = set()
    for i, (tid, bid, cheats) in enumerate(items, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        parts, names = [], []
        for _h, c in cheats.items():
            if not isinstance(c, dict):
                continue
            title = (c.get("title") or "").strip()
            source = c.get("source") or ""
            parts.append(f"{title}\n{source}" if title else source)
            if title:
                m = re.match(r"^[\[{](.+?)[\]}]$", title)
                names.append(m.group(1).strip() if m else title.strip("[]{} "))
        content = ("\n\n".join(parts)).strip() + "\n"

        save_dir = out / "by_bid" if flat_output else out / "titles" / tid / "cheats"
        save_path = save_dir / f"{bid}.txt"
        if save_cheat_merged(save_path, content):
            written += 1
        games.add(tid)
        db.upsert_game({
            "title_id": tid, "title": None, "slug": None, "image": None, "banner": None,
            "sources": [{
                "build_id": bid, "title_id": tid, "source_id": None,
                "version": None, "upload_date": None,
                "cheat_count": len(names), "cheat_names": names,
                "credits": None, "description": None, "cheat_id": None,
            }],
        }, source="titledb")
        if progress_cb:
            progress_cb(i, total)

    print(f"Imported {written} build(s) for {len(games)} game(s) from titledb cheats.json.")
    return written, len(games)


TITLEDB_BUILDS_URL = "https://raw.githubusercontent.com/blawar/titledb/master/builds.json"
TITLEDB_VERSIONS_URL = "https://raw.githubusercontent.com/blawar/titledb/master/versions.json"


def version_int_to_str(version_int: int) -> str:
    """Nintendo version integer -> display string (0=1.0.0, 65536=1.1.0, ...)."""
    return f"1.{int(version_int) // 65536}.0"


def fill_versions_from_titledb(db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Fill missing versions (and per-version release dates) from titledb.

    builds.json maps an update title id to {versionInt: nso_build_id}. The first
    16 hex chars of that build id are the Atmosphere/cheat build id, so we can
    resolve build id -> version even for cheats not on cheatslips (e.g. GBAtemp).
    versions.json adds the release date per (title id, versionInt).
    """
    import requests

    print("Downloading titledb builds.json + versions.json...")
    data = requests.get(TITLEDB_BUILDS_URL, timeout=120).json()
    try:
        vdata = requests.get(TITLEDB_VERSIONS_URL, timeout=120).json()
    except Exception:
        vdata = {}
    # Lookup: cheat build id (first 16 hex, upper) -> (versionInt, update_title_id).
    lut = {}
    for upd, versions in data.items():
        for vint, h in (versions or {}).items():
            if h:
                lut[h[:16].upper()] = (int(vint), upd.upper())
    # versions.json is keyed by the BASE title id.
    vdates = {k.upper(): v for k, v in (vdata or {}).items()}
    print(f"titledb knows {len(lut)} build ids.")

    pairs = db.builds_missing_version()
    total = len(pairs)
    filled = 0
    print(f"Resolving versions for {total} build(s) via titledb...")
    for i, (tid, bid) in enumerate(pairs, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        hit = lut.get((bid or "").upper())
        if hit is not None:
            vint, _upd = hit
            # Release date: versions.json keyed by base title id (ends in 000).
            base = (tid or "").upper()
            date = (vdates.get(base) or {}).get(str(vint))
            filled += db.set_build_version(tid, bid, version=version_int_to_str(vint),
                                           version_date=date)
        if progress_cb:
            progress_cb(i, total)
    print(f"titledb filled {filled} version(s).")
    return filled


TITLEDB_REGION_URL = "https://raw.githubusercontent.com/blawar/titledb/master/{region}.json"

# Regions tried in order when filling missing game names. The files are cached
# locally for 7 days, so subsequent runs are instant. Only filenames that
# actually exist in blawar/titledb are listed (e.g. EU.en / ZH.zh do NOT exist).
TITLEDB_REGIONS = ["US.en", "GB.en", "AU.en", "JP.ja", "KR.ko", "HK.zh"]

# Short display label per titledb region file, used for the "Region" column.
TITLEDB_REGION_LABELS = {
    "US.en": "US", "GB.en": "EU", "AU.en": "AU",
    "JP.ja": "JP", "KR.ko": "KR", "HK.zh": "HK",
}

# switchbrew's "Region" column uses 3-letter codes; map them to our labels.
_SWITCHBREW_REGION_MAP = {
    "USA": "US", "EUR": "EU", "JPN": "JP", "KOR": "KR", "CHN": "CN",
}


def _switchbrew_region_map(cache_dir: str = ".") -> Dict[str, str]:
    """Return {title_id -> region_str} from switchbrew's Title list/Games table.

    switchbrew lists a Region column (e.g. "EUR USA", "JPN") that the titledb
    eShop dumps do not cover for some (older / delisted / regional) titles. We
    reuse the same cached wikitext downloaded for name-filling; if it is missing
    we do NOT trigger a download here (the name step handles that).
    """
    import re
    cache = Path(cache_dir) / "switchbrew_games.txt"
    if not cache.exists():
        return {}
    try:
        text = cache.read_text(encoding="utf-8")
    except Exception:
        return {}
    out: Dict[str, str] = {}
    # row:  | <16-hex ProgramId> || <name> || <Region> || ...
    row_re = re.compile(
        r"^\|\s*([0-9A-Fa-f]{16})\s*\|\|\s*([^|]*?)\s*\|\|\s*([^|]*?)\s*\|\|",
        re.MULTILINE)
    for m in row_re.finditer(text):
        tid = m.group(1).upper()
        raw = (m.group(3) or "").strip()
        if not raw or tid in out:
            continue
        labels = []
        for tok in raw.replace(",", " ").split():
            lab = _SWITCHBREW_REGION_MAP.get(tok.upper())
            if lab and lab not in labels:
                labels.append(lab)
        if labels:
            out[tid] = "/".join(sorted(labels))
    return out


def _region_from_name(name: Optional[str]) -> Optional[str]:
    """Guess a region from a title's script when no data source lists it.

    Japanese kana (hiragana/katakana) are unambiguously JP. CJK ideographs with
    no kana are treated as Chinese (CN) — the only Chinese-script titles in the
    dataset are Tencent/iQue SKUs. Latin/other scripts return None (unknown).
    """
    if not name:
        return None
    has_kana = has_han = False
    for ch in name:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:      # hiragana + katakana
            has_kana = True
            break
        if 0x4E00 <= o <= 0x9FFF:      # CJK unified ideographs
            has_han = True
    if has_kana:
        return "JP"
    if has_han:
        return "CN"
    return None


def fill_regions_from_titledb(db: "GameDatabase", regions: Optional[List[str]] = None,
                              cache_dir: str = ".", progress_cb=None, should_stop=None) -> int:
    """Tag every known title id with the eShop region(s) it appears in.

    Unlike fill_metadata_from_titledb (which only fills names/covers still
    missing), this checks ALL title ids already in the database against every
    titledb regional dump, even if the name/cover were already filled from
    another source (e.g. cheatslips itself). Region files are the same ones
    used for name-filling and reuse the same 7-day local cache.
    """
    import json
    import requests

    if regions is None:
        regions = TITLEDB_REGIONS

    all_tids = db._apply_restrict([t.upper() for t in db.all_title_ids()])
    if not all_tids:
        return 0
    all_tids_set = set(all_tids)

    found: Dict[str, List[str]] = {}
    total = len(regions)
    for i, region in enumerate(regions, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        cache = Path(cache_dir) / f"titledb_{region}.json"
        data = None
        if cache.exists() and (time.time() - cache.stat().st_mtime < 7 * 86400):
            print(f"Using cached {cache.name}")
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                data = None
        if data is None:
            print(f"Downloading titledb {region}.json (~80 MB, cached afterwards)...")
            try:
                resp = requests.get(TITLEDB_REGION_URL.format(region=region), timeout=300)
            except Exception as exc:
                print(f"  {region} download failed ({exc}) - skipping.")
                if progress_cb:
                    progress_cb(i, total)
                continue
            if resp.status_code != 200:
                print(f"titledb {region}.json not available (HTTP {resp.status_code}) - skipping.")
                if progress_cb:
                    progress_cb(i, total)
                continue
            try:
                data = json.loads(resp.content.decode("utf-8", "replace"))
            except Exception as exc:
                print(f"titledb {region}.json is not valid JSON ({exc}) - skipping.")
                if progress_cb:
                    progress_cb(i, total)
                continue
            try:
                cache.write_bytes(resp.content)
            except Exception:
                pass

        label = TITLEDB_REGION_LABELS.get(region, region)
        for entry in data.values():
            if isinstance(entry, dict):
                tid = (entry.get("id") or "").upper()
                if tid in all_tids_set:
                    found.setdefault(tid, []).append(label)
        if progress_cb:
            progress_cb(i, total)

    tagged = 0
    for tid, labels in found.items():
        region_str = "/".join(sorted(set(labels)))
        if db.update_game_fields(tid, {"region": region_str}):
            tagged += 1

    # Propagate the region from base games (…000) to DLC/update title ids that
    # titledb does not list itself (e.g. "… [DLC 003]" or update …800 entries).
    # update_game_fields only fills a region that is still empty.
    base_regions = {}
    for r in db._conn.execute(
        "SELECT title_id, region FROM builds "
        "WHERE region IS NOT NULL AND region != '' AND title_id LIKE '%000'"
    ).fetchall():
        base_regions[(r[0] or "").upper()] = r[1]
    derived = 0
    for tid in all_tids:
        if tid.endswith("000") or tid in found:
            continue
        breg = base_regions.get(tid[:-3] + "000")
        if breg and db.update_game_fields(tid, {"region": breg}):
            derived += 1
    if derived:
        print(f"Derived region from base game for {derived} DLC/update title(s).")

    # --- Fallbacks for titles no titledb region file lists (JP/CN/Asian retail
    # SKUs, homebrew ports, delisted titles). update_game_fields only fills a
    # region that is still empty, so these never override real titledb data. ---
    still_missing = [
        (r[0] or "").upper() for r in db._conn.execute(
            "SELECT DISTINCT title_id FROM builds "
            "WHERE (region IS NULL OR region = '') AND length(title_id) = 16"
        ).fetchall()
        if not db._restricted(r[0])
    ]
    sb_regions = _switchbrew_region_map(cache_dir)
    sb_filled = hb_filled = script_filled = 0
    # Fetch names once for the script heuristic.
    names = {}
    for r in db._conn.execute(
        "SELECT DISTINCT title_id, game_title FROM builds WHERE length(title_id) = 16"
    ).fetchall():
        names[(r[0] or "").upper()] = r[1]
    for tid in still_missing:
        # 1) switchbrew Region column.
        sbr = sb_regions.get(tid)
        if sbr and db.update_game_fields(tid, {"region": sbr}):
            sb_filled += 1
            continue
        # 2) Homebrew: dedicated title-id range (05…) or a name saying so.
        nm = names.get(tid) or ""
        if (tid.startswith("05") or "homebrew" in nm.lower()) and \
                db.update_game_fields(tid, {"region": "Homebrew"}):
            hb_filled += 1
            continue
        # 3) CJK script heuristic on the game name.
        guess = _region_from_name(names.get(tid))
        if guess and db.update_game_fields(tid, {"region": guess}):
            script_filled += 1
    fallback = sb_filled + hb_filled + script_filled
    if fallback:
        print(f"Fallback regions: switchbrew {sb_filled}, homebrew {hb_filled}, "
              f"script heuristic {script_filled}.")
    print(f"Tagged region for {tagged} title id(s).")
    return tagged + derived + fallback


def fill_descriptions_from_titledb(db: "GameDatabase", regions: Optional[List[str]] = None,
                                   cache_dir: str = ".", progress_cb=None, should_stop=None) -> int:
    """Fill missing game descriptions (+ intro tagline) for every title from the
    titledb region files (English regions by default). Uses the local 7-day cache
    and downloads a region file only if it is missing/stale. Returns the number of
    titles filled.
    """
    import json
    import requests

    if regions is None:
        regions = ["US.en", "GB.en", "AU.en"]

    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_description IS NULL OR game_description = '') "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    todo = {(r[0] or "").upper() for r in rows if not db._restricted(r[0])}
    if not todo:
        print("All titles already have a description.")
        return 0
    print(f"Filling descriptions for {len(todo)} title(s) from titledb...")

    index = {}
    for i, region in enumerate(regions, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        cache = Path(cache_dir) / f"titledb_{region}.json"
        data = None
        if cache.exists() and (time.time() - cache.stat().st_mtime < 7 * 86400):
            print(f"Using cached {cache.name}")
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                data = None
        if data is None:
            print(f"Downloading titledb {region}.json (~80 MB, cached afterwards)...")
            try:
                resp = requests.get(TITLEDB_REGION_URL.format(region=region), timeout=300)
            except Exception as exc:
                print(f"  {region} download failed ({exc}) — skipping.")
                if progress_cb:
                    progress_cb(i, len(regions))
                continue
            if resp.status_code != 200:
                print(f"titledb {region}.json not available (HTTP {resp.status_code}) — skipping.")
                if progress_cb:
                    progress_cb(i, len(regions))
                continue
            try:
                data = json.loads(resp.content.decode("utf-8", "replace"))
            except Exception as exc:
                print(f"titledb {region}.json is not valid JSON ({exc}) — skipping.")
                if progress_cb:
                    progress_cb(i, len(regions))
                continue
            try:
                cache.write_bytes(resp.content)
            except Exception:
                pass
        for e in data.values():
            if not isinstance(e, dict):
                continue
            tid = (e.get("id") or "").upper()
            if tid in todo and tid not in index:
                desc = (e.get("description") or "").strip()
                intro = (e.get("intro") or "").strip()
                if desc or intro:
                    index[tid] = (desc, intro)
        if progress_cb:
            progress_cb(i, len(regions))

    filled = 0
    for tid, (desc, intro) in index.items():
        if should_stop and should_stop():
            break
        fields = {}
        if desc:
            fields["game_description"] = desc
        if intro:
            fields["intro"] = intro
        if fields and db.update_game_fields(tid, fields):
            filled += 1
    print(f"Filled descriptions for {filled} title(s).")
    return filled


def fill_metadata_from_titledb(db: "GameDatabase", region: str = "US.en",
                               cache_dir=".", progress_cb=None, should_stop=None) -> int:
    """Fill missing game names + cover images from titledb's regional eShop data.

    Used after importing the GBAtemp archive: those titles have no names/covers,
    and many are not on cheatslips. titledb's region file maps title id -> name,
    iconUrl (cover) and bannerUrl. The ~80 MB file is cached locally and reused
    for 7 days. Returns the number of games filled.
    """
    import json
    import requests

    cache = Path(cache_dir) / f"titledb_{region}.json"
    data = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < 7 * 86400):
        print(f"Using cached {cache.name}")
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            print(f"Cached {cache.name} is corrupt - re-downloading...")
            data = None
    if data is None:
        print(f"Downloading titledb {region}.json (~80 MB, cached afterwards)...")
        resp = requests.get(TITLEDB_REGION_URL.format(region=region), timeout=300)
        if resp.status_code != 200:
            print(f"titledb {region}.json not available (HTTP {resp.status_code}) - skipping region.")
            return 0
        try:
            data = json.loads(resp.content.decode("utf-8", "replace"))
        except Exception as exc:
            print(f"titledb {region}.json is not valid JSON ({exc}) - skipping region.")
            return 0
        # Only cache once we know the payload parsed correctly.
        try:
            cache.write_bytes(resp.content)
        except Exception:
            pass

    by_tid = {}
    for entry in data.values():
        if isinstance(entry, dict):
            tid = (entry.get("id") or "").upper()
            if tid:
                by_tid[tid] = entry
    print(f"titledb has metadata for {len(by_tid)} titles.")

    tids = db.title_ids_missing_meta()
    total = len(tids)
    filled = 0
    print(f"Filling names/covers for {total} game(s)...")
    for i, tid in enumerate(tids, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        e = by_tid.get(tid.upper())
        if e and (e.get("name") or e.get("iconUrl")):
            cat = e.get("category")
            if isinstance(cat, list):
                cat = ", ".join(cat)
            langs = e.get("languages")
            if isinstance(langs, list):
                langs = ", ".join(langs) if langs else None
            rc = e.get("ratingContent")
            if isinstance(rc, list):
                rc = ", ".join(rc) if rc else None
            shots = e.get("screenshots")
            shots = json.dumps(shots, ensure_ascii=False) if isinstance(shots, list) and shots else None
            db.update_game_fields(tid, {
                "game_title": e.get("name"),
                "image": e.get("iconUrl"),
                "banner": e.get("bannerUrl"),
                "publisher": e.get("publisher"),
                "developer": e.get("developer"),
                "category": cat,
                "game_description": e.get("description"),
                "release_date": str(e.get("releaseDate")) if e.get("releaseDate") else None,
                "players": str(e.get("numberOfPlayers")) if e.get("numberOfPlayers") else None,
                "size_bytes": str(e.get("size")) if e.get("size") else None,
                "rating": str(e.get("rating")) if e.get("rating") is not None else None,
                # Extended titledb metadata:
                "screenshots": shots,
                "languages": langs,
                "nsu_id": str(e.get("nsuId")) if e.get("nsuId") else None,
                "intro": e.get("intro"),
                "rating_content": rc,
                "is_demo": "1" if e.get("isDemo") else None,
            })
            filled += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"Filled names/covers for {filled} game(s).")
    return filled


SWITCHBREW_GAMES_URL = "https://switchbrew.org/w/index.php?title=Title_list/Games&action=raw"


def fill_metadata_from_switchbrew(db: "GameDatabase", cache_dir: str = ".",
                                  progress_cb=None, should_stop=None) -> int:
    """Fill missing game names from the switchbrew.org "Title list/Games" wiki.

    switchbrew maintains a curated MediaWiki table mapping ProgramId -> game
    name. It covers some (mostly older / regional / delisted) titles that the
    titledb eShop dumps miss. We download the raw wikitext (cached 7 days),
    parse the table and fill names for any title id still missing one. No cover
    images are available from this source. Returns the number of games filled.
    """
    import re
    import requests

    cache = Path(cache_dir) / "switchbrew_games.txt"
    text = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < 7 * 86400):
        print(f"Using cached {cache.name}")
        try:
            text = cache.read_text(encoding="utf-8")
        except Exception:
            text = None
    if text is None:
        print("Downloading switchbrew Title list/Games...")
        try:
            resp = requests.get(SWITCHBREW_GAMES_URL, timeout=120,
                                headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            print(f"switchbrew download failed ({exc}) - skipping.")
            return 0
        if resp.status_code != 200:
            print(f"switchbrew not available (HTTP {resp.status_code}) - skipping.")
            return 0
        text = resp.text
        try:
            cache.write_text(text, encoding="utf-8")
        except Exception:
            pass

    # Parse rows of the form:  | <16-hex ProgramId> || <Description> || <Region> || ...
    by_tid = {}
    row_re = re.compile(r"^\|\s*([0-9A-Fa-f]{16})\s*\|\|\s*([^|]+?)\s*\|\|", re.MULTILINE)
    for m in row_re.finditer(text):
        tid = m.group(1).upper()
        name = m.group(2).strip()
        if name and tid not in by_tid:
            by_tid[tid] = name
    print(f"switchbrew has names for {len(by_tid)} titles.")

    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id)) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    rows = [r for r in rows if not db._restricted(r[0])]
    total = len(rows)
    filled = 0
    for i, row in enumerate(rows, 1):
        if should_stop and should_stop():
            break
        tid = row[0]
        name = by_tid.get(tid.upper())
        if name:
            db.update_game_fields(tid, {"game_title": name})
            filled += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"switchbrew filled {filled} game name(s).")
    return filled


def derive_names_from_base(db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Let DLC/update title ids inherit a name + cover from their base game.

    Many add-on/update title ids (suffix 001/002/.../800) are never listed in
    titledb, but their base application (…000) usually is. For each still-unnamed
    16-char title id we look up the base id and copy its name/cover, tagging the
    suffix so the row stays identifiable (e.g. "Mario [DLC 002]").
    Returns the number of titles enriched.
    """
    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id)) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    rows = [r for r in rows if not db._restricted(r[0])]
    total = len(rows)
    derived = 0
    for i, row in enumerate(rows, 1):
        if should_stop and should_stop():
            break
        tid = row[0]
        base = tid[:-3] + "000"
        if base.upper() != tid.upper():
            base_info = db._conn.execute(
                "SELECT game_title, image, banner, publisher, developer, "
                "category, game_description, release_date "
                "FROM builds WHERE title_id = ? AND game_title IS NOT NULL "
                "AND game_title != '' LIMIT 1", (base,)
            ).fetchone()
            if base_info:
                suffix = tid[-3:].upper()
                label = f"{base_info[0]} [DLC {suffix}]"
                db.update_game_fields(tid, {
                    "game_title": label,
                    "image": base_info[1],
                    "banner": base_info[2],
                    "publisher": base_info[3],
                    "developer": base_info[4],
                    "category": base_info[5],
                    "game_description": base_info[6],
                    "release_date": base_info[7],
                })
                derived += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"Derived names for {derived} DLC/update title(s) from base games.")
    return derived


TINFOIL_TITLE_URL = "https://tinfoil.io/Title/{title_id}"
SWITCH_CHEAT_GAMES_MD_URL = "https://raw.githubusercontent.com/ibnux/switch-cheat/master/GAMES.md"
NX_GFX_README_MD_URL = "https://raw.githubusercontent.com/ADEMOLA200/Switch-Emulator-Mod-Database/develop/README.md"

# Title IDs that are not listed on any scraper site but are known to the community.
# Used as a final fallback when every online source fails to provide a name.
KNOWN_TITLE_NAMES: Dict[str, str] = {
    "05450B00BA020000": "AM2R - Another Metroid 2 Remake",
    "0100A6D0223CC000": "Guilty Gear -Strive- Nintendo Switch Edition",
    "0100CDC01E300000": "Potion Permit",
    "01001FD01856A000": "GUNDAM BATTLE ALLIANCE (HK) Demo",
    "05BE1C0259DE0000": "Grand Theft Auto: Vice City Native Port",
    "01009120119B4002": "Deathsmiles I・II (Update)",
    "054507E0B7552000": "Super Mario 64 Port",
    "0100195015AC6001": "Prinny 1•2: Exploded and Reloaded Update",
    "0100BBA015E8E001": "Klonoa Phantasy Reverie Series Update",
    "0100AA00128BA001": "Saviors of Sapphire Wings & Stranger of Sword City Revisited Update",
    "01009120119B4001": "Deathsmiles I・II Update",
    "010040F011DE4001": "Devious Dungeon Collection",
    "01001FA01451C002": "Prinny Presents NIS Classics Volume 1: Phantom Brave / Soul Nomad & the World Eaters Update",
    "010040F011DE4002": "Devious Dungeon Collection Update",
    "0100414D32524E00": "AM2R - Another Metroid 2 Remake (Homebrew Port)",
    "01001FA01451C001": "Prinny Presents NIS Classics Volume 1: Phantom Brave / Soul Nomad & the World Eaters Update (older)",
    "010072400E06A000": "Asdivine Kamura",
}

# Title ids where every online source (cheatslips, titledb, tinfoil, ...) reports a
# wrong or misleading game name. Unlike KNOWN_TITLE_NAMES (which only fills empty
# names), these forcibly overwrite whatever name was scraped, and upsert_build()
# re-applies them on every write so a later re-scrape can't bring the wrong name back.
TITLE_NAME_OVERRIDES: Dict[str, str] = {
    "010092302342A000": "Pokémon FireRed (Italian Version)",
    "0100554023408000": "Pokémon FireRed (English Version)",
    "010034D02340E000": "Pokémon Leaf Green (English Version)",
    "0100386014952000": "Perky Little Things (Uncensored Cartridge Version)",
}

# Build IDs that are known to belong to a specific title id even when the file is
# not stored under the titles/ directory structure (e.g. by_bid/ dumps).
KNOWN_BUILD_IDS: Dict[str, str] = {
    "D0D456EE7DCF0FEE": "0100CDC01E300000",
}


_PLACEHOLDER_BUILD_IDS = {
    "0000000000000000",
    "0000000000000001",
    "1111111111111111",
    "FFFFFFFF",
}


def title_id_kind(title_id: Optional[str]) -> str:
    """Heuristically classify a Switch title id by its last 3 hex digits.

    - ``base``    -> ``…000`` : the application id. Atmosphère files cheats under
      this id, so cheats are only recognised on the console for base ids.
    - ``update``  -> ``…800`` : patch / update title id.
    - ``dlc``     -> anything else : add-on content / variant.
    - ``invalid`` -> not a 16-hex value.

    Update/DLC ids generally need adjusting to their base id for the cheats to
    work on the console. The matching base id is ``title_id[:-3] + '000'``.
    """
    if not title_id:
        return "invalid"
    tid = title_id.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{16}", tid):
        return "invalid"
    suffix = tid[-3:]
    if suffix == "000":
        return "base"
    if suffix == "800":
        return "update"
    return "dlc"


def base_title_id(title_id: Optional[str]) -> Optional[str]:
    """Return the simple base (…000) application id for any title id (or None).

    This is the quick heuristic (just zero the last 3 hex digits). It is exact
    for updates (…800 -> …000); for DLC it is only a *candidate* — use
    candidate_base_title_ids()/resolve_base_title_id() when correctness matters.
    """
    if not title_id:
        return None
    tid = title_id.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{16}", tid):
        return None
    return tid[:-3] + "000"


def candidate_base_title_ids(title_id: Optional[str]) -> List[str]:
    """All plausible base application ids for an update/DLC title id, best guess first.

    Nintendo's conventions:
      - update (patch): base = id with the 0x800 bit cleared  (reliable)
      - DLC (AddOnContent): standard base = (id & ~0xFFF) - 0x1000
    Some cheat sources, however, just append a small index to the base
    (e.g. …546000 -> …546003), so the plain "zero the last 3 digits" candidate is
    tried as well. Returned list is de-duplicated, order = most likely first.
    """
    tid = (title_id or "").strip().upper()
    if not re.fullmatch(r"[0-9A-F]{16}", tid):
        return []
    kind = title_id_kind(tid)
    if kind == "base":
        return [tid]
    n = int(tid, 16)
    cands = []
    if kind == "update":
        cands.append(f"{n & ~0x800:016X}")            # strip patch bit -> …000
    else:  # dlc / add-on / variant
        cands.append(tid[:-3] + "000")                # simple strip (cheat-source style)
        cands.append(f"{(n & ~0xFFF) - 0x1000:016X}")  # standard AddOnContent base
    out, seen = [], set()
    for c in cands:
        if re.fullmatch(r"[0-9A-F]{16}", c) and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_base_title_id(db: "GameDatabase", title_id: Optional[str]):
    """Resolve the correct base id for an update/DLC id, verified against the DB.

    Returns (base_id, confident):
      - base id itself              -> (id, True)
      - update id                   -> (base, True)   # deterministic
      - DLC id whose candidate base exists in the DB -> (that base, True)
      - DLC id, no candidate in DB  -> (best guess, False)
      - invalid                     -> (None, False)
    """
    cands = candidate_base_title_ids(title_id)
    if not cands:
        return (None, False)
    kind = title_id_kind(title_id)
    if kind == "base":
        return (cands[0], True)
    if kind == "update":
        return (cands[0], True)
    for c in cands:
        row = db._conn.execute(
            "SELECT 1 FROM builds WHERE title_id = ? LIMIT 1", (c,)
        ).fetchone()
        if row:
            return (c, True)
    return (cands[0], False)


def is_placeholder_build_id(build_id: str, title_id: str = None) -> bool:
    """Return True if a build id is a placeholder that should not be stored.

    Placeholders are all-zero, all-one, all-F, or equal to the title id.
    """
    if not build_id:
        return True
    bid = build_id.strip().upper()
    if not bid:
        return True
    if bid in _PLACEHOLDER_BUILD_IDS:
        return True
    # Some imports store the title id as the build id by mistake.
    if title_id and bid == title_id.upper().strip():
        return True
    return False


# Specific (title id, build id) pairs known to be bad data (e.g. bogus entries
# picked up from a scrape source) that must never be stored or shown again.
BLOCKED_BUILD_PAIRS = {
    ("01000698009C6E00", "70C806F458D36843"),
    ("207231A04B2F3744", "250CE7C4A4DE1940"),
}


def is_blocked_pair(title_id: Optional[str], build_id: Optional[str]) -> bool:
    """Return True for a (title id, build id) pair we must never store or show."""
    if not title_id or not build_id:
        return False
    t, b = title_id.strip().upper(), build_id.strip().upper()
    # A build id equal to the title id is a cheatslips placeholder / mis-upload
    # (real Switch build ids are derived from the executable and never match the
    # title id). These otherwise reappear on every scrape, so block them outright.
    if t == b:
        return True
    return (t, b) in BLOCKED_BUILD_PAIRS


def _markdown_link_text(text: str) -> Optional[str]:
    """Extract the visible text from a markdown link like [Text](url)."""
    m = re.match(r"\[([^\]]+)\]\([^)]+\)", text.strip())
    if m:
        return m.group(1).strip()
    return None


def _parse_games_md_table(text: str) -> Dict[str, str]:
    """Parse the GAMES.md markdown table and return title_id -> name mappings.

    The table has columns: No | NAME | TITLE ID | BUILD ID. The title id is a
    markdown link like `[0100...0000](https://...)`.
    """
    by_tid: Dict[str, str] = {}
    # Match a table row: | number | name | [title_id](url) | build_id |
    # We allow the name to contain `|` only inside balanced brackets, which is
    # enough for the GAMES.md format.
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*\[([0-9A-Fa-f]{16})\]\([^)]+\)\s*\|\s*[^|]*\|\s*$",
        re.MULTILINE,
    )
    for m in row_re.finditer(text):
        name = m.group(1).strip()
        tid = m.group(2).upper()
        # Skip entries where the name is just the raw title id (common in GAMES.md for
        # titles nobody has named yet). Keeping those would overwrite real names with ids.
        if name and tid and name.upper() != tid and tid not in by_tid:
            by_tid[tid] = name
    return by_tid


def fetch_games_md_title_ids(cache_dir=".", cache_days: int = 7) -> List[str]:
    """Download and cache GAMES.md, returning the list of title ids in the table.

    This includes title ids whose name is just the id itself, so it can be used to
    import missing title ids into the database.
    """
    import requests

    cache = Path(cache_dir) / "games.md"
    text = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < cache_days * 86400):
        print(f"Using cached {cache.name}")
        try:
            text = cache.read_text(encoding="utf-8")
        except Exception:
            text = None
    if text is None:
        print("Downloading ibnux/switch-cheat GAMES.md...")
        try:
            resp = requests.get(SWITCH_CHEAT_GAMES_MD_URL, timeout=120,
                                headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            print(f"GAMES.md download failed ({exc}) - skipping.")
            return []
        if resp.status_code != 200:
            print(f"GAMES.md not available (HTTP {resp.status_code}) - skipping.")
            return []
        text = resp.text
        try:
            cache.write_text(text, encoding="utf-8")
        except Exception:
            pass

    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*\[([0-9A-Fa-f]{16})\]\([^)]+\)\s*\|\s*[^|]*\|\s*$",
        re.MULTILINE,
    )
    tids = []
    for m in row_re.finditer(text):
        tid = m.group(2).upper()
        if tid and tid not in tids:
            tids.append(tid)
    return tids


def _parse_games_md_entries(text: str) -> List[Tuple[str, List[str]]]:
    """Parse GAMES.md and return (title_id, [build_ids]) for each table row."""
    row_re = re.compile(
        r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*\[([0-9A-Fa-f]{16})\]\([^)]+\)\s*\|\s*([^|]*)\|\s*$",
        re.MULTILINE,
    )
    entries = []
    for m in row_re.finditer(text):
        tid = m.group(2).upper()
        raw_bids = m.group(3).strip()
        bids = [b.strip().upper() for b in raw_bids.split(",") if b.strip()]
        entries.append((tid, bids))
    return entries


def import_missing_title_ids_from_games_md(db: "GameDatabase", cache_dir=".",
                                            progress_cb=None, should_stop=None) -> int:
    """Import title ids from GAMES.md that are not yet in the database.

    Only creates rows when GAMES.md lists at least one real build id for the title.
    Placeholder-only entries (0000...0000, 0000...0001, title_id itself) are skipped.
    Returns the number of imported rows.
    """
    import requests

    cache = Path(cache_dir) / "games.md"
    text = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < 7 * 86400):
        print(f"Using cached {cache.name}")
        try:
            text = cache.read_text(encoding="utf-8")
        except Exception:
            text = None
    if text is None:
        print("Downloading ibnux/switch-cheat GAMES.md...")
        try:
            resp = requests.get(SWITCH_CHEAT_GAMES_MD_URL, timeout=120,
                                headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            print(f"GAMES.md download failed ({exc}) - skipping.")
            return 0
        if resp.status_code != 200:
            print(f"GAMES.md not available (HTTP {resp.status_code}) - skipping.")
            return 0
        text = resp.text
        try:
            cache.write_text(text, encoding="utf-8")
        except Exception:
            pass

    entries = _parse_games_md_entries(text)
    if not entries:
        print("GAMES.md: no title ids parsed.")
        return 0

    existing = set()
    for row in db._conn.execute(
        "SELECT DISTINCT title_id FROM builds WHERE title_id IS NOT NULL"
    ).fetchall():
        existing.add((row[0] or "").upper())

    now = datetime.datetime.now().isoformat(timespec="seconds")
    imported = 0
    to_import = []
    for tid, bids in entries:
        if tid in existing:
            continue
        real_bids = [b for b in bids if not is_placeholder_build_id(b, tid)]
        if not real_bids:
            continue
        to_import.append((tid, real_bids[0]))

    if not to_import:
        print("GAMES.md: all importable title ids already in the database.")
        return 0

    print(f"GAMES.md: importing {len(to_import)} new title id(s) with real build ids...")
    for i, (tid, bid) in enumerate(to_import, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        with db._conn:
            db._conn.execute(
                """INSERT INTO builds
                    (build_id, title_id, slug, game_title, last_updated, source)
                   VALUES (?, ?, ?, ?, ?, 'gamesmd')
                   ON CONFLICT(build_id, title_id) DO NOTHING""",
                (bid, tid, None, None, now),
            )
        imported += 1
        if progress_cb:
            progress_cb(i, len(to_import))
    print(f"GAMES.md imported {imported} new title id(s) with real build ids.")
    return imported


def fetch_games_md_names(cache_dir=".", cache_days: int = 7) -> Dict[str, str]:
    """Download and cache GAMES.md, returning title_id -> name mappings."""
    import requests

    cache = Path(cache_dir) / "games.md"
    text = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < cache_days * 86400):
        print(f"Using cached {cache.name}")
        try:
            text = cache.read_text(encoding="utf-8")
        except Exception:
            text = None
    if text is None:
        print("Downloading ibnux/switch-cheat GAMES.md...")
        try:
            resp = requests.get(SWITCH_CHEAT_GAMES_MD_URL, timeout=120,
                                headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            print(f"GAMES.md download failed ({exc}) - skipping.")
            return {}
        if resp.status_code != 200:
            print(f"GAMES.md not available (HTTP {resp.status_code}) - skipping.")
            return {}
        text = resp.text
        try:
            cache.write_text(text, encoding="utf-8")
        except Exception:
            pass
    return _parse_games_md_table(text)


def _parse_nx_gfx_readme_table(text: str) -> Dict[str, str]:
    """Parse the ADEMOLA200/Switch-Emulator-Mod-Database README.md table.

    The table has columns: NAME | TITLE ID | BUILD ID | VERSION | CHEAT TYPES | LATEST STATUS.
    The name and title id are both markdown links. We split by `|` and take the first two
    columns as name and title id.
    """
    by_tid: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        # Skip lines that are clearly not data rows (e.g. the separator line is `| --- | ...`).
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        name = _markdown_link_text(parts[0])
        tid = _markdown_link_text(parts[1])
        if tid and re.fullmatch(r"[0-9A-Fa-f]{16}", tid):
            name = (name or "").strip()
            if name and tid.upper() not in by_tid:
                by_tid[tid.upper()] = name
    return by_tid


def fetch_nx_gfx_readme_names(cache_dir=".", cache_days: int = 7) -> Dict[str, str]:
    """Download and cache the ADEMOLA200 README.md, returning title_id -> name mappings."""
    import requests

    cache = Path(cache_dir) / "nx_gfx_readme.md"
    text = None
    if cache.exists() and (time.time() - cache.stat().st_mtime < cache_days * 86400):
        print(f"Using cached {cache.name}")
        try:
            text = cache.read_text(encoding="utf-8")
        except Exception:
            text = None
    if text is None:
        print("Downloading ADEMOLA200/Switch-Emulator-Mod-Database README.md...")
        try:
            resp = requests.get(NX_GFX_README_MD_URL, timeout=120,
                                headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            print(f"NX GFX README.md download failed ({exc}) - skipping.")
            return {}
        if resp.status_code != 200:
            print(f"NX GFX README.md not available (HTTP {resp.status_code}) - skipping.")
            return {}
        text = resp.text
        try:
            cache.write_text(text, encoding="utf-8")
        except Exception:
            pass
    return _parse_nx_gfx_readme_table(text)


def apply_buildid_map(db: "GameDatabase", overwrite: bool = True) -> int:
    """Fuellt version + game_title vorhandener Builds aus der lokalen Ergaenzungs-
    DB (build_id -> version/name). Eine Build-ID entspricht eindeutig genau einer
    Version, und unsere Werte stammen aus der echten installierten Datei - daher
    wird die Version standardmaessig AUTORITATIV gesetzt (overwrite=True). Der
    Name wird nur gefuellt, wenn noch keiner/ein Platzhalter da ist.
    Rueckgabe: Anzahl tatsaechlich geaenderter Zeilen."""
    m = getattr(db, "_buildid_map", None)
    if not m:
        return 0
    changed = 0
    with db._conn:
        for bid, rec in m.items():
            tid = rec.get("title_id") or ""
            if not tid:
                continue  # ohne Title-ID nicht zuordenbar (Kollisionsschutz)
            ver = rec.get("version") or None
            name = rec.get("name") or None
            if not ver and not name:
                continue
            # Nur selbst-extrahierte/manuelle Eintraege duerfen ueberschreiben;
            # aus der DB archivierte ("db") fuellen nur Leeres (Fallback/Archiv).
            ov = overwrite and rec.get("source", "extracted") in ("extracted", "manual")
            vcond = ("version IS NULL OR version = '' OR version != ?"
                     if ov else "version IS NULL OR version = ''")
            # Gibt es die exakte (build_id + title_id)-Zeile? Wenn ja, strikt
            # dort schreiben: eine falsch zugeordnete Build-ID (Datenfehler,
            # fremder Titel) hat dann den richtigen Titel daneben und wird nur
            # DORT getroffen - der fremde bleibt unberuehrt.
            exact = db._conn.execute(
                "SELECT 1 FROM builds WHERE build_id = ? AND title_id = ? LIMIT 1",
                (bid, tid)).fetchone()
            if exact:
                if ver:
                    cur = db._conn.execute(
                        f"UPDATE builds SET version = ? WHERE build_id = ? AND title_id = ? AND ({vcond})",
                        (ver, bid, tid, ver) if ov else (ver, bid, tid))
                    changed += cur.rowcount
                if name:
                    cur = db._conn.execute(
                        "UPDATE builds SET game_title = ? WHERE build_id = ? AND title_id = ? AND "
                        "(game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id))",
                        (name, bid, tid))
                    changed += cur.rowcount
            elif ver:
                # Editions-Fallback: dieselbe Build-ID kommt in der DB NUR unter
                # anderen Title-IDs vor (verschiedene Editionen/Regionen desselben
                # Spiels - identische Binary => identische Version). Nur Version
                # setzen (der Name kann editionsspezifisch sein).
                cur = db._conn.execute(
                    f"UPDATE builds SET version = ? WHERE build_id = ? AND ({vcond})",
                    (ver, bid, ver) if ov else (ver, bid))
                changed += cur.rowcount
    return changed


def sync_buildid_map_from_db(db: "GameDatabase") -> int:
    """Archiviert Versionen aus cheats.db in die lokale Versions-DB: jede
    build_id (mit Version), die noch NICHT in der lokalen DB steht, wird als
    source='db' ergaenzt (build_id -> title_id/version/name). Bereits vorhandene
    (v.a. eigene, autoritative) Eintraege bleiben unangetastet - unsere DB
    gewinnt. So wachsen extern geladene (CheatSlips/TitleDB) Versionen mit ein.
    Rueckgabe: Anzahl neu archivierter Build-IDs."""
    rows = db._conn.execute(
        "SELECT build_id, title_id, version, game_title FROM builds "
        "WHERE version IS NOT NULL AND version != '' AND build_id IS NOT NULL "
        "AND length(build_id) = 16"
    ).fetchall()
    added = 0
    for bid, tid, ver, name in rows:
        b = (bid or "").upper()
        if b in db._buildid_map:
            continue  # schon vorhanden -> unsere gewinnt
        db._buildid_map[b] = {
            "title_id": (tid or "").upper(),
            "version": (ver or "").strip(),
            "name": (name or "").strip(),
            "source": "db",
        }
        added += 1
    if added:
        db._write_buildid_map()
    return added


def apply_title_name_overrides(db: "GameDatabase") -> int:
    """Force-correct game names for title ids in TITLE_NAME_OVERRIDES.

    Unlike fill_known_title_names, this overwrites whatever name is already
    stored (online sources for these specific title ids are wrong).
    """
    if not TITLE_NAME_OVERRIDES:
        return 0
    fixed = 0
    with db._conn:
        for tid, name in TITLE_NAME_OVERRIDES.items():
            cur = db._conn.execute(
                "UPDATE builds SET game_title = ? "
                "WHERE title_id = ? AND (game_title IS NULL OR game_title != ?)",
                (name, tid, name),
            )
            if cur.rowcount:
                print(f"  name override {tid} -> {name}")
            fixed += cur.rowcount
    return fixed


def fill_known_title_names(db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Fill missing game names from the hard-coded KNOWN_TITLE_NAMES mapping.

    These are title ids that are not listed on any scraper site (tinfoil, titledb,
    GAMES.md, etc.) but are known to the community. Returns the number of names filled.
    """
    filled = apply_title_name_overrides(db)
    # Lokale Ergaenzungs-DB (build_id -> version/name) auf den Bestand anwenden.
    filled += apply_buildid_map(db)
    if not KNOWN_TITLE_NAMES:
        return filled
    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id)) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    total = len(rows)
    if not total:
        return filled

    for i, row in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid = row[0]
        name = KNOWN_TITLE_NAMES.get(tid.upper())
        if name:
            db.update_game_fields(tid, {"game_title": name})
            print(f"  known name {tid} -> {name}")
            filled += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"Known title names filled {filled} game name(s).")
    return filled


def fix_title_id_names(db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Fix rows where the game_title is the raw title_id instead of a real name.

    Some import paths stored the title id as a placeholder in the game_title column.
    This function clears those placeholders and then tries to derive real names:
    1. Hard-coded KNOWN_TITLE_NAMES (for base games not listed online)
    2. Inherit from the base game title for DLC/update ids (suffix 001..800)
    Returns the number of names fixed.
    """
    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE UPPER(game_title) = UPPER(title_id) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    total = len(rows)
    if not total:
        print("No rows found where game_title equals title_id.")
        return 0

    # Clear the placeholder title-ids so they look like missing names.
    for row in rows:
        db._conn.execute(
            "UPDATE builds SET game_title = NULL WHERE title_id = ?",
            (row[0],),
        )
    db._conn.commit()
    print(f"Cleared {total} placeholder title-id name(s).")

    # First try known names.
    filled = fill_known_title_names(db, progress_cb=progress_cb, should_stop=should_stop)

    # Then let DLC/update ids inherit their base game's name.
    derived = derive_names_from_base(db, progress_cb=progress_cb, should_stop=should_stop)
    filled += derived

    # For any remaining base-game ids that still lack a name, use the known mapping
    # again as a final pass (it only updates rows with empty game_title).
    filled += fill_known_title_names(db, progress_cb=progress_cb, should_stop=should_stop)

    print(f"Fixed {filled} title-id-as-name row(s).")
    return filled


def remove_placeholder_builds(db: "GameDatabase") -> int:
    """Delete rows whose build_id is a placeholder (all zeros, all ones, title_id, etc.)."""
    rows = db._conn.execute(
        "SELECT build_id, title_id FROM builds WHERE build_id IS NOT NULL"
    ).fetchall()
    removed = 0
    with db._conn:
        for bid, tid in rows:
            if is_placeholder_build_id(bid, tid):
                cur = db._conn.execute(
                    "DELETE FROM builds WHERE build_id = ? AND title_id = ?",
                    (bid, tid),
                )
                removed += cur.rowcount
    print(f"Removed {removed} placeholder build row(s).")
    return removed


def fill_missing_names_from_games_md(db: "GameDatabase", cache_dir=".",
                                      progress_cb=None, should_stop=None) -> int:
    """Fill missing game names using both GAMES.md and ADEMOLA200 README.md tables.

    Downloads both markdown files (each cached 7 days), merges the title/name tables,
    then updates every database row whose title id still lacks a name. Returns the
    number of names filled.
    """
    by_tid: Dict[str, str] = {}
    games_md_names = fetch_games_md_names(cache_dir=cache_dir)
    if games_md_names:
        by_tid.update(games_md_names)
        print(f"GAMES.md: {len(games_md_names)} names loaded.")
    nx_gfx_names = fetch_nx_gfx_readme_names(cache_dir=cache_dir)
    if nx_gfx_names:
        by_tid.update(nx_gfx_names)
        print(f"NX GFX README: {len(nx_gfx_names)} names loaded.")

    if not by_tid:
        print("No names parsed from either GAMES.md or NX GFX README.")
        return 0

    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id)) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    rows = [r for r in rows if not db._restricted(r[0])]
    total = len(rows)
    if not total:
        print("No missing game names — nothing to fill from GAMES.md/NX GFX README.")
        return 0

    print(f"Merged {len(by_tid)} names; filling {total} missing title(s)...")
    filled = 0
    for i, row in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid = row[0]
        name = by_tid.get(tid.upper())
        if name:
            db.update_game_fields(tid, {"game_title": name})
            print(f"  filled {tid} -> {name}")
            filled += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"GAMES.md / NX GFX README filled {filled} game name(s).")
    return filled


def scrape_tinfoil_name(title_id: str, timeout: int = 30) -> Optional[str]:
    """Fetch the game name for a title id from tinfoil.io.

    Returns the stripped game title or None if the page is unavailable or has no
    recognizable title. Trademark symbols (®, ™) are preserved because they are part
    of the official name on the page.
    """
    import requests

    url = TINFOIL_TITLE_URL.format(title_id=title_id.upper())
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        soup = parse_html(resp.text)
    except Exception:
        return None
    # The title page uses the game name in <title> and the first <h1>.
    for tag in (soup.find("h1"), soup.title):
        if tag:
            name = tag.get_text(strip=True)
            if name and name not in ("Home Page", "Titles", "Title"):
                return name
    return None


def fill_missing_names_from_tinfoil(db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Fill missing game names by scraping tinfoil.io title pages.

    Queries the database for title ids that still have no game name, then requests
    each tinfoil.io/Title/<title_id> page and stores the returned title. Returns
    the number of names filled.
    """
    rows = db._conn.execute(
        "SELECT DISTINCT title_id FROM builds "
        "WHERE (game_title IS NULL OR game_title = '' OR UPPER(game_title) = UPPER(title_id)) "
        "AND title_id IS NOT NULL AND length(title_id) = 16"
    ).fetchall()
    rows = [r for r in rows if not db._restricted(r[0])]
    total = len(rows)
    if not total:
        print("No missing game names — nothing to scrape from tinfoil.io.")
        return 0

    print(f"Scraping tinfoil.io for {total} missing game name(s)...")
    filled = 0
    for i, row in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid = row[0]
        try:
            name = scrape_tinfoil_name(tid)
        except Exception as exc:
            print(f"  ERROR {tid}: {exc}")
            name = None
        if name:
            db.update_game_fields(tid, {"game_title": name})
            print(f"  filled {tid} -> {name}")
            filled += 1
        if progress_cb:
            progress_cb(i, total)
    print(f"tinfoil.io filled {filled} game name(s).")
    return filled


def fill_missing_names(db: "GameDatabase", api: "CheatslipsAPI" = None,
                       regions: Optional[List[str]] = None, cache_dir: str = ".",
                       progress_cb=None, should_stop=None, with_regions: bool = False) -> int:
    """Fill missing game names + covers by trying multiple titledb regions, then the API.

    Iterates the given region files in order, downloading and caching each one
    (7-day cache). Stops early once every title in the DB has a name. Any titles
    still unnamed after all regions are tried are looked up via the CheatSlips
    API (if ``api`` is provided - no token required for game names). Then
    tinfoil.io is scraped as another fallback. Finally, any remaining DLC/update
    title ids inherit their base game's name + cover.
    Returns the total number of games filled across all sources.
    """
    if regions is None:
        regions = TITLEDB_REGIONS

    total_filled = 0
    for region in regions:
        if should_stop and should_stop():
            break
        remaining = db.title_ids_missing_meta()
        if not remaining:
            print("All games now have names/covers — done early.")
            break
        print(f"[{region}] {len(remaining)} title(s) still missing — scanning titledb {region}...")
        try:
            filled = fill_metadata_from_titledb(
                db, region=region, cache_dir=cache_dir,
                progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"[{region}] skipped due to error: {exc}")
            filled = 0
        total_filled += filled

    if api is not None and not (should_stop and should_stop()):
        remaining = db.title_ids_missing_meta()
        if remaining:
            print(f"{len(remaining)} title(s) still missing — trying CheatSlips API...")
            updated = refresh_titles_from_api(
                api, db, remaining,
                progress_cb=progress_cb, should_stop=should_stop,
            )
            total_filled += updated

    # Extra source: switchbrew wiki (older / regional titles titledb may miss).
    if not (should_stop and should_stop()) and db.title_ids_missing_meta():
        try:
            total_filled += fill_metadata_from_switchbrew(
                db, cache_dir=cache_dir,
                progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"switchbrew step skipped: {exc}")

    # Extra source: tinfoil.io title pages (covers titles that titledb may miss).
    if not (should_stop and should_stop()) and db.title_ids_missing_meta():
        try:
            total_filled += fill_missing_names_from_tinfoil(
                db, progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"tinfoil.io step skipped: {exc}")

    # Extra source: ibnux/switch-cheat GAMES.md table.
    if not (should_stop and should_stop()) and db.title_ids_missing_meta():
        try:
            total_filled += fill_missing_names_from_games_md(
                db, cache_dir=cache_dir,
                progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"GAMES.md step skipped: {exc}")

    # Final fallback: hard-coded known titles not listed on any scraper site.
    if not (should_stop and should_stop()) and db.title_ids_missing_meta():
        try:
            total_filled += fill_known_title_names(
                db, progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"known title names step skipped: {exc}")

    # Final pass: DLC/update titles inherit their base game's name + cover.
    if not (should_stop and should_stop()):
        total_filled += derive_names_from_base(db, should_stop=should_stop)

    # Optional: also tag every title id with its eShop region(s). Reuses the same
    # (cached) titledb region files, so it adds little extra cost here.
    if with_regions and not (should_stop and should_stop()):
        try:
            fill_regions_from_titledb(
                db, regions=regions, cache_dir=cache_dir,
                progress_cb=progress_cb, should_stop=should_stop,
            )
        except Exception as exc:
            print(f"region tagging step skipped: {exc}")

    print(f"fill_missing_names: {total_filled} game(s) enriched in total.")
    return total_filled


def fill_missing_versions(api: "CheatslipsAPI", scraper: "CheatslipsMetadataScraper",
                          db: "GameDatabase", progress_cb=None, should_stop=None) -> int:
    """Fill in game versions for builds that have none, using cheatslips' HTML.

    The version<->build-id mapping only exists on cheatslips (its game page lists
    "1.4.0 ... BID: ..."). For each title with missing versions we resolve the
    slug via the API, scrape the game page and match build ids to versions.
    Builds that are not on cheatslips (e.g. GBAtemp-only) keep no version.
    """
    tids = db.title_ids_missing_version()
    total = len(tids)
    filled = 0
    print(f"Filling versions for {total} game(s) using cheatslips...")
    for i, tid in enumerate(tids, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        # Find the cheatslips slug for this title id (from the DB or the API).
        info_db = db.get_game_info(tid)
        slug = info_db.get("slug") if info_db else None
        title = info_db.get("title") if info_db else None
        if not slug:
            try:
                data = api.get_game(tid)
                slug = data.get("slug")
                title = title or data.get("name")
            except Exception:
                slug = None
        if not slug:
            if progress_cb:
                progress_cb(i, total)
            continue
        try:
            details = scraper.scrape_game_details(slug)
        except Exception as exc:
            print(f"  ERROR {tid}: {exc}")
            if progress_cb:
                progress_cb(i, total)
            continue
        if details:
            db.set_game_meta(tid, slug=slug, game_title=title or details.get("title"))
            for s in details.get("sources", []):
                v = s.get("version")
                b = (s.get("build_id") or "").upper()
                if v and b:
                    filled += db.set_version(tid, b, v)
        if progress_cb:
            progress_cb(i, total)
    print(f"Filled {filled} version(s).")
    return filled


def import_disk_titles_to_db(titles_dir: Path, meta_dir: Path, db: "GameDatabase") -> int:
    """Scan titles/ and by_bid/ on disk, import any TID/BID not yet in the DB, and fill
    known names/slugs from the meta/*.json sidecar files or the hard-coded KNOWN_BUILD_IDS.

    Returns the number of new build rows inserted.
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")

    # Build: title_id -> {slug, title} from meta JSONs
    meta_info: Dict[str, Dict] = {}
    if meta_dir.exists():
        for jf in meta_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                slug = data.get("slug", "")
                title = data.get("title") or ""
                for src in data.get("sources", []):
                    tid = (src.get("title_id") or "").upper()
                    if tid and len(tid) == 16 and tid not in meta_info:
                        meta_info[tid] = {"slug": slug, "title": title}
            except Exception:
                pass

    # Existing TIDs already in DB
    existing_bids: set = set()
    for row in db._conn.execute("SELECT build_id FROM builds WHERE build_id IS NOT NULL").fetchall():
        existing_bids.add((row[0] or "").upper())

    inserted = 0

    if titles_dir.exists():
        tid_dirs = [d for d in titles_dir.iterdir() if d.is_dir() and len(d.name) == 16]
        print(f"Scanning {len(tid_dirs)} title directories on disk...")
        for tid_dir in tid_dirs:
            tid = tid_dir.name.upper()
            meta = meta_info.get(tid, {})
            cheats_dir = tid_dir / "cheats"
            bids = []
            if cheats_dir.exists():
                bids = [f.stem.upper() for f in cheats_dir.glob("*.txt") if len(f.stem) == 16]
            # Drop placeholder build ids (all zeros, all ones, equal to title id, etc.).
            bids = [b for b in bids if b and not is_placeholder_build_id(b, tid)]
            if not bids:
                # Don't create a placeholder row. If only placeholder build ids exist,
                # skip the title directory entirely.
                continue
            for bid in bids:
                if bid in existing_bids:
                    continue  # already in DB
                with db._conn:
                    db._conn.execute(
                        """INSERT INTO builds
                            (build_id, title_id, slug, game_title, last_updated, source)
                           VALUES (?, ?, ?, ?, ?, 'disk')
                           ON CONFLICT(build_id, title_id) DO NOTHING""",
                        (bid, tid, meta.get("slug"), meta.get("title") or None, now),
                    )
                existing_bids.add(bid)
                inserted += 1
            # Also patch name/slug for TIDs already in DB but lacking them
            if meta.get("title") or meta.get("slug"):
                db.set_game_meta(tid, slug=meta.get("slug"), game_title=meta.get("title"))

    # Scan by_bid/ files and associate known build ids with their title id.
    by_bid_dir = titles_dir.parent / "by_bid"
    if by_bid_dir.exists():
        known_bid_files = [f for f in by_bid_dir.glob("*.txt") if len(f.stem) == 16]
        print(f"Scanning {len(known_bid_files)} build-id files on disk...")
        for f in known_bid_files:
            bid = f.stem.upper()
            if bid in existing_bids:
                continue
            if is_placeholder_build_id(bid):
                print(f"  skipping {bid}: placeholder build id")
                continue
            tid = KNOWN_BUILD_IDS.get(bid)
            if not tid:
                print(f"  skipping {bid}: unknown build id")
                continue
            meta = meta_info.get(tid, {})
            with db._conn:
                db._conn.execute(
                    """INSERT INTO builds
                        (build_id, title_id, slug, game_title, last_updated, source)
                       VALUES (?, ?, ?, ?, ?, 'disk')
                       ON CONFLICT(build_id, title_id) DO NOTHING""",
                    (bid, tid, meta.get("slug"), meta.get("title") or None, now),
                )
            existing_bids.add(bid)
            inserted += 1
            print(f"  imported {bid} -> {tid}")
            if meta.get("title") or meta.get("slug"):
                db.set_game_meta(tid, slug=meta.get("slug"), game_title=meta.get("title"))

    # Apply hard-coded known names to any newly imported rows.
    if inserted:
        fill_known_title_names(db)

    print(f"Imported {inserted} new build row(s) from disk.")
    return inserted


# --------------------------------------------------------------------------
# Export downloaded cheats to a Nintendo Switch SD card
# --------------------------------------------------------------------------

# Marker folders/files that identify a Switch SD card root (CFW layout).
_SD_MARKERS = {"atmosphere", "switch", "nintendo", "bootloader", "emummc",
               "sept", "warmboot.bin", "payload.bin"}

# Export targets. Every modern cheat tool ultimately reads the Atmosphère
# path, so that is the default and the only one that auto-loads.
SD_EXPORT_MODES = {
    # mode:      (sub-path template relative to the SD root, human label)
    "atmosphere": ("atmosphere/contents/{tid}/cheats/{bid}.txt",
                   "Atmosphère (auto-loads on game start)"),
    "breeze":     ("switch/breeze/cheats/{tid}/{bid}.txt",
                   "Breeze (activate in the Breeze UI)"),
    "edizon":     ("switch/EdiZon/cheats/{bid}.txt",
                   "EdiZon SE (loads when the game launches)"),
}


def detect_sd_roots() -> List[str]:
    """Return likely Switch SD-card roots.

    On Windows every drive letter whose root contains a CFW marker folder
    (atmosphere/, switch/, Nintendo/, bootloader/, emummc/ …) is returned.
    On other platforms common mount points are probed. Best-effort only.
    """
    roots: List[str] = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:/")
            try:
                if not root.exists():
                    continue
                names = {e.name.lower() for e in root.iterdir()}
            except Exception:
                continue
            if names & _SD_MARKERS:
                roots.append(str(root))
    else:
        for base in ("/media", "/run/media", "/mnt", "/Volumes"):
            b = Path(base)
            if not b.exists():
                continue
            for cand in b.rglob("*"):
                try:
                    if cand.is_dir() and {e.name.lower() for e in cand.iterdir()} & _SD_MARKERS:
                        roots.append(str(cand))
                except Exception:
                    continue
    return roots


def looks_like_sd_root(path) -> bool:
    """True if ``path`` looks like a Switch SD root (has a CFW marker folder)."""
    try:
        p = Path(path)
        return p.is_dir() and {e.name.lower() for e in p.iterdir()} & _SD_MARKERS != set()
    except Exception:
        return False


def _local_cheat_file(out: Path, tid: str, bid: str) -> Optional[Path]:
    """Find a build's downloaded cheat file in our output dir (both layouts)."""
    for p in (out / "titles" / tid / "cheats" / f"{bid}.txt",
              out / "by_bid" / f"{bid}.txt"):
        if p.exists():
            return p
    return None


def export_cheats_to_sd(db: "GameDatabase", output_dir, sd_root, mode: str = "atmosphere",
                        title_ids: Optional[List[str]] = None,
                        progress_cb=None, should_stop=None) -> Dict[str, int]:
    """Copy downloaded cheat files onto a Switch SD card in the tool's layout.

    ``mode`` is one of SD_EXPORT_MODES:
      atmosphere -> {sd}/atmosphere/contents/{TID}/cheats/{BID}.txt (auto-load)
      breeze     -> {sd}/switch/breeze/cheats/{TID}/{BID}.txt       (activate in UI)
      edizon     -> {sd}/switch/EdiZon/cheats/{BID}.txt             (loads on launch)

    Only builds whose local file contains REAL cheat codes are exported; empty
    / stub / quota files are skipped. Existing target files are unioned so
    cheats already on the SD card are never lost. Returns a stats dict with
    keys: exported, skipped_stub, missing, games, errors.
    """
    out = Path(output_dir)
    sd = Path(sd_root)
    if mode not in SD_EXPORT_MODES:
        raise ValueError(f"Unknown export mode: {mode!r}")
    template = SD_EXPORT_MODES[mode][0]

    if not sd.exists():
        raise RuntimeError(f"SD path does not exist: {sd}")

    # Which (title_id, build_id) pairs to consider.
    if title_ids:
        wanted = {t.upper() for t in title_ids}
        rows = [(r[0], r[1]) for r in db._conn.execute(
            "SELECT DISTINCT title_id, build_id FROM builds WHERE build_id IS NOT NULL").fetchall()
            if (r[0] or "").upper() in wanted]
    else:
        rows = [(r[0], r[1]) for r in db._conn.execute(
            "SELECT DISTINCT title_id, build_id FROM builds WHERE build_id IS NOT NULL").fetchall()]

    total = len(rows)
    stats = {"exported": 0, "skipped_stub": 0, "missing": 0, "errors": 0, "games": 0}
    games_done = set()
    print(f"Exporting to SD ({SD_EXPORT_MODES[mode][1]}): {total} build(s) to check → {sd}")

    for i, (tid, bid) in enumerate(rows, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        tid_u, bid_u = (tid or "").upper(), (bid or "").upper()
        if not tid_u or not bid_u:
            continue
        src = _local_cheat_file(out, tid_u, bid_u)
        if src is None:
            stats["missing"] += 1
            if progress_cb:
                progress_cb(i, total)
            continue
        try:
            content = src.read_text(encoding="utf-8", errors="replace")
        except Exception:
            stats["errors"] += 1
            if progress_cb:
                progress_cb(i, total)
            continue
        # Never push empty/stub/quota files onto the card.
        if cheat_file_is_empty(content):
            stats["skipped_stub"] += 1
            if progress_cb:
                progress_cb(i, total)
            continue
        target = sd / template.format(tid=tid_u, bid=bid_u)
        try:
            # Union with an existing target so SD cheats are never lost.
            save_cheat_merged(target, content)
            stats["exported"] += 1
            games_done.add(tid_u)
        except Exception as exc:
            stats["errors"] += 1
            print(f"  ERROR {tid_u}/{bid_u}: {exc}")
        if progress_cb:
            progress_cb(i, total)

    stats["games"] = len(games_done)
    print(f"SD export done: {stats['exported']} file(s) for {stats['games']} game(s) "
          f"exported, {stats['skipped_stub']} stub/empty skipped, "
          f"{stats['missing']} not downloaded, {stats['errors']} error(s).")
    return stats


def _export_build_rows(db: "GameDatabase", title_ids: Optional[List[str]]):
    """(title_id, build_id) pairs to export — all, or only the given title ids."""
    rows = db._conn.execute(
        "SELECT DISTINCT title_id, build_id FROM builds "
        "WHERE build_id IS NOT NULL").fetchall()
    if title_ids:
        wanted = {t.upper() for t in title_ids}
        return [(r[0], r[1]) for r in rows if (r[0] or "").upper() in wanted]
    return [(r[0], r[1]) for r in rows]


def export_cheats_to_zip(db: "GameDatabase", output_dir, zip_path, mode: str = "atmosphere",
                         title_ids: Optional[List[str]] = None,
                         progress_cb=None, should_stop=None) -> Dict[str, int]:
    """Export downloaded cheat files into a ZIP archive with the SD-card layout.

    The archive mirrors exactly what ``export_cheats_to_sd`` writes, so the user
    can unzip it onto the SD-card root and the cheats land in the right place:
      atmosphere -> atmosphere/contents/{TID}/cheats/{BID}.txt (auto-load)
      breeze     -> switch/breeze/cheats/{TID}/{BID}.txt        (activate in UI)
      edizon     -> switch/EdiZon/cheats/{BID}.txt              (loads on launch)

    Only builds whose local file contains REAL cheat codes are included; empty /
    stub / quota files are skipped. ``title_ids`` limits the export to those
    titles (e.g. the selected rows). Returns a stats dict with keys:
    exported, skipped_stub, missing, games, errors.
    """
    out = Path(output_dir)
    zip_path = Path(zip_path)
    if mode not in SD_EXPORT_MODES:
        raise ValueError(f"Unknown export mode: {mode!r}")
    template = SD_EXPORT_MODES[mode][0]

    rows = _export_build_rows(db, title_ids)
    total = len(rows)
    stats = {"exported": 0, "skipped_stub": 0, "missing": 0, "errors": 0, "games": 0}
    games_done = set()
    seen_arcnames = set()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting to ZIP ({SD_EXPORT_MODES[mode][1]}): {total} build(s) to check → {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (tid, bid) in enumerate(rows, 1):
            if should_stop and should_stop():
                print("Stopped by user.")
                break
            tid_u, bid_u = (tid or "").upper(), (bid or "").upper()
            if not tid_u or not bid_u:
                continue
            src = _local_cheat_file(out, tid_u, bid_u)
            if src is None:
                stats["missing"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            try:
                content = src.read_text(encoding="utf-8", errors="replace")
            except Exception:
                stats["errors"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            if cheat_file_is_empty(content):
                stats["skipped_stub"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            arcname = template.format(tid=tid_u, bid=bid_u)
            # The flat EdiZon layout is keyed by build id only; guard against the
            # (rare) case of the same build id under two titles.
            if arcname in seen_arcnames:
                if progress_cb:
                    progress_cb(i, total)
                continue
            try:
                zf.writestr(arcname, content)
                seen_arcnames.add(arcname)
                stats["exported"] += 1
                games_done.add(tid_u)
            except Exception as exc:
                stats["errors"] += 1
                print(f"  ERROR {tid_u}/{bid_u}: {exc}")
            if progress_cb:
                progress_cb(i, total)

    stats["games"] = len(games_done)
    # An empty archive is useless — remove it so the user isn't misled.
    if stats["exported"] == 0:
        try:
            zip_path.unlink()
        except Exception:
            pass
    print(f"ZIP export done: {stats['exported']} file(s) for {stats['games']} game(s) "
          f"written, {stats['skipped_stub']} stub/empty skipped, "
          f"{stats['missing']} not downloaded, {stats['errors']} error(s).")
    return stats


# ---------------------------------------------------------------------------
# Emulator export — the Yuzu-family "load" layout used by Eden / Suyu / Sudachi
# (and desktop yuzu / Ryujinx). The generic structure the user places inside an
# emulator's `load` folder is:
#     <TitleID>/<GameName>/cheats/<BuildID>.txt
# Picking a specific emulator just prepends that emulator's load path so the
# package is drop-in.
# ---------------------------------------------------------------------------
# Every Yuzu-family emulator reads cheats from
#     <base>/load/<TitleID>/<GameName>/cheats/<BuildID>.txt
# Ryujinx is the exception: it uses a `mods` folder instead of `load`, but the
# same <TitleID>/<GameName>/cheats/<BuildID>.txt tail. The prefix below is the
# path from the emulator's config base (%APPDATA% on Windows, ~/.local/share on
# Linux / Steam Deck, or the Android data path) down to that load/mods folder;
# it is prepended so the exported package is drop-in.
EMULATOR_TARGETS = {
    # id:            (human label, prefix prepended to <TID>/<Name>/cheats/<BID>.txt)
    # --- Desktop (Windows / Linux / Steam Deck) — Yuzu-family: <base>/load ---
    "yuzu":         ("Yuzu (Windows)", "yuzu/load"),
    "suyu":         ("Suyu (Windows / Android)", "suyu/load"),
    "sudachi":      ("Sudachi (Windows / Linux / Steam Deck)", "sudachi/load"),
    "torzu":        ("Torzu (Windows)", "torzu/load"),
    # Ryujinx: uses `mods`, not `load`.
    "ryujinx":      ("Ryujinx (Windows) — mods folder", "Ryujinx/mods"),
    # --- Android emulators ---
    "eden":         ("Eden (Android)", "Android/data/dev.eden.eden_emulator/files/load"),
    "sudachi_and":  ("Sudachi (Android)", "Android/data/org.sudachi.sudachi/files/load"),
    # --- Generic: the contents you drop into a 'load' (or Ryujinx 'mods') folder ---
    "generic":      ("Generic — a 'load' or 'mods' folder", ""),
}

# Trademark / service marks / U+FFFD (as \u escapes so the source stays
# encoding-safe), and characters a file system won't allow in a folder name.
_MODNAME_SYMBOLS = re.compile("[™®©℗℠�]")
_MODNAME_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_mod_name(name: str) -> str:
    """A folder-safe game name for the emulator mod folder: strip trademark
    symbols and filesystem-illegal characters, normalise en/em dashes to a
    hyphen, collapse whitespace, drop trailing dots and cap the length."""
    n = _MODNAME_SYMBOLS.sub("", name or "")
    n = n.replace("–", "-").replace("—", "-")  # en/em dash -> hyphen
    n = _MODNAME_INVALID.sub("", n)
    n = re.sub(r"\s+", " ", n).strip().strip(".").strip()
    return n[:60].strip()


def build_title_name_map(conn) -> Dict[str, str]:
    """Map each 16-hex Title ID to its cleaned, folder-safe game name.

    For each Title ID the most common cleaned name across its builds is used
    (ties broken by the shortest — the cleaner canonical title). This is the
    same rule as the names.json export, so the folder names match the Android
    app's. ``conn`` is a plain sqlite3 connection (``GameDatabase._conn``).
    """
    import collections
    buckets = collections.defaultdict(collections.Counter)
    for r in conn.execute(
            "SELECT title_id, game_title FROM builds "
            "WHERE game_title IS NOT NULL AND game_title <> ''"):
        tid = (r[0] or "").strip().upper()
        if len(tid) != 16:
            continue
        name = sanitize_mod_name(r[1])
        if name:
            buckets[tid][name] += 1
    return {tid: sorted(ctr.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
            for tid, ctr in buckets.items()}


def export_cheats_for_emulator(db: "GameDatabase", output_dir, dest, name_map,
                               prefix: str = "", as_zip: bool = False,
                               title_ids: Optional[List[str]] = None,
                               progress_cb=None, should_stop=None) -> Dict[str, int]:
    """Export downloaded cheats into the emulator load layout:

        [<prefix>/]<TitleID>/<GameName>/cheats/<BuildID>.txt

    ``name_map`` maps Title ID -> already-sanitised game name (see
    ``build_title_name_map``); a Title ID that's missing falls back to itself.
    Only builds whose local file contains real cheat codes are written; empty /
    stub files are skipped. Writes a folder tree (``as_zip=False``) or a single
    ZIP archive (``as_zip=True``). Returns a stats dict with keys:
    exported, skipped_stub, missing, games, errors.
    """
    out = Path(output_dir)
    dest = Path(dest)
    prefix = (prefix or "").strip("/\\")
    rows = _export_build_rows(db, title_ids)
    total = len(rows)
    stats = {"exported": 0, "skipped_stub": 0, "missing": 0, "errors": 0, "games": 0}
    games_done = set()

    def rel_for(tid_u: str, bid_u: str) -> str:
        mod = name_map.get(tid_u) or tid_u
        parts = ([prefix] if prefix else []) + [tid_u, mod, "cheats", f"{bid_u}.txt"]
        return "/".join(parts)

    zf = None
    if as_zip:
        dest.parent.mkdir(parents=True, exist_ok=True)
        zf = zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED)
    print(f"Exporting for emulator ({'ZIP' if as_zip else 'folder'}): "
          f"{total} build(s) to check -> {dest}")
    try:
        for i, (tid, bid) in enumerate(rows, 1):
            if should_stop and should_stop():
                print("Stopped by user.")
                break
            tid_u, bid_u = (tid or "").upper(), (bid or "").upper()
            if not tid_u or not bid_u:
                continue
            src = _local_cheat_file(out, tid_u, bid_u)
            if src is None:
                stats["missing"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            try:
                content = src.read_text(encoding="utf-8", errors="replace")
            except Exception:
                stats["errors"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            if cheat_file_is_empty(content):
                stats["skipped_stub"] += 1
                if progress_cb:
                    progress_cb(i, total)
                continue
            rel = rel_for(tid_u, bid_u)
            try:
                if zf is not None:
                    zf.writestr(rel, content)
                else:
                    save_cheat_merged(dest / rel, content)
                stats["exported"] += 1
                games_done.add(tid_u)
            except Exception as exc:
                stats["errors"] += 1
                print(f"  ERROR {tid_u}/{bid_u}: {exc}")
            if progress_cb:
                progress_cb(i, total)
    finally:
        if zf is not None:
            zf.close()
            if stats["exported"] == 0:
                try:
                    dest.unlink()
                except Exception:
                    pass

    stats["games"] = len(games_done)
    print(f"Emulator export done: {stats['exported']} file(s) for {stats['games']} "
          f"game(s), {stats['skipped_stub']} stub/empty skipped, "
          f"{stats['missing']} not downloaded, {stats['errors']} error(s).")
    return stats


# Cheat paths inside an exported ZIP (any of the three SD layouts):
#   atmosphere/contents/<TID>/cheats/<BID>.txt   -> tid, bid
#   switch/breeze/cheats/<TID>/<BID>.txt         -> tid, bid
#   switch/EdiZon/cheats/<BID>.txt               -> bid only (tid resolved via DB)
_ZIP_ATMO_RE = re.compile(r"([0-9A-Fa-f]{16})/cheats/([0-9A-Fa-f]{16})\.txt$")
_ZIP_BREEZE_RE = re.compile(r"cheats/([0-9A-Fa-f]{16})/([0-9A-Fa-f]{16})\.txt$")
_ZIP_FLAT_RE = re.compile(r"cheats/([0-9A-Fa-f]{16})\.txt$")


def import_cheats_from_zip(output_dir, db: "GameDatabase", zip_path,
                           progress_cb=None, should_stop=None):
    """Import cheat files from a ZIP archive (as produced by export_cheats_to_zip
    or any archive using the same SD-card layouts) back into the database + disk.

    Recognises all three export layouts. For the flat EdiZon layout (build id
    only) the title id is resolved from the existing database or KNOWN_BUILD_IDS;
    entries whose title id cannot be recovered are skipped. Codeless/stub files
    are skipped. Files are written into our titles/{tid}/cheats/{bid}.txt schema
    (source='import-zip'). Returns (files_written, games).
    """
    import io
    import zipfile as _zip

    out = Path(output_dir)
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise RuntimeError(f"ZIP not found: {zip_path}")
    raw = zip_path.read_bytes()
    zf = _zip.ZipFile(io.BytesIO(raw))

    entries = [n for n in zf.namelist() if n.lower().endswith(".txt")]
    total = len(entries)
    print(f"ZIP import: {total} .txt entry/entries in {zip_path.name}")

    games = {}     # tid -> list of (bid, names)
    written = stubs = unresolved = 0
    for i, name in enumerate(entries, 1):
        if should_stop and should_stop():
            print("Stopped by user.")
            break
        m = _ZIP_ATMO_RE.search(name)
        if m:
            tid, bid = m.group(1).upper(), m.group(2).upper()
        else:
            m = _ZIP_BREEZE_RE.search(name)
            if m:
                tid, bid = m.group(1).upper(), m.group(2).upper()
            else:
                m = _ZIP_FLAT_RE.search(name)
                if not m:
                    continue
                bid = m.group(1).upper()
                tid = (db.title_id_for_build(bid) or KNOWN_BUILD_IDS.get(bid) or "").upper()
                if not tid:
                    unresolved += 1
                    if progress_cb:
                        progress_cb(i, total)
                    continue

        content = zf.read(name).decode("utf-8", "replace")
        # Only import files that actually contain real cheat codes.
        if not parse_valid_cheats(content):
            stubs += 1
            if progress_cb:
                progress_cb(i, total)
            continue
        save_path = out / "titles" / tid / "cheats" / f"{bid}.txt"
        if save_cheat_merged(save_path, content):
            written += 1
        names = parse_cheat_names_from_content(content)
        games.setdefault(tid, []).append((bid, names))
        if progress_cb:
            progress_cb(i, total)

    for tid, builds in games.items():
        sources = [{
            "build_id": bid, "title_id": tid, "source_id": None,
            "version": None, "upload_date": None,
            "cheat_count": len(names), "cheat_names": names,
            "credits": None, "description": None, "cheat_id": None,
        } for bid, names in builds]
        db.upsert_game({"title_id": tid, "title": None, "slug": None,
                        "image": None, "banner": None, "sources": sources},
                       source="import-zip")

    msg = f"ZIP import done: {written} file(s) for {len(games)} game(s)"
    if stubs:
        msg += f", {stubs} stub/empty skipped"
    if unresolved:
        msg += f", {unresolved} skipped (unknown title id — EdiZon flat layout)"
    print(msg + ".")
    return written, len(games)


def import_database(live_db, imported_db, mode: str = "merge") -> dict:
    """Import a previously exported cheats.db back into the live database.

    ``mode="merge"`` (default): every build from *imported_db* is upserted into
    *live_db* — existing builds keep their non-empty fields (COALESCE) and never
    lose a real cheat count to a 0/NULL one; new builds are added. Nothing is
    removed. Both files are migrated to the current schema first, so importing an
    older export works and only the columns both share are copied.

    ``mode="replace"``: *live_db* is overwritten with a clean copy of
    *imported_db* (SQLite online backup). A timestamped backup of the current
    live database is written next to it first, and the WAL/SHM sidecars are
    cleared so no stale pages survive.

    Returns a summary dict: {mode, total_imported, before, after, added,
    updated, backup}.
    """
    import datetime as _dt

    live = Path(live_db)
    imported = Path(imported_db)
    if not imported.exists():
        raise RuntimeError(f"Database not found: {imported}")

    # Validate: it must actually be a cheats database (has a 'builds' table).
    probe = sqlite3.connect(str(imported))
    try:
        has_builds = probe.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='builds'"
        ).fetchone()
    finally:
        probe.close()
    if not has_builds:
        raise RuntimeError("This file has no 'builds' table — not a Switch Cheats database.")

    if mode == "replace":
        backup = None
        if live.exists():
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = live.with_name(f"{live.stem}_backup_before_import_{stamp}.db")
            bcon = sqlite3.connect(str(live))
            dcon = sqlite3.connect(str(backup))
            try:
                bcon.backup(dcon)
            finally:
                dcon.close(); bcon.close()
        # Overwrite the live DB with a clean copy of the imported one.
        scon = sqlite3.connect(str(imported))
        # Fresh target: remove the live file + its WAL/SHM sidecars first.
        for p in (live, live.with_name(live.name + "-wal"), live.with_name(live.name + "-shm")):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        tcon = sqlite3.connect(str(live))
        try:
            scon.backup(tcon)
            total = tcon.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        finally:
            tcon.close(); scon.close()
        print(f"Database replaced from {imported.name} ({total} build(s)).")
        return {"mode": "replace", "total_imported": total, "before": 0,
                "after": total, "added": total, "updated": 0, "backup": str(backup) if backup else None}

    # --- merge -----------------------------------------------------------
    # Migrate both files to the full schema so their column sets line up.
    GameDatabase(imported).close()
    GameDatabase(live).close()

    con = sqlite3.connect(str(live))
    try:
        con.execute("PRAGMA busy_timeout=5000")
        before = con.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        con.execute("ATTACH DATABASE ? AS imp", (str(imported),))
        main_cols = [r[1] for r in con.execute("PRAGMA table_info(builds)")]
        imp_cols = {r[1] for r in con.execute("PRAGMA imp.table_info(builds)")}
        cols = [c for c in main_cols if c in imp_cols]
        if "build_id" not in cols or "title_id" not in cols:
            raise RuntimeError("Imported database is missing the build_id/title_id key columns.")
        total_imported = con.execute("SELECT COUNT(*) FROM imp.builds").fetchone()[0]

        col_list = ", ".join(cols)
        # Build the ON CONFLICT update: keep existing non-empty values, and never
        # let a 0/NULL cheat count overwrite a real one (mirrors upsert_build).
        set_parts = []
        for c in cols:
            if c in ("build_id", "title_id"):
                continue
            if c == "cheat_count":
                set_parts.append(
                    "cheat_count = CASE WHEN excluded.cheat_count IS NULL "
                    "OR excluded.cheat_count = 0 THEN builds.cheat_count "
                    "ELSE excluded.cheat_count END")
            elif c == "cheat_names":
                set_parts.append(
                    "cheat_names = CASE WHEN excluded.cheat_count IS NULL "
                    "OR excluded.cheat_count = 0 THEN builds.cheat_names "
                    "ELSE excluded.cheat_names END")
            elif c == "last_updated":
                set_parts.append("last_updated = excluded.last_updated")
            elif c == "cheats_added_at":
                # Wie upsert_build: nur bei echter Cheat-Aenderung stempeln.
                set_parts.append(
                    "cheats_added_at = CASE WHEN excluded.cheat_count IS NULL "
                    "OR excluded.cheat_count = 0 THEN builds.cheats_added_at "
                    "WHEN builds.cheat_names IS NOT NULL AND "
                    "excluded.cheat_names = builds.cheat_names "
                    "THEN builds.cheats_added_at "
                    "ELSE COALESCE(excluded.cheats_added_at, "
                    "builds.cheats_added_at) END")
            else:
                set_parts.append(f"{c} = COALESCE(excluded.{c}, builds.{c})")
        sql = (f"INSERT INTO builds ({col_list}) "
               f"SELECT {col_list} FROM imp.builds WHERE build_id IS NOT NULL "
               f"AND title_id IS NOT NULL "
               f"ON CONFLICT(build_id, title_id) DO UPDATE SET {', '.join(set_parts)}")
        with con:
            con.execute(sql)
        after = con.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        con.execute("DETACH DATABASE imp")
    finally:
        con.close()

    added = after - before
    updated = max(0, total_imported - added)
    print(f"Database merge: imported {total_imported} build(s) — "
          f"{added} added, {updated} updated (now {after} total).")
    return {"mode": "merge", "total_imported": total_imported, "before": before,
            "after": after, "added": added, "updated": updated, "backup": None}


def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION} by {APP_AUTHOR} — scrape & download "
                    "Nintendo Switch cheats from CheatSlips.com")
    sub = parser.add_subparsers(dest="command", required=True)

    meta = sub.add_parser("metadata", help="Scrape game/build metadata without login")
    meta.add_argument("--output", "-o", default="./metadata", help="Output directory")
    meta.add_argument("--max-pages", type=int, default=None, help="Limit number of game list pages")
    meta.add_argument("--delay", type=float, default=0.3, help="Seconds between requests")
    meta.add_argument("--workers", type=int, default=4, help="Parallel threads for scraping game details")
    meta.add_argument("--list-workers", type=int, default=8, help="Parallel threads for listing pages (default: 8)")
    meta.add_argument("--game-slug", default=None, help="Scrape only a single game")
    meta.add_argument("--db", default="./cheats.db", help="Path to the persistent SQLite database to maintain")
    meta.add_argument("--log-file", default=None, help="Mirror console output into this log file")

    dl = sub.add_parser("download", help="Download cheat files via the official API (no browser)")
    dl.add_argument("--output", "-o", default="./cheatsdownload", help="Output directory")
    dl.add_argument("--db", default="./cheats.db", help="Database with the title ids to download")
    dl.add_argument("--token", default=None, help="CheatSlips API token (from your account)")
    dl.add_argument("--email", default=None, help="Email (used to fetch an API token if --token is not given)")
    dl.add_argument("--password", default=None, help="Password (used to fetch an API token)")
    dl.add_argument("--title-id", default=None, help="Download only a single title id")
    dl.add_argument("--flat-output", action="store_true", help="Save all cheats as flat {build_id}.txt files")
    dl.add_argument("--no-resume", action="store_true", help="Re-download even if files already exist")
    dl.add_argument("--log-file", default=None, help="Mirror console output into this log file")

    pkg = sub.add_parser("package", help="Zip the downloaded titles folder for easy copying to SD card")
    pkg.add_argument("--output", "-o", default="./cheatsdownload", help="Output directory containing the titles folder")
    pkg.add_argument("--zip-path", default=None, help="Path for the output zip file (default: cheatsdownload.zip)")

    dbp = sub.add_parser("db", help="Search/display the maintained cheat database (build id, title id, name, version)")
    dbp.add_argument("--db", default="./cheats.db", help="Path to the SQLite database")
    dbp.add_argument("--search", default=None, help="Filter by game name (substring)")
    dbp.add_argument("--build-id", default=None, help="Filter by build id (substring)")
    dbp.add_argument("--title-id", default=None, help="Filter by title id (substring)")
    dbp.add_argument("--limit", type=int, default=None, help="Max rows to display")
    dbp.add_argument("--export-csv", default=None, help="Write the (filtered) rows to a CSV file instead of printing")
    dbp.add_argument("--output", default="./cheatsdownload", help="Download directory to reconcile against (shows downloaded status)")
    dbp.add_argument("--missing-only", action="store_true", help="Show only builds that are NOT downloaded yet")

    enrich = sub.add_parser(
        "enrich-titles",
        help="Fill missing game names for all title IDs on disk using titledb (no login needed)",
    )
    enrich.add_argument("--output", "-o", default="./cheatsdownload",
                        help="Directory that contains the titles/ and meta/ folders")
    enrich.add_argument("--db", default="./cheats.db",
                        help="SQLite database to update (will be created if missing)")
    enrich.add_argument("--region", default="US.en",
                        help="titledb region file to use, e.g. US.en, DE.de, JP.ja (default: US.en)")
    enrich.add_argument("--no-index", action="store_true",
                        help="Skip writing titles_index.json")

    sub.add_parser("gui", help="Open the graphical interface (scrape button + database view)")

    args = parser.parse_args()

    if args.command == "metadata":
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if args.log_file:
            enable_file_logging(args.log_file)
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        scraper = CheatslipsMetadataScraper(delay=args.delay)

        if args.game_slug:
            games = [(args.game_slug, args.game_slug)]
        else:
            games = scraper.list_all_games(max_pages=args.max_pages, workers=args.list_workers)

        print(f"Found {len(games)} games")
        results = []

        if args.workers <= 1 or len(games) <= 1:
            for idx, (slug, title) in enumerate(games, 1):
                print(f"[{idx}/{len(games)}] {title}")
                info = scraper.scrape_game_details(slug)
                if info:
                    info["title"] = info.get("title") or title
                    results.append(info)
        else:
            print(f"Scraping with {args.workers} parallel workers")
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_to_game = {
                    executor.submit(scraper.scrape_game_details, slug): (slug, title)
                    for slug, title in games
                }
                for idx, future in enumerate(as_completed(future_to_game), 1):
                    slug, title = future_to_game[future]
                    try:
                        info = future.result()
                        if info:
                            info["title"] = info.get("title") or title
                            results.append(info)
                        print(f"[{idx}/{len(games)}] {title}")
                    except Exception as exc:
                        print(f"[{idx}/{len(games)}] ERROR {title}: {exc}")

        # Sort by build_id
        results.sort(key=lambda x: x["slug"])
        for info in results:
            info["sources"].sort(key=lambda s: s["build_id"])

        index_path = out_dir / "metadata.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Saved metadata to {index_path}")

        # Flat index sorted by build ID
        by_bid: Dict[str, List[Dict]] = {}
        for info in results:
            for src in info["sources"]:
                bid = src["build_id"]
                by_bid.setdefault(bid, []).append({
                    "slug": info["slug"],
                    "title": info["title"],
                    "title_id": src["title_id"],
                    "source_id": src["source_id"],
                    "version": src.get("version"),
                    "upload_date": src.get("upload_date"),
                    "cheat_count": src.get("cheat_count"),
                    "cheat_names": src["cheat_names"],
                })
        bid_index_path = out_dir / "by_build_id.json"
        with open(bid_index_path, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(by_bid.items())), f, indent=2, ensure_ascii=False)
        print(f"Saved build-id index to {bid_index_path}")

        # Maintain the persistent SQLite database additionally.
        db = GameDatabase(Path(args.db))
        for info in results:
            db.upsert_game(info)
        print(f"Database now holds {db.count()} build(s): {Path(args.db)}")
        db.close()

    elif args.command == "download":
        if args.log_file:
            enable_file_logging(args.log_file)
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)

        db_path = Path(args.db)
        if not db_path.exists():
            print(f"ERROR: database {db_path} not found. Run 'metadata' first.")
            sys.exit(1)

        api = CheatslipsAPI(token=args.token or None)
        if not api.token:
            if args.email and args.password:
                print("Requesting API token...")
                try:
                    api.get_token(args.email, args.password)
                except Exception as exc:
                    print(f"ERROR: {exc}")
                    sys.exit(1)
            else:
                print("ERROR: provide --token, or --email and --password.")
                sys.exit(1)
        if not api.token_works():
            print("ERROR: the API token is invalid (no cheat content returned).")
            sys.exit(1)

        db = GameDatabase(db_path)
        title_ids = [args.title_id] if args.title_id else None
        try:
            api_download_from_db(
                api, db, out_dir,
                title_ids=title_ids,
                resume=not args.no_resume,
                flat_output=args.flat_output,
                progress_cb=None,
            )
        finally:
            db.close()
        print("Done.")

    elif args.command == "enrich-titles":
        out_dir = Path(args.output)
        titles_dir = out_dir / "titles"
        meta_dir = out_dir / "meta"
        db = GameDatabase(Path(args.db))

        # 1. Import all TIDs/BIDs from disk into the DB
        import_disk_titles_to_db(titles_dir, meta_dir, db)
        before = db.count()
        print(f"DB now has {before} build row(s).")

        # 2. Fill names + covers from the titledb regional eShop dump
        cache_dir = out_dir
        filled = fill_metadata_from_titledb(
            db,
            region=args.region,
            cache_dir=str(cache_dir),
        )

        # 3. Derive names for DLC/update TIDs from their base game (000 → 001/002/800)
        derive_names_from_base(db)

        # 4. Summary
        tids_with_name = db._conn.execute(
            "SELECT COUNT(DISTINCT title_id) FROM builds "
            "WHERE game_title IS NOT NULL AND game_title != ''"
        ).fetchone()[0]
        tids_total = db._conn.execute(
            "SELECT COUNT(DISTINCT title_id) FROM builds "
            "WHERE title_id IS NOT NULL AND length(title_id) = 16"
        ).fetchone()[0]
        print(f"\n=== Result ===")
        print(f"Games total     : {tids_total}")
        print(f"Names known     : {tids_with_name}")
        print(f"Names missing   : {tids_total - tids_with_name}")

        # 4. Write titles_index.json for easy reference
        if not args.no_index:
            index = {}
            rows = db._conn.execute(
                "SELECT DISTINCT title_id, game_title, slug, image, publisher, "
                "developer, release_date, category "
                "FROM builds WHERE title_id IS NOT NULL AND length(title_id) = 16 "
                "ORDER BY game_title COLLATE NOCASE"
            ).fetchall()
            for r in rows:
                tid = r[0].upper()
                if tid not in index:
                    index[tid] = {
                        "title_id": tid,
                        "name": r[1],
                        "slug": r[2],
                        "image": r[3],
                        "publisher": r[4],
                        "developer": r[5],
                        "release_date": r[6],
                        "category": r[7],
                    }
            index_path = out_dir / "titles_index.json"
            index_path.write_text(
                json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"\nIndex written: {index_path} ({len(index)} titles)")
        db.close()
        print("Done.")

    elif args.command == "package":
        out_dir = Path(args.output)
        titles_dir = out_dir / "titles"
        if not titles_dir.exists():
            print(f"ERROR: {titles_dir} does not exist. Run download first.")
            sys.exit(1)
        zip_path = Path(args.zip_path) if args.zip_path else out_dir / f"{out_dir.name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for txt in titles_dir.rglob("*.txt"):
                zf.write(txt, txt.relative_to(out_dir))
        print(f"Created {zip_path} with {len(list(titles_dir.rglob('*.txt')))} cheat files")

    elif args.command == "db":
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"ERROR: database {db_path} not found. Run 'metadata' first.")
            sys.exit(1)
        db = GameDatabase(db_path)
        rows = db.search(term=args.search, build_id=args.build_id, title_id=args.title_id)

        # Reconcile against what is actually downloaded on disk.
        downloaded = scan_downloaded_build_ids(args.output)
        if args.missing_only:
            rows = [r for r in rows if (r["build_id"] or "").upper() not in downloaded]
        if args.limit:
            rows = rows[: args.limit]
        if args.export_csv:
            n = export_rows_csv(rows, Path(args.export_csv))
            print(f"Exported {n} row(s) to {args.export_csv}")
            db.close()
            return
        if not rows:
            print("No matching entries.")
        else:
            header = f"{'DL':<3} {'Game':<40} {'Version':<9} {'Title ID':<16} {'Build ID':<16} {'Uploaded':<12} {'Cheats':>6}"
            print(header)
            print("-" * len(header))
            for r in rows:
                title = (r["game_title"] or "")[:40]
                cc = r["cheat_count"]
                flag = "OK" if (r["build_id"] or "").upper() in downloaded else "-"
                print(
                    f"{flag:<3} {title:<40} {(r['version'] or '-'):<9} "
                    f"{(r['title_id'] or '-'):<16} {(r['build_id'] or '-'):<16} "
                    f"{(r['upload_date'] or '-'):<12} {(cc if cc is not None else '-'):>6}"
                )
            have = sum(1 for r in rows if (r["build_id"] or "").upper() in downloaded)
            print(f"\n{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}; {have} downloaded, {len(rows) - have} missing.")
        db.close()

    elif args.command == "gui":
        from gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
