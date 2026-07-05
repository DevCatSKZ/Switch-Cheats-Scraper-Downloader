#!/usr/bin/env python3
"""Get cheat codes the API won't deliver (quota-limited) by using your
**system's default browser** for login and then downloading cheat ZIPs with
that authenticated session.

Flow:
  1. Opens the cheatslips login page in your default browser.
  2. You log in and solve the reCAPTCHA.
  3. You paste the 'session' cookie value from the browser into the prompt.
  4. The tool downloads cheat ZIPs for missing builds, extracts and sorts them
     into titles/{title_id}/cheats/{build_id}.txt.

No external browser-automation dependencies are needed.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
import webbrowser
from pathlib import Path
from typing import Callable, List, Optional

from scraper import save_cheat_merged

BASE_URL = "https://www.cheatslips.com"
COOKIE_DOMAIN = "cheatslips.com"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# An Atmosphere cheat line is a "[Name]" / "{Name}" header or a pair of 8-hex
# words (the actual code). Used to recognise real cheat content in the HTML.
_HEX_PAIR_RE = re.compile(r"\b[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}\b")
_HEADER_RE = re.compile(r"^[\[{].+?[\]}]$")


# --------------------------------------------------------------------- session
def create_session_from_token(token: str) -> "requests.Session":
    """Create a web session authenticated via API token (no browser_cookie3).

    The cheatslips API uses X-API-TOKEN header. We set it on the session
    and also try setting it as a cookie, so both API and web endpoints
    may accept it.
    """
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml",
                      "X-API-TOKEN": token})
    # Also try as cookie — some web routes check session, not header
    s.cookies.set("session", token, domain=COOKIE_DOMAIN, path="/")
    return s


def create_session_from_cookie(cookie_value: str) -> "requests.Session":
    """Create a web session from a manually pasted session cookie."""
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})
    s.cookies.set("session", cookie_value, domain=COOKIE_DOMAIN, path="/")
    return s


def open_login_page():
    """Open the cheatslips login in the system default browser."""
    try:
        webbrowser.open(f"{BASE_URL}/login")
    except Exception:
        pass


def session_logged_in(session) -> bool:
    """Best-effort check that the cookie session is actually authenticated."""
    try:
        r = session.get(f"{BASE_URL}/account", timeout=20, allow_redirects=True)
    except Exception:
        return False
    # Logged out -> redirected to /login.
    if "/login" in (r.url or "").lower():
        return False
    body = r.text.lower()
    return "logout" in body or "my account" in body or "subscription" in body


# ----------------------------------------------------------------- extraction
def looks_like_cheat_text(text: str) -> bool:
    """Heuristic: does this text contain real Atmosphere cheat codes?"""
    return bool(text) and bool(_HEX_PAIR_RE.search(text))


def extract_cheat_text_from_html(html: str) -> str:
    """Best-effort extraction of the cheat .txt content from a logged-in page.

    Tries <pre>/<code>/<textarea> blocks, then any block element whose text looks
    like a cheat file, then a whole-page line filter. Returns "" if nothing
    cheat-like is found (caller can dump the HTML for inspection).
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""
    soup = BeautifulSoup(html, "lxml")

    candidates: List[str] = []
    for tag in soup.find_all(["pre", "code", "textarea"]):
        t = tag.get_text("\n")
        if looks_like_cheat_text(t):
            candidates.append(t)
    if candidates:
        return max(candidates, key=len).strip()

    for tag in soup.find_all(["div", "section", "article", "p", "span"]):
        t = tag.get_text("\n")
        if looks_like_cheat_text(t) and t.count("\n") >= 2:
            candidates.append(t)
    if candidates:
        return max(candidates, key=len).strip()

    keep, in_block = [], False
    for ln in soup.get_text("\n").splitlines():
        s = ln.strip()
        if _HEADER_RE.match(s) or _HEX_PAIR_RE.search(s):
            keep.append(ln.rstrip())
            in_block = True
        elif in_block and not s:
            keep.append("")
    out = "\n".join(keep).strip()
    return out if looks_like_cheat_text(out) else ""


