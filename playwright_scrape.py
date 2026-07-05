#!/usr/bin/env python3
"""Playwright-based browser automation for cheatslips.com.

Opens a real browser window, navigates to a game page, and downloads every
listed build ID. Downloads are intercepted and saved to the correct folder
structure (titles/{title_id}/cheats/{build_id}.txt).

Requires:
    pip install playwright
    playwright install
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from browser_scrape import extract_cheat_text_from_html
from scraper import save_cheat_merged, BUILD_UNAVAILABLE

BASE_URL = "https://www.cheatslips.com"

# Playwright browsers already ensured this session (avoid repeat installs).
_BROWSERS_READY = set()


def install_browsers(targets, log: Callable[[str], None] = print) -> bool:
    """Download the given Playwright browsers ('chromium'/'firefox') so the app
    ships them itself and the user never has to run 'playwright install'.
    Returns True on success. Results are cached per session."""
    todo = [t for t in targets if t not in _BROWSERS_READY]
    if not todo:
        return True
    log(f"Installing Playwright browser(s): {', '.join(todo)} — one-time download, please wait...")
    try:
        if getattr(sys, "frozen", False):
            # In a packaged .exe, sys.executable is the app itself — "-m
            # playwright" won't work. Call Playwright's bundled node driver
            # directly instead (installs into PLAYWRIGHT_BROWSERS_PATH).
            from playwright._impl._driver import compute_driver_executable, get_driver_env
            drv = compute_driver_executable()
            cmd = list(drv) if isinstance(drv, (list, tuple)) else [drv]
            r = subprocess.run(cmd + ["install", *todo], capture_output=True,
                               text=True, timeout=900, env=get_driver_env())
        else:
            r = subprocess.run([sys.executable, "-m", "playwright", "install", *todo],
                               capture_output=True, text=True, timeout=900)
        if r.returncode == 0:
            _BROWSERS_READY.update(todo)
            log("Browser install finished.")
            return True
        log(f"Browser install failed (exit {r.returncode}): "
            f"{((r.stderr or r.stdout) or '').strip()[:300]}")
    except Exception as exc:
        log(f"Browser install error: {exc}")
    return False


def _needs_browser_install(exc) -> bool:
    """True if a launch error means the Playwright browser isn't downloaded yet."""
    m = str(exc).lower()
    return ("executable doesn" in m or "playwright install" in m
            or "looks like playwright" in m or "please run the following" in m)


def ensure_browsers_installed(kinds=("chromium", "firefox"), log: Callable[[str], None] = print) -> bool:
    """Best-effort: make sure the bundled browsers are present (call once at
    startup). Chrome/Edge use the user's own install and need nothing here."""
    return install_browsers([k for k in kinds if k in ("chromium", "firefox")], log)

_HERE = Path(__file__).resolve().parent
# App data directory — shared with gui.py via SCS_DATA_DIR so the login profile
# lands in the per-user data folder when running as a packaged .exe.
_DATA_DIR = Path(os.environ.get("SCS_DATA_DIR") or _HERE)
# Dedicated, persistent browser profile. Logging in once (and solving the
# reCAPTCHA once) keeps the session here so future runs and every in-run quota
# reset need no further login. This is independent of the user's Firefox/Chrome.
PROFILE_DIR = _DATA_DIR / "browser_profile"
STORAGE_FILE = PROFILE_DIR / "storage_state.json"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# Common installed Chromium/Chrome/Edge paths on Windows
_WINDOWS_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_installed_browser() -> Optional[str]:
    """Return the path to an installed Chrome/Edge executable, or None."""
    for path in _WINDOWS_CHROME_PATHS:
        if isinstance(path, Path):
            if path.exists():
                return str(path)
        else:
            if os.path.exists(path):
                return path
    return None


def _chrome_user_data_dir() -> Optional[Path]:
    """Return the default Chrome user data directory on Windows, if it exists."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    p = Path(local_appdata) / "Google" / "Chrome" / "User Data"
    if p.exists():
        return p
    return None


def _copy_profile_for_playwright(source: Path, log: Callable[[str], None]) -> Optional[Path]:
    """Copy the Chrome profile to a temp dir so Playwright can use it without conflicts.

    Returns the temp profile directory or None if copying failed.
    """
    import tempfile
    import shutil
    try:
        tmp = Path(tempfile.mkdtemp(prefix="cheatslips_profile_"))
        shutil.copytree(source, tmp / "User Data")
        log(f"Copied Chrome profile to {tmp}")
        return tmp / "User Data"
    except Exception as exc:
        log(f"Could not copy Chrome profile: {exc}")
        return None


def _load_storage_state(context, page, log=print) -> None:
    """Restore cookies and localStorage from STORAGE_FILE into the browser.

    Session-only state is not written to disk by Chromium on close, so we save
    it explicitly and inject it back on the next start. This keeps the user
    logged in across runs.
    """
    if not STORAGE_FILE.exists():
        log("  No saved browser session state yet.")
        return
    try:
        data = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
        cookies = data.get("cookies", [])
        origins = data.get("origins", [])
        if cookies:
            context.add_cookies(cookies)
            log(f"  Restored {len(cookies)} cookie(s).")
        if origins:
            for origin in origins:
                url = origin.get("origin")
                items = origin.get("localStorage", [])
                if not url or not items:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    page.evaluate(
                        """(items) => {
                            for (const {name, value} of items) {
                                localStorage.setItem(name, value);
                            }
                        }""",
                        items,
                    )
                    log(f"  Restored {len(items)} localStorage item(s) for {url}.")
                except Exception as exc:
                    log(f"  Could not restore localStorage for {url}: {exc}")
        if not cookies and not origins:
            log("  Saved session state file is empty.")
    except Exception as exc:
        log(f"  Could not restore session state: {exc}")


def _save_storage_state(context, log=print) -> None:
    """Persist the current browser context state (cookies + localStorage)."""
    try:
        state = context.storage_state()
        STORAGE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        cookies = state.get("cookies", [])
        origins = state.get("origins", [])
        total_ls = sum(len(o.get("localStorage", [])) for o in origins)
        log(f"  Saved {len(cookies)} cookie(s) and {total_ls} localStorage item(s) for next session.")
    except Exception as exc:
        log(f"  Could not save session state: {exc}")


def _launch_browser(p, headless: bool, use_installed: bool, log: Callable[[str], None]):
    """Launch Chromium and return (browser, context).

    Optionally uses the user's installed browser/profile so they can stay logged in.
    """
    args = [
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
        "--disable-features=RestoreSessionState",
        "--no-first-run",
        "--disable-default-apps",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-notifications",
    ]
    if use_installed:
        exe = find_installed_browser()
        if exe:
            log(f"Using installed browser: {exe}")
            profile_dir = _chrome_user_data_dir()
            if profile_dir:
                copied = _copy_profile_for_playwright(profile_dir, log)
                if copied:
                    try:
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=str(copied),
                            executable_path=exe,
                            headless=headless,
                            args=args,
                            viewport={"width": 1280, "height": 900},
                            user_agent=_UA,
                        )
                        return None, context
                    except Exception as exc:
                        log(f"Could not launch installed browser profile: {exc}; falling back to bundled Chromium.")
            try:
                browser = p.chromium.launch(executable_path=exe, headless=headless, args=args)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=_UA,
                )
                return browser, context
            except Exception as exc:
                log(f"Could not launch installed browser: {exc}; falling back to bundled Chromium.")
        else:
            log("No installed Chrome/Edge found; using bundled Chromium.")
    # Incognito only for bundled Chromium to avoid restore dialog
    args.append("--incognito")
    browser = p.chromium.launch(headless=headless, args=args)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=_UA,
    )
    return browser, context

# Common cookie/consent banner button texts (case-insensitive)
_CONSENT_BUTTONS = [
    "accept all", "accept", "agree", "i agree", "i understand", "continue",
    "got it", "dismiss", "allow", "allow all", "save preferences", "yes, i agree",
    "einverstanden", "akzeptieren", "alle akzeptieren", "verstanden", "weiter",
    "zustimmen", "alle zustimmen",
]

_HEX_PAIR_RE = re.compile(r"\b[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}\b")
_HEADER_RE = re.compile(r"^[\[{].+?[\]}]$")


def _looks_like_cheat(text: str) -> bool:
    return bool(text) and bool(_HEX_PAIR_RE.search(text))


def _extract_cheat_text(data: bytes) -> Optional[str]:
    """Try to decode bytes as a cheat text file."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    if _looks_like_cheat(text):
        return text
    return None


def _extract_zip(data: bytes) -> Optional[str]:
    """Extract the best cheat .txt file from a ZIP."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return None
    best_name, best_content = None, ""
    for info in zf.infolist():
        if info.is_dir():
            continue
        try:
            content = zf.read(info).decode("utf-8", errors="replace")
        except Exception:
            continue
        if _looks_like_cheat(content) and len(content) > len(best_content):
            best_content = content
            best_name = info.filename
    return best_content if best_content else None


def _parse_downloaded_content(data: bytes, log: Callable[[str], None]) -> Optional[str]:
    """Turn downloaded bytes into cheat text (ZIP or plain text)."""
    if data[:4] == b"PK\x03\x04":
        return _extract_zip(data)
    return _extract_cheat_text(data)


def _save_cheat_file(title_id: str, build_id: str, content: str, out_dir: Path) -> str:
    save_dir = out_dir / "titles" / title_id / "cheats"
    save_dir.mkdir(parents=True, exist_ok=True)
    path = save_dir / f"{build_id}.txt"
    save_cheat_merged(path, content)
    return str(path)


def _session_from_playwright(context, log: Callable[[str], None]):
    """Create a requests.Session with cookies from the Playwright browser context."""
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        cookies = context.cookies()
        log(f"Browser cookies: {cookies}")
        cookie_header = []
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            domain = c.get("domain", "www.cheatslips.com")
            path = c.get("path", "/")
            if name and value:
                s.cookies.set(name, value, domain=domain, path=path)
                cookie_header.append(f"{name}={value}")
        if cookie_header:
            s.headers["Cookie"] = "; ".join(cookie_header)
        log(f"Transferred {len(cookies)} cookie(s). Cookie header: {s.headers.get('Cookie','')[:80]}...")
    except Exception as exc:
        log(f"Could not transfer cookies: {exc}")
    return s


def _post_download_with_session(session, page_url: str, html: str,
                                 log: Callable[[str], None]) -> Optional[bytes]:
    """Parse the page for the download form (CSRF + action=download) and POST it via requests.

    Returns the response bytes (ZIP or text) or None.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        log("    BeautifulSoup not available — cannot parse download form.")
        return None
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form")
    if not form:
        log("    No form found on page.")
        return None
    dl_btn = None
    for btn in form.find_all("button"):
        if (btn.get("value") or "").lower() == "download":
            dl_btn = btn
            break
    if not dl_btn:
        log("    No download button in form.")
        return None
    data = {}
    for inp in form.find_all("input"):
        n = inp.get("name")
        if n:
            data[n] = inp.get("value", "")
    if dl_btn.get("name"):
        data[dl_btn["name"]] = dl_btn.get("value", "")
    full = page_url if page_url.startswith("http") else BASE_URL + page_url
    log(f"    POST {full} with data={list(data.keys())}")
    r = session.post(full, data=data, timeout=60, allow_redirects=True)
    log(f"    Response: {r.status_code}, Content-Type={r.headers.get('Content-Type','?')}, len={len(r.content)}")
    if r.status_code != 200:
        return None
    return r.content