# ------------------------------------------------------------------- scraper
class CookieCheatScraper:
    """Fetches cheat codes via an authenticated cookie session.

    Tries ZIP download first (the site's download button), then falls back to
    HTML extraction. ZIPs are extracted and sorted into the correct folder.
    """

    def __init__(self, session, log: Callable[[str], None] = print):
        self.session = session
        self.log = log

    def _get(self, url: str) -> str:
        full = url if url.startswith("http") else BASE_URL + url
        r = self.session.get(full, timeout=30)
        r.raise_for_status()
        return r.text

    def _post_download(self, page_url: str, html: str) -> Optional[bytes]:
        """Parse the page for the download form (CSRF + action=download) and POST it.

        Returns ZIP bytes if the server responds with a ZIP, else None.
        """
        try:
            from bs4 import BeautifulSoup
        except Exception:
            return None
        soup = BeautifulSoup(html, "lxml")
        form = soup.find("form")
        if not form:
            return None
        # Check the form has a download button
        dl_btn = None
        for btn in form.find_all("button"):
            if (btn.get("value") or "").lower() == "download":
                dl_btn = btn
                break
        if not dl_btn:
            return None
        # Collect form data
        data = {}
        for inp in form.find_all("input"):
            n = inp.get("name")
            if n:
                data[n] = inp.get("value", "")
        # Add the button's name+value (action=download)
        if dl_btn.get("name"):
            data[dl_btn["name"]] = dl_btn.get("value", "")
        # POST to the same page URL
        full = page_url if page_url.startswith("http") else BASE_URL + page_url
        r = self.session.post(full, data=data, timeout=60, allow_redirects=True)
        if r.status_code != 200:
            return None
        resp_data = r.content
        # Check if response is a ZIP
        if resp_data[:4] == b"PK\x03\x04":
            try:
                zf = zipfile.ZipFile(io.BytesIO(resp_data))
                if zf.testzip() is None:
                    return resp_data
            except Exception:
                pass
        # Check if response is plain text cheat codes
        try:
            text = resp_data.decode("utf-8", errors="replace")
            if looks_like_cheat_text(text):
                # Save as a fake "zip" with one entry — or just save directly
                return resp_data  # caller will check if it's ZIP or text
        except Exception:
            pass
        return None

    def _download_zip(self, url: str) -> Optional[bytes]:
        """Download a URL and return ZIP bytes if the response is a ZIP."""
        full = url if url.startswith("http") else BASE_URL + url
        r = self.session.get(full, timeout=60, stream=True)
        if r.status_code != 200:
            return None
        ct = (r.headers.get("Content-Type") or "").lower()
        data = r.content
        # Check if it's actually a ZIP (magic bytes PK\x03\x04)
        if data[:4] == b"PK\x03\x04" or "zip" in ct or "octet-stream" in ct:
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                # Verify it's a valid ZIP
                if zf.testzip() is None:
                    return data
            except Exception:
                pass
        return None

    def _extract_and_sort_zip(self, zip_data: bytes, title_id: str,
                              build_id: str, out_dir: Path) -> Optional[str]:
        """Extract a cheat ZIP and sort files into titles/{tid}/cheats/{bid}.txt.

        cheatslips ZIPs typically contain a .txt file with cheat codes.
        We extract the largest .txt file and save it as {build_id}.txt.
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_data))
        except Exception as exc:
            self.log(f"    ZIP parse error: {exc}")
            return None

        # Find the best .txt file (largest one with cheat-like content)
        best_name = None
        best_content = ""
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.lower()
            if not name.endswith(".txt"):
                continue
            try:
                content = zf.read(info).decode("utf-8", errors="replace")
            except Exception:
                continue
            if looks_like_cheat_text(content) and len(content) > len(best_content):
                best_content = content
                best_name = info.filename

        if not best_content:
            # Try any file as a last resort
            for info in zf.infolist():
                if info.is_dir():
                    continue
                try:
                    content = zf.read(info).decode("utf-8", errors="replace")
                except Exception:
                    continue
                if looks_like_cheat_text(content) and len(content) > len(best_content):
                    best_content = content
                    best_name = info.filename

        if not best_content:
            self.log(f"    ZIP had no cheat-like .txt file")
            return None

        save_dir = out_dir / "titles" / title_id / "cheats"
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{build_id}.txt"
        save_cheat_merged(path, best_content)
        self.log(f"    ✓ Extracted {best_name} -> {path.name} ({len(best_content)} bytes)")
        return str(path)

    def scrape_build(self, slug: str, title_id: str, build_id: str,
                     out_dir: Path, source_ids: Optional[List[str]] = None,
                     debug_dir: Optional[Path] = None) -> Optional[str]:
        """Download one build's codes -> titles/{tid}/cheats/{bid}.txt.

        1. Fetches the game page, finds the download form (CSRF + action=download).
        2. POSTs the form to get the cheat ZIP/txt.
        3. Extracts and saves the codes.
        Falls back to HTML extraction if no form is found.
        """
        urls = [f"/game/{slug}/{build_id}"]
        for sid in (source_ids or []):
            urls.append(f"/game/{slug}/{sid}")

        for u in urls:
            try:
                html = self._get(u)
            except Exception as exc:
                self.log(f"    page {u} failed: {exc}")
                continue

            # Try POST download form first
            try:
                resp_data = self._post_download(u, html)
                if resp_data:
                    # Is it a ZIP?
                    if resp_data[:4] == b"PK\x03\x04":
                        self.log(f"    ✓ Got ZIP via POST download form from {u}")
                        return self._extract_and_sort_zip(resp_data, title_id, build_id, out_dir)
                    # Is it plain text cheat codes?
                    try:
                        text = resp_data.decode("utf-8", errors="replace")
                        if looks_like_cheat_text(text):
                            self.log(f"    ✓ Got cheat text via POST download form from {u}")
                            save_dir = out_dir / "titles" / title_id / "cheats"
                            save_dir.mkdir(parents=True, exist_ok=True)
                            path = save_dir / f"{build_id}.txt"
                            save_cheat_merged(path, text)
                            return str(path)
                    except Exception:
                        pass
            except Exception as exc:
                self.log(f"    POST download failed for {u}: {exc}")

            # Fallback: HTML extraction (codes visible on page)
            codes = extract_cheat_text_from_html(html)
            if codes and len(codes) > 40:
                save_dir = out_dir / "titles" / title_id / "cheats"
                save_dir.mkdir(parents=True, exist_ok=True)
                path = save_dir / f"{build_id}.txt"
                save_cheat_merged(path, codes)
                return str(path)

            # Save debug page for inspection
            if debug_dir is not None:
                try:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    safe = u.strip("/").replace("/", "_")
                    (debug_dir / f"{build_id}_{safe}.html").write_text(html, encoding="utf-8")
                except Exception:
                    pass
            time.sleep(0.3)

        return None