def _find_source_build_pairs(html: str, slug: str) -> List[tuple]:
    """Scrape (page_id, build_id) pairs from the game page.

    cheatslips lists builds as cards. Each card links to the actual download page
    either via a numeric source_id (e.g. /game/{slug}/4657) or directly via the
    16-hex build_id (e.g. /game/{slug}/FA3FB8D6C8B648EB). The page_id returned
    here is used to navigate to the correct download page.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []

    pairs = []
    # Each build is typically in a .card with a link to /game/{slug}/{page_id}
    # page_id can be a numeric source_id OR a 16-hex build_id.
    source_re = rf"/game/{re.escape(slug)}/(\d+)(?![0-9A-Fa-f])"
    build_url_re = rf"/game/{re.escape(slug)}/([0-9A-Fa-f]{{16}})"
    for card in soup.find_all("div", class_="card"):
        # Find page_id from the play/link button inside the card
        page_id = None
        for a in card.find_all("a", href=True):
            m = re.search(source_re, a["href"])
            if m:
                page_id = m.group(1)
                break
            m = re.search(build_url_re, a["href"])
            if m:
                page_id = m.group(1).upper()
                break
        # Find build_id in the card text
        build_id = None
        text = card.get_text(" ")
        for m in re.finditer(r"\b[0-9A-Fa-f]{16}\b", text):
            bid = m.group(0).upper()
            # Title IDs start with 0100; skip those if they appear in the card.
            if bid.startswith("0100"):
                continue
            build_id = bid
            break
        if page_id and build_id:
            pairs.append((page_id, build_id))

    # "Game releases" table: each row lists a build that has cheats but is not
    # shown as a featured cheat card. Rows link to /game/{slug}/{build_id} (a
    # landing page that in turn links to the numeric cheat page), so include them
    # too — otherwise builds that only appear in this table are never downloaded.
    # _download_build follows the build-id landing page to the numeric page.
    seen_bids = {b.upper() for _, b in pairs if b}
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "build id" not in headers:
            continue
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            m = re.search(r"\b([0-9A-Fa-f]{16})\b", tds[0].get_text(" "))
            if not m:
                continue
            bid = m.group(1).upper()
            # Title IDs start with 0100; they are not build ids.
            if bid.startswith("0100") or bid in seen_bids:
                continue
            # Prefer an explicit page link in the row; else use the build-id URL.
            page_id = bid
            for a in tr.find_all("a", href=True):
                sm = re.search(source_re, a["href"])
                if sm:
                    page_id = sm.group(1)
                    break
                bm = re.search(build_url_re, a["href"])
                if bm:
                    page_id = bm.group(1).upper()
                    break
            pairs.append((page_id, bid))
            seen_bids.add(bid)

    # Fallback: if no cards/table rows found, scan all /game/{slug}/{page_id} links
    if not pairs:
        seen = set()
        for a in soup.find_all("a", href=True):
            m = re.search(source_re, a["href"])
            if m:
                sid = m.group(1)
                if sid not in seen:
                    seen.add(sid)
                    pairs.append((sid, None))
            else:
                m = re.search(build_url_re, a["href"])
                if m:
                    bid = m.group(1).upper()
                    if bid not in seen:
                        seen.add(bid)
                        pairs.append((bid, None))

    return pairs


def _handle_consent_banners(page, log: Callable[[str], None]):
    """Try to click common cookie/consent banners automatically.

    Fast path: if none of the known banner containers or buttons are visible
    within 200 ms, we assume there is no banner and return immediately.
    """
    # Fast pre-check: look for any known accept button with a very short timeout.
    quick_selectors = [
        "button:has-text('Consent')",
        "button:has-text('Accept all')",
        "button:has-text('Accept')",
        "button:has-text('Agree')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Alle akzeptieren')",
        "#onetrust-accept-btn-handler",
        "#cookie-accept",
        "#consent-accept",
        "#cc-accept",
        "#CybotCookiebotDialogBodyButtonAccept",
        "#accept-cookie",
        ".cc-accept",
        ".cookie-accept",
        "button[aria-label*='accept' i]",
        "button[aria-label*='cookie' i]",
    ]
    try:
        if not page.locator(", ".join(quick_selectors)).first.is_visible(timeout=200):
            return
    except Exception:
        return

    clicked = False
    # First pass: EXACT-text accept buttons. This avoids ever matching the
    # opposite "Do not consent" button via substring matching. cheatslips shows
    # an IAB consent dialog whose accept button is just "Consent".
    for exact in ("Consent", "Accept all", "Accept All", "Accept", "Agree",
                  "I agree", "Einverstanden", "Akzeptieren", "Alle akzeptieren"):
        try:
            loc = page.get_by_role("button", name=exact, exact=True).first
            if loc.is_visible(timeout=200):
                loc.click(timeout=1000)
                log(f"    Clicked consent banner (exact): '{exact}'")
                time.sleep(0.2)
                return
        except Exception:
            continue
    for text in _CONSENT_BUTTONS:
        selectors = [
            f"button:has-text('{text}')",
            f"a:has-text('{text}')",
            f"[role='button']:has-text('{text}')",
            f"input[type='button'][value='{text}' i]",
            f"input[type='submit'][value='{text}' i]",
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.is_visible(timeout=200):
                    loc.click(timeout=1000)
                    log(f"    Clicked consent banner: '{text}'")
                    clicked = True
                    time.sleep(0.2)
                    break
            except Exception:
                continue
        if clicked:
            break


def _find_download_button(page, log: Callable[[str], None]):
    """Return the locator for the download button on the page, or None."""
    # Try specific selectors first
    for selector in [
        "button[name='action'][value='download']",
        "button[value='download']",
        "form[method='post'] button:has-text('Download')",
        "button:has-text('Download')",
        "a:has-text('Download')",
        "button .fa-download",
        "a .fa-download",
    ]:
        loc = page.locator(selector).first
        try:
            if loc.is_visible(timeout=1500):
                log(f"    Found download button via selector: {selector}")
                return loc
        except Exception:
            continue
    # Try to find by button text inside any form
    try:
        buttons = page.locator("button").all()
        for btn in buttons:
            txt = (btn.inner_text() or "").strip().lower()
            if "download" in txt:
                if btn.is_visible():
                    log(f"    Found download button by text: {txt!r}")
                    return btn
    except Exception:
        pass
    return None


def _download_build(page, source_id: str, build_id: Optional[str], slug: str,
                    title_id: str, out_dir: Path, log: Callable[[str], None],
                    depth: int = 0, reset_cb: Optional[Callable[[], bool]] = None,
                    quota_retries: int = 0) -> Optional[str]:
    """Navigate to the source build page in the browser and use the browser's
    fetch API to POST the download form. This keeps the logged-in session intact.

    Some builds (often older ones) are reached via a build-id URL such as
    /game/{slug}/9A318D7FC3DD902F, which is only a landing page that links to the
    real numeric cheat page (/game/{slug}/3385). When no download form is found
    there, we follow that numeric link once and retry (controlled by ``depth``).

    When the website download limit is hit, cheatslips serves a codeless
    "preview" ZIP (cheat names only, no code lines). If ``reset_cb`` is given we
    reset the quota and retry once (controlled by ``quota_retries``).
    """
    url = f"{BASE_URL}/game/{slug}/{source_id}"
    log(f"  Navigating to source page {url} (build_id={build_id})")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:
        log(f"    Could not load page: {exc}")
        return None

    _handle_consent_banners(page, log)

    # Wait a moment for any JavaScript-rendered download form to appear.
    try:
        page.wait_for_selector('form:has(button[value="download"]), form:has(.fa-download), button[value="download"], a:has(.fa-download)', timeout=3000)
    except Exception:
        pass

    # Extract the build_id and form data from the rendered page.
    # We search every form for a download button and accept several common
    # button/link styles (button[value="download"], .fa-download icons, etc.).
    info = page.evaluate("""
        () => {
            const result = { build_id: null, csrf: null, action: null, has_download: false };
            const text = document.body.innerText;
            const m = text.match(/Build Id\\s*[:\\-]?\\s*([0-9A-Fa-f]{16})/i);
            if (m) result.build_id = m[1].toUpperCase();

            const csrfByName = (root, name) => {
                const el = root.querySelector('input[name="' + name + '"]');
                return el ? el.value : null;
            };

            const isDownloadBtn = (el) => {
                if (!el) return false;
                const val = (el.value || "").toLowerCase();
                const txt = (el.innerText || el.textContent || "").toLowerCase();
                const cls = (el.className || "").toLowerCase();
                return val === "download" || txt.includes("download") || cls.includes("fa-download");
            };

            const forms = Array.from(document.querySelectorAll('form'));
            for (const form of forms) {
                const btns = Array.from(form.querySelectorAll('button, input[type="submit"], a'));
                const dlBtn = btns.find(isDownloadBtn);
                if (dlBtn) {
                    result.has_download = true;
                    result.action = dlBtn.name || 'action';
                    // CSRF token may be named csrf_token or csrf.
                    result.csrf = csrfByName(form, "csrf_token") || csrfByName(form, "csrf");
                    // If not found in the form, look in the whole page (some sites put it in a meta tag).
                    if (!result.csrf) {
                        result.csrf = csrfByName(document, "csrf_token") || csrfByName(document, "csrf");
                    }
                    break;
                }
            }
            return result;
        }
    """)
    log(f"    Page info: {info}")

    if not info.get("has_download"):
        # The build-id URL is often just a landing page that links to the real
        # numeric cheat page (e.g. /game/{slug}/3385). Follow that link once.
        if depth == 0:
            numeric_id = page.evaluate(
                """
                (slug) => {
                    const re = new RegExp('/game/' + slug + '/(\\\\d+)(?![0-9A-Fa-f])');
                    for (const a of document.querySelectorAll('a[href]')) {
                        const m = (a.getAttribute('href') || '').match(re);
                        if (m) return m[1];
                    }
                    return null;
                }
                """,
                slug,
            )
            if numeric_id and str(numeric_id) != str(source_id):
                log(f"    No form on build-id page; following link to numeric page_id={numeric_id}")
                return _download_build(page, str(numeric_id), build_id, slug,
                                       title_id, out_dir, log, depth + 1,
                                       reset_cb=reset_cb, quota_retries=quota_retries)
        log(f"    No download form found for page_id={source_id} — trying HTML extraction...")
        html = page.content()
        text = extract_cheat_text_from_html(html)
        if text:
            log(f"    Extracted cheat text from page HTML ({len(text)} bytes)")
            path = _save_cheat_file(title_id, build_id, text, out_dir)
            log(f"    ✓ Saved {build_id} -> {path} ({len(text)} bytes)")
            return path
        try:
            debug_dir = Path("browser_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{build_id or source_id}_no_download.html").write_text(html, encoding="utf-8")
            log(f"    Debug saved to browser_debug/{build_id or source_id}_no_download.html")
        except Exception:
            pass
        log(f"    No cheat text found in page HTML for page_id={source_id} "
            f"(no cheat available on cheatslips for this build)")
        return BUILD_UNAVAILABLE

    if not build_id:
        build_id = info.get("build_id")
        if build_id:
            log(f"    Extracted build_id from page: {build_id}")
    if not build_id:
        log(f"    Could not determine build_id for page_id={source_id}")
        return None

    csrf = info.get("csrf")
    action_name = info.get("action") or "action"
    if not csrf:
        log(f"    No CSRF token found for page_id={source_id} — trying HTML extraction...")
        html = page.content()
        text = extract_cheat_text_from_html(html)
        if text:
            log(f"    Extracted cheat text from page HTML ({len(text)} bytes)")
            path = _save_cheat_file(title_id, build_id, text, out_dir)
            log(f"    ✓ Saved {build_id} -> {path} ({len(text)} bytes)")
            return path
        log(f"    No cheat text found in page HTML for page_id={source_id}")
        return BUILD_UNAVAILABLE

    # Use the browser's fetch API to POST the form with the active session
    js_url = f"/game/{slug}/{source_id}"
    log(f"    POSTing download form via browser fetch...")
    try:
        b64data = page.evaluate("""
            async ({url, csrf, action_name}) => {
                const body = new URLSearchParams();
                body.append('csrf_token', csrf);
                body.append(action_name, 'download');
                const resp = await fetch(url, {
                    method: 'POST',
                    body: body,
                    credentials: 'same-origin',
                    headers: { 'Accept': 'text/html,application/xhtml+xml' }
                });
                const buf = await resp.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let binary = '';
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return btoa(binary);
            }
        """, {"url": js_url, "csrf": csrf, "action_name": action_name})
        data = base64.b64decode(b64data)
    except Exception as exc:
        log(f"    Browser fetch failed: {exc}")
        return None

    content = _parse_downloaded_content(data, log)
    if not content:
        # A ZIP with no code lines is cheatslips' download-limit "preview"
        # (cheat names only). Reset the quota and retry once before giving up.
        is_zip = data[:4] == b"PK\x03\x04"
        if is_zip and reset_cb and quota_retries < 1:
            log(f"    Download had no cheat codes for {build_id} — likely the website "
                f"download limit; resetting quota and retrying...")
            if reset_cb():
                return _download_build(page, source_id, build_id, slug, title_id,
                                       out_dir, log, depth=depth, reset_cb=reset_cb,
                                       quota_retries=quota_retries + 1)
            log("    Quota reset failed — cannot retry the browser download.")
        log(f"    Response was not a valid cheat for {build_id} ({len(data)} bytes)")
        try:
            debug_dir = Path("browser_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{build_id}_response.bin").write_bytes(data)
            log(f"    Raw response saved to browser_debug/{build_id}_response.bin")
        except Exception:
            pass
        if is_zip:
            # A valid ZIP that still has no code lines after a quota reset means
            # the upload itself is codeless — mark it so future runs skip it.
            log(f"    (ZIP contained only cheat names, no code lines — the upload "
                f"itself has no codes; marking build as unavailable.)")
            return BUILD_UNAVAILABLE
        # A non-ZIP response (HTML error/redirect) is likely transient — let the
        # caller retry it on a later run rather than marking it unavailable.
        return None

    path = _save_cheat_file(title_id, build_id, content, out_dir)
    log(f"    ✓ Saved {build_id} -> {path} ({len(content)} bytes)")
    return path


def _fill_login_form(page, email: Optional[str], password: Optional[str],
                     log: Callable[[str], None]) -> bool:
    """Auto-fill the cheatslips login form with email/password if fields exist."""
    if not email or not password:
        log("No email/password configured in GUI — please enter them manually in the browser.")
        return False
    try:
        email_field = page.locator("input[name='email'], input[type='email'], input#email").first
        pw_field = page.locator("input[name='password'], input[type='password'], input#password").first
        if email_field.is_visible(timeout=500) and pw_field.is_visible(timeout=500):
            email_field.fill(email)
            pw_field.fill(password)
            log("Email and password filled automatically.")
            return True
    except Exception as exc:
        log(f"Could not auto-fill login form: {exc}")
    return False


def _try_auto_recaptcha(page, log: Callable[[str], None]) -> bool:
    """Try to click the reCAPTCHA checkbox and wait for it to solve itself.

    This is best-effort: if reCAPTCHA shows an image challenge or detects the
    automation, it falls back to manual solving. Returns True only if the
    checkbox appears to be checked automatically.
    """
    try:
        checkbox = page.frame_locator('iframe[title="reCAPTCHA"]').locator(
            '.recaptcha-checkbox-border').first
        if not checkbox.is_visible(timeout=500):
            return False
        checkbox.click(timeout=1000)
        log("Clicked reCAPTCHA checkbox — waiting for automatic solve...")
        # Wait up to 15 seconds for the checked state to appear.
        for _ in range(30):
            try:
                checked = page.frame_locator('iframe[title="reCAPTCHA"]').locator(
                    '.recaptcha-checkbox-checked').first
                if checked.is_visible(timeout=500):
                    log("reCAPTCHA solved automatically.")
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        log("reCAPTCHA did not solve automatically — manual solve needed.")
    except Exception as exc:
        log(f"Could not click reCAPTCHA checkbox: {exc}")
    return False


def _click_login_button(page, log: Callable[[str], None]) -> bool:
    """Click the login form submit button, if visible."""
    try:
        btn = page.locator(
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Login'), button:has-text('Sign in'), "
            "button:has-text('Log in')"
        ).first
        if btn.is_visible(timeout=500):
            btn.click(timeout=1000)
            log("Clicked login button.")
            return True
    except Exception as exc:
        log(f"Could not click login button: {exc}")
    return False


def _wait_for_login(page, email: Optional[str], password: Optional[str],
                    log: Callable[[str], None], should_stop, timeout_seconds: int = 300) -> bool:
    """Open login page, fill credentials, and wait until user is logged in."""
    login_url = f"{BASE_URL}/login"
    log(f"Opening login page: {login_url}")
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    # Handle consent banners only on the login page; after login we stop clicking
    # random buttons to avoid closing the browser by accident.
    _handle_consent_banners(page, log)

    filled = _fill_login_form(page, email, password, log)
    if filled:
        recaptcha_ok = _try_auto_recaptcha(page, log)
        if recaptcha_ok:
            _click_login_button(page, log)
            log("Login form submitted — waiting for redirect...")
        else:
            log("Please solve the reCAPTCHA and click the login button (or press Enter).")
            log("The tool will continue automatically once you are logged in.")
    else:
        log("Please log in manually in the browser.")

    log("Waiting for successful login (download button visible on a game page)...")
    for _ in range(timeout_seconds):
        if should_stop and should_stop():
            log("Stopped by user.")
            return False
        # Detect login success by checking account/logout links or absence of login form
        try:
            html = page.content()
            # Only accept clear markers, not "Create an account" on the login page
            lower = html.lower()
            if any(x in lower for x in ["logout", ">my account<", ">subscription<"]):
                log("Login detected (account page / logout link visible).")
                _save_storage_state(page.context, log=log)
                return True
            # If the login form is gone and a user menu is present, we are logged in
            if ("href=\"/login\"" not in lower and
                ("href=\"/account\"" in lower or "href=\"/logout\"" in lower)):
                log("Login detected (login link gone, account/logout link present).")
                _save_storage_state(page.context, log=log)
                return True
            # If user navigated to a game page, look for download button
            btn = _find_download_button(page, log)
            if btn:
                log("Login detected (download button on game page).")
                _save_storage_state(page.context, log=log)
                return True
        except Exception:
            pass
        time.sleep(1)
    log("Timeout: login was not detected. Make sure you logged in.")
    return False


def scrape_game_page(slug: str, title_id: str, out_dir: Path,
                     email: Optional[str] = None,
                     password: Optional[str] = None,
                     log: Callable[[str], None] = print,
                     headless: bool = False,
                     should_stop: Optional[Callable[[], bool]] = None,
                     use_installed_browser: bool = False) -> List[str]:
    """Open a browser, log in, then navigate to a game page and download all listed builds.

    Returns a list of saved file paths.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is not installed. Install it with:\n"
            "    pip install playwright\n"
            "    playwright install") from exc

    saved_paths: List[str] = []
    game_url = f"{BASE_URL}/game/{slug}"

    with sync_playwright() as p:
        browser, context = _launch_browser(p, headless, use_installed_browser, log)
        page = context.new_page()

        # Step 1: Login (auto-fill credentials, wait for user to solve reCAPTCHA)
        logged_in = _wait_for_login(page, email, password, log, should_stop)
        if not logged_in:
            context.close()
            if browser:
                browser.close()
            return saved_paths

        # Step 2: Navigate to the game page in the browser and find build IDs
        log(f"Navigating to game page: {game_url}")
        try:
            page.goto(game_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            log(f"Could not navigate to game page: {exc}")
            context.close()
            if browser:
                browser.close()
            return saved_paths
        _handle_consent_banners(page, log)

        game_html = page.content()
        pairs = _find_source_build_pairs(game_html, slug)
        log(f"Found {len(pairs)} build(s) on the page: {pairs}")

        if should_stop and should_stop():
            context.close()
            if browser:
                browser.close()
            return saved_paths

        # Step 3: Download each build using the browser's logged-in session
        for source_id, build_id in pairs:
            if should_stop and should_stop():
                log("Stopped by user.")
                break
            try:
                path = _download_build(page, source_id, build_id, slug, title_id, out_dir, log)
                if path and path != BUILD_UNAVAILABLE:
                    saved_paths.append(path)
            except Exception as exc:
                log(f"  ERROR downloading source_id={source_id}: {exc}")
            time.sleep(0.5)

        context.close()
        if browser:
            browser.close()

    log(f"Playwright scrape done — {len(saved_paths)}/{len(pairs)} build(s) saved.")
    return saved_paths


def _click_reset_button(page, log: Callable[[str], None]) -> bool:
    """On the quota reset page, find and click the reset button. Returns True if clicked."""
    clicked = False
    try:
        for selector in [
            "button:has-text('Reset')",
            "input[type='submit']:has-text('Reset')",
            "button[value='reset']",
            "button[name='reset']",
            "form button",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    txt = (btn.inner_text() or "").strip().lower()
                    if "reset" in txt or "reset" in (btn.get_attribute("value") or "").lower():
                        btn.click(timeout=1000)
                        log(f"Clicked reset button: {txt!r}")
                        clicked = True
                        break
            except Exception:
                continue
        if not clicked:
            btn = page.locator("form button").first
            if btn.is_visible(timeout=500):
                btn.click(timeout=1000)
                log("Clicked first form button (reset fallback).")
                clicked = True
    except Exception as exc:
        log(f"Could not click reset button: {exc}")
    if clicked:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
    return clicked


class BrowserSession:
    """A long-lived, logged-in browser used to reset the API quota and to
    download cheats directly from the website when the API is rate-limited.

    Open it ONCE at the start of a download run and reuse it. Login (and the
    reCAPTCHA) happen a single time; afterwards every quota reset is just one
    click in the already-authenticated window. The login is stored in a
    dedicated persistent profile (``browser_profile/``) so it survives restarts.

    Typical use::

        with BrowserSession(email, password, log=print) as bs:
            bs.reset_quota()
            bs.download_build(slug, title_id, build_id, out_dir, source_id)
    """

    def __init__(self, email: Optional[str] = None, password: Optional[str] = None,
                 log: Callable[[str], None] = print, headless: bool = False,
                 use_installed_browser: bool = False, browser: Optional[str] = None,
                 should_stop: Optional[Callable[[], bool]] = None):
        self.email = email
        self.password = password
        self.log = log
        self.headless = headless
        # Which browser to drive: "builtin" (bundled Chromium), "chrome", "edge"
        # or "firefox". Falls back to the old use_installed_browser flag.
        self.browser = (browser or ("chrome" if use_installed_browser else "builtin")).lower()
        self.should_stop = should_stop
        self._pw = None
        self._context = None
        self._page = None
        self._logged_in = False

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *exc):
        self.close()

    def start(self) -> "BrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright is not installed. Install it with:\n"
                "    pip install playwright\n"
                "    playwright install") from exc
        self._pw = sync_playwright().start()
        self._context = self._launch_persistent()
        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()
        _load_storage_state(self._context, self._page, log=self.log)
        return self

    def _launch_persistent(self):
        chromium_args = [
            "--disable-session-crashed-bubble",
            "--disable-restore-session-state",
            "--disable-features=RestoreSessionState",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-notifications",
        ]
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        common = dict(
            user_data_dir=str(PROFILE_DIR),
            headless=self.headless,
            viewport={"width": 1280, "height": 900},
            user_agent=_UA,
            accept_downloads=True,
        )
        b = self.browser

        def _chromium():
            return self._pw.chromium.launch_persistent_context(args=chromium_args, **common)

        def _firefox():
            return self._pw.firefox.launch_persistent_context(**common)

        if b == "firefox":
            self.log("Launching persistent profile (Firefox)")
            try:
                # Firefox uses Playwright's own build — auto-installed if missing.
                return self._launch_auto(_firefox, "firefox")
            except Exception as exc:
                self.log(f"Firefox unavailable ({exc}); using bundled Chromium instead.")
                return self._launch_auto(_chromium, "chromium")
        if b in ("chrome", "edge"):
            channel = "chrome" if b == "chrome" else "msedge"
            self.log(f"Launching persistent profile with installed {b} (channel={channel})")
            try:
                # Channels drive the user's OWN Chrome/Edge — nothing to install.
                return self._pw.chromium.launch_persistent_context(
                    args=chromium_args, channel=channel, **common)
            except Exception as exc:
                self.log(f"{b} not available ({exc}); using bundled Chromium.")
                return self._launch_auto(_chromium, "chromium")
        self.log(f"Launching persistent profile (bundled Chromium) at {PROFILE_DIR}")
        return self._launch_auto(_chromium, "chromium")

    def _launch_auto(self, launcher, target):
        """Launch, and if the Playwright browser isn't downloaded yet, install it
        automatically and retry once — so the user never has to do it manually."""
        try:
            return launcher()
        except Exception as exc:
            if _needs_browser_install(exc) and install_browsers([target], self.log):
                return launcher()
            raise

    # -- auth --------------------------------------------------------------
    def _is_logged_in_now(self) -> bool:
        try:
            url = (self._page.url or "").lower()
            if "/login" in url:
                return False
            html = self._page.content().lower()
            return any(x in html for x in (
                "logout", ">my account<", ">subscription<",
                "href=\"/logout\"", "href=\"/account\"",
            ))
        except Exception:
            return False

    def ensure_login(self) -> bool:
        """Make sure the browser is logged in. Returns True if logged in."""
        if self._logged_in:
            return True
        try:
            self._page.goto(f"{BASE_URL}/account", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        if self._is_logged_in_now():
            self.log("Already logged in (persistent profile).")
            self._logged_in = True
            _save_storage_state(self._context, log=self.log)
            return True
        # Not logged in: fill credentials and wait for the user to solve the
        # reCAPTCHA / finish the login in the visible window.
        ok = _wait_for_login(self._page, self.email, self.password, self.log, self.should_stop)
        self._logged_in = ok
        return ok

    # -- actions -----------------------------------------------------------
    def reset_quota(self) -> bool:
        """Navigate to the quota reset page and click reset. Returns success."""
        if not self.ensure_login():
            self.log("Cannot reset quota — not logged in.")
            return False
        reset_url = f"{BASE_URL}/profile/quota/reset"
        try:
            self._page.goto(reset_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            self.log(f"Could not open reset page: {exc}")
            return False
        clicked = _click_reset_button(self._page, self.log)
        if clicked:
            self.log("Quota reset submitted.")
        else:
            self.log("Could not find the reset button.")
        return clicked

    def download_build(self, slug: str, title_id: str, build_id: Optional[str],
                       out_dir, source_id: Optional[str] = None) -> Optional[str]:
        """Download a build via the browser.

        cheatslips frequently splits a build's cheats across SEVERAL source pages
        (e.g. /game/{slug}/4068 … 4072), each holding *different* codes. We
        therefore fetch **all** of them and merge them into one file — otherwise
        real cheats are missed and the build gets wrongly marked 'unavailable'.

        Returns the saved path, ``None`` (transient — retry later) or
        ``BUILD_UNAVAILABLE`` (no codes on ANY source).
        """
        if not self.ensure_login():
            return None
        out = Path(out_dir)
        source_ids = self._source_ids_for_build(slug, build_id, source_id)
        if not source_ids:
            self.log(f"  No source page found for {title_id}/{build_id}.")
            return None
        self.log(f"  {title_id}/{build_id}: {len(source_ids)} source page(s) {source_ids}")
        saved = None
        any_unavailable = any_transient = False
        for sid in source_ids:
            if self.should_stop and self.should_stop():
                break
            # Each _download_build merges its codes into titles/{tid}/cheats/{bid}.txt.
            r = _download_build(self._page, str(sid), build_id, slug, title_id, out,
                                self.log, reset_cb=self.reset_quota)
            if r == BUILD_UNAVAILABLE:
                any_unavailable = True
            elif r:
                saved = r
            else:
                any_transient = True
        if saved:
            return saved                 # at least one source yielded real codes
        if any_transient:
            return None                  # give transient failures another run
        return BUILD_UNAVAILABLE if any_unavailable else None

    def _source_ids_for_build(self, slug: str, build_id: str,
                              source_id: Optional[str] = None) -> List[str]:
        """Return ALL source-page ids for a build. cheatslips lists every upload
        of a build on /game/{slug}/{build_id} as a numeric /game/{slug}/{id}."""
        ids: List[str] = []
        if slug and build_id:
            url = f"{BASE_URL}/game/{slug}/{build_id}"
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                _handle_consent_banners(self._page, self.log)
                pairs = _find_source_build_pairs(self._page.content(), slug)
                bid = build_id.upper()
                for pid, fbid in pairs:
                    if (str(pid).isdigit() and (fbid is None or fbid.upper() == bid)
                            and str(pid) not in ids):
                        ids.append(str(pid))
            except Exception as exc:
                self.log(f"  Could not read build page for {build_id}: {exc}")
        if ids:
            return ids
        # Fallbacks when the build-id page lists no numeric sources.
        if source_id and str(source_id) not in ids:
            ids.append(str(source_id))
        elif not ids:
            sid = self._resolve_source_id(slug, build_id)
            if sid:
                ids.append(str(sid))
        return ids

    def _resolve_source_id(self, slug: str, build_id: str) -> Optional[str]:
        """Navigate to the game page and find the numeric source_id for a build_id."""
        if not slug or not build_id:
            return None
        game_url = f"{BASE_URL}/game/{slug}"
        try:
            self._page.goto(game_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            self.log(f"  Could not open game page {game_url}: {exc}")
            return None
        _handle_consent_banners(self._page, self.log)
        try:
            pairs = _find_source_build_pairs(self._page.content(), slug)
        except Exception as exc:
            self.log(f"  Could not parse build list from {game_url}: {exc}")
            return None
        bid = build_id.upper()
        for sid, found_bid in pairs:
            if found_bid and found_bid.upper() == bid:
                return sid
        # Not shown as a cheat card. Many builds only appear in the "Game
        # releases" table, which links to the build-id URL directly. Fall back to
        # the build_id itself: _download_build navigates to /game/{slug}/{bid} and,
        # if that is only a landing page, follows its link to the numeric cheat
        # page. If the build genuinely has no cheats, it fails gracefully there.
        self.log(f"  Build {bid} not among the {len(pairs)} cheat card(s) on "
                 f"{game_url}; trying the build-id URL directly.")
        return bid

    def download_game(self, slug: str, title_id: str, out_dir) -> List[str]:
        """Open a game page and download every build listed on it."""
        if not self.ensure_login():
            return []
        out = Path(out_dir)
        saved: List[str] = []
        game_url = f"{BASE_URL}/game/{slug}"
        try:
            self._page.goto(game_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            self.log(f"Could not open game page {game_url}: {exc}")
            return saved
        _handle_consent_banners(self._page, self.log)
        pairs = _find_source_build_pairs(self._page.content(), slug)
        self.log(f"Found {len(pairs)} build(s) on {slug}: {pairs}")
        for source_id, build_id in pairs:
            if self.should_stop and self.should_stop():
                break
            try:
                path = _download_build(self._page, source_id, build_id, slug,
                                       title_id, out, self.log)
                if path and path != BUILD_UNAVAILABLE:
                    saved.append(path)
            except Exception as exc:
                self.log(f"  ERROR build source_id={source_id}: {exc}")
            time.sleep(0.3)
        return saved

    def close(self):
        try:
            if self._context:
                _save_storage_state(self._context, log=self.log)
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._context = None
        self._pw = None
        self._page = None


def reset_quota_via_browser(email: Optional[str] = None,
                            password: Optional[str] = None,
                            log: Callable[[str], None] = print,
                            headless: bool = False,
                            should_stop: Optional[Callable[[], bool]] = None,
                            use_installed_browser: bool = False) -> bool:
    """Open browser, log in, and click the quota reset button.

    Returns True if the reset was successful. The user must solve the reCAPTCHA
    during the login step unless an already-authenticated installed browser is used.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is not installed. Install it with:\n"
            "    pip install playwright\n"
            "    playwright install") from exc

    reset_url = f"{BASE_URL}/profile/quota/reset"
    log(f"Opening browser for quota reset at {reset_url}")

    with sync_playwright() as p:
        browser, context = _launch_browser(p, headless, use_installed_browser, log)
        page = context.new_page()

        logged_in = _wait_for_login(page, email, password, log, should_stop)
        if not logged_in:
            context.close()
            if browser:
                browser.close()
            return False

        log(f"Navigating to quota reset page: {reset_url}")
        try:
            page.goto(reset_url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            log(f"Could not navigate to reset page: {exc}")
            context.close()
            if browser:
                browser.close()
            return False

        # Look for the reset button and click it
        clicked = _click_reset_button(page, log)
        if clicked:
            log("Quota reset submitted.")
        else:
            log("Could not find reset button.")

        context.close()
        if browser:
            browser.close()
        return clicked


def _url_to_slug(url: str) -> str:
    """Extract the slug from a cheatslips game URL."""
    url = url.strip().rstrip("/")
    m = re.search(r"/game/([^/]+)", url)
    if m:
        return m.group(1)
    raise ValueError(f"Not a valid cheatslips game URL: {url}")


def scrape_game_url(url: str, title_id: str, out_dir: Path,
                    log: Callable[[str], None] = print,
                    headless: bool = False,
                    should_stop: Optional[Callable[[], bool]] = None) -> List[str]:
    """Convenience wrapper that takes a full URL."""
    slug = _url_to_slug(url)
    return scrape_game_page(slug, title_id, out_dir, log=log,
                            headless=headless, should_stop=should_stop)
