#!/usr/bin/env python3
"""Unit tests for the pure/helper logic in scraper.py.

Run with:  python -m unittest test_scraper   (uses only the standard library)
"""

import json
import tempfile
import unittest
from pathlib import Path

from playwright_scrape import _find_source_build_pairs, _url_to_slug
from scraper import (
    CheatslipsMetadataScraper,
    GameDatabase,
    download_ibnux_archive,
    extract_version,
    normalize_slug,
    parse_cheat_names_from_content,
    parse_valid_cheats,
    cheat_file_is_empty,
    find_empty_cheat_files,
    recount_cheats_from_disk,
    scan_downloaded_build_ids,
    version_int_to_str,
    _region_from_name,
    _switchbrew_region_map,
    is_blocked_pair,
)


class TestExtractVersion(unittest.TestCase):
    def test_version_before_tid(self):
        text = "Breeze beta99o FINAL FANTASY TACTICS 1.4.0 TID: 010038B015560000 BID: 3CFD457814DD647F"
        self.assertEqual(extract_version(text), "1.4.0")

    def test_two_part_version(self):
        self.assertEqual(extract_version("Game 1.2 TID: ABC"), "1.2")

    def test_v_prefix_fallback(self):
        self.assertEqual(extract_version("Some Game v2.3.1 cheats"), "2.3.1")

    def test_none_when_absent(self):
        self.assertIsNone(extract_version("No version here"))

    def test_empty(self):
        self.assertIsNone(extract_version(""))


class TestNormalizeSlug(unittest.TestCase):
    def test_spaces_to_dashes(self):
        self.assertEqual(normalize_slug("Jump Force"), "jump-force")

    def test_trademark_symbols_stripped(self):
        self.assertEqual(normalize_slug("Star Wars™ Battlefront"), "star-wars-battlefront")

    def test_accents(self):
        self.assertEqual(normalize_slug("Pokémon"), "pokemon")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(normalize_slug("A   B"), "a-b")

    def test_no_trailing_dash(self):
        self.assertEqual(normalize_slug("Hello !"), "hello")


class TestGameDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = GameDatabase(Path(self.tmp.name) / "cheats.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _info(self, version="1.0.0", upload_date="01 Jan 2026"):
        return {
            "slug": "test-game",
            "title": "Test Game",
            "title_id": "0100000000000000",
            "sources": [{
                "source_id": "1",
                "build_id": "AAAA000000000001",
                "title_id": "0100000000000000",
                "version": version,
                "upload_date": upload_date,
                "cheat_count": 2,
                "cheat_names": ["Inf HP", "Max Money"],
            }],
        }

    def test_insert_and_count(self):
        self.db.upsert_game(self._info())
        self.assertEqual(self.db.count(), 1)

    def test_search_by_name(self):
        self.db.upsert_game(self._info())
        rows = self.db.search(term="test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], "1.0.0")
        self.assertEqual(json.loads(rows[0]["cheat_names"]), ["Inf HP", "Max Money"])

    def test_search_by_build_id(self):
        self.db.upsert_game(self._info())
        self.assertEqual(len(self.db.search(build_id="AAAA000000000001")), 1)
        self.assertEqual(len(self.db.search(build_id="DEADBEEF")), 0)

    def test_search_term_matches_title_id(self):
        # The GUI passes everything through term=, so typing an id must work.
        self.db.upsert_game(self._info())
        self.assertEqual(len(self.db.search(term="0100000000000000")), 1)
        self.assertEqual(len(self.db.search(term="010000000000")), 1)   # partial
        self.assertEqual(len(self.db.search(term="aaaa000000000001")), 1)  # build id, lower case
        self.assertEqual(len(self.db.search(term="FFFFFFFFFFFFFFFF")), 0)

    def test_wal_mode_and_title_index(self):
        mode = self.db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(str(mode).lower(), "wal")
        names = {r[1] for r in self.db._conn.execute("PRAGMA index_list(builds)")}
        self.assertIn("idx_builds_title", names)
        # The title_id lookup must actually use the index (no full scan).
        plan = " ".join(str(r[3]) for r in self.db._conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM builds WHERE title_id = ?",
            ("0100000000000000",)))
        self.assertIn("idx_builds_title", plan)

    def test_upsert_updates_and_keeps_old_version(self):
        self.db.upsert_game(self._info(version="1.0.0"))
        # A later scrape with no version must not wipe the known version.
        self.db.upsert_game(self._info(version=None))
        rows = self.db.search(build_id="AAAA000000000001")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], "1.0.0")

    def test_clear_empties_db(self):
        self.db.upsert_game(self._info())
        self.assertEqual(self.db.count(), 1)
        removed = self.db.clear()
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.count(), 0)

    def test_delete_build(self):
        self.db.upsert_game(self._info())
        n = self.db.delete_build("AAAA000000000001", "0100000000000000")
        self.assertEqual(n, 1)
        self.assertEqual(self.db.count(), 0)

    def test_update_build_ids(self):
        self.db.upsert_game(self._info())
        ok = self.db.update_build_ids("AAAA000000000001", "0100000000000000",
                                      "BBBB000000000002", "0100000000000099")
        self.assertTrue(ok)
        rows = self.db.search()
        self.assertEqual(rows[0]["build_id"], "BBBB000000000002")
        self.assertEqual(rows[0]["title_id"], "0100000000000099")

    def test_update_build_ids_conflict(self):
        self.db.upsert_game(self._info())
        self.db.upsert_build({"build_id": "BBBB000000000002", "title_id": "0100000000000000",
                              "cheat_count": 0, "cheat_names": "[]"})
        ok = self.db.update_build_ids("AAAA000000000001", "0100000000000000",
                                      "BBBB000000000002", "0100000000000000")
        self.assertFalse(ok)  # target already exists

    def test_zero_cheat_title_ids(self):
        self.db.upsert_game(self._info())  # cheat_count 2
        self.db.upsert_build({"build_id": "CCCC000000000003", "title_id": "0100000000000050",
                              "cheat_count": 0, "cheat_names": "[]"})
        zeros = self.db.zero_cheat_title_ids()
        self.assertIn("0100000000000050", zeros)
        self.assertNotIn("0100000000000000", zeros)

    def test_purge_invalid_removes_bad_title_ids(self):
        self.db.upsert_game(self._info())  # valid 16-char title id
        # Insert a row with a bad title id (simulates old 'NONE' scrape).
        self.db.upsert_build({
            "build_id": "CCCC000000000003", "title_id": "NONE", "slug": "x",
            "game_title": "X", "version": None, "source_id": "9",
            "upload_date": None, "cheat_count": 0, "cheat_names": "[]",
            "last_updated": "now",
        })
        self.assertEqual(self.db.count(), 2)
        removed = self.db.purge_invalid()
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.count(), 1)
        self.assertEqual(self.db.search()[0]["title_id"], "0100000000000000")

    def test_upsert_overwrites_with_new_version(self):
        self.db.upsert_game(self._info(version="1.0.0"))
        self.db.upsert_game(self._info(version="1.1.0"))
        rows = self.db.search(build_id="AAAA000000000001")
        self.assertEqual(rows[0]["version"], "1.1.0")
        self.assertEqual(self.db.count(), 1)  # still one row, not duplicated


class TestScanDownloaded(unittest.TestCase):
    def test_finds_build_ids_in_titles_and_by_bid(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            tdir = out / "titles" / "0100000000000000" / "cheats"
            tdir.mkdir(parents=True)
            (tdir / "AAAA000000000001.txt").write_text(
                "[Inf HP]\n04000000 12345678 00000063\n", encoding="utf-8")
            bdir = out / "by_bid"
            bdir.mkdir()
            (bdir / "bbbb000000000002.txt").write_text(
                "[Max Money]\n04000000 ABCDEF00 000F423F\n", encoding="utf-8")
            found = scan_downloaded_build_ids(out)
            self.assertIn("AAAA000000000001", found)
            self.assertIn("BBBB000000000002", found)  # uppercased
            self.assertNotIn("CCCC000000000003", found)

    def test_missing_dir_returns_empty(self):
        self.assertEqual(scan_downloaded_build_ids("does-not-exist-xyz"), set())

    def test_ignores_invalid_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            tdir = out / "titles" / "0100000000000000" / "cheats"
            tdir.mkdir(parents=True)
            (tdir / "AAAA000000000001.txt").write_text("[Inf HP]\n04000000 12345678 00000063\n", encoding="utf-8")
            (tdir / "EMPTY00000000000.txt").write_text("", encoding="utf-8")
            (tdir / "QUOTA00000000000.txt").write_text("API quota exceeded", encoding="utf-8")
            (tdir / "PLACEHOLDER00000.txt").write_text("Please register and send APIToken", encoding="utf-8")
            found = scan_downloaded_build_ids(out)
            self.assertIn("AAAA000000000001", found)
            self.assertNotIn("EMPTY00000000000", found)
            self.assertNotIn("QUOTA00000000000", found)
            self.assertNotIn("PLACEHOLDER00000", found)

    def test_scan_cache_written_and_reused(self):
        import scraper as _s
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            tdir = out / "titles" / "0100000000000000" / "cheats"
            tdir.mkdir(parents=True)
            f = tdir / "AAAA000000000001.txt"
            f.write_text("[Inf HP]\n04000000 12345678 00000063\n", encoding="utf-8")
            first = scan_downloaded_build_ids(out)
            self.assertIn("AAAA000000000001", first)
            cache_file = out / _s.SCAN_CACHE_NAME
            self.assertTrue(cache_file.exists(), "scan cache not written")
            # Second scan must hit the cache: patch the validity check so a
            # cache MISS would flip the result — the result staying identical
            # proves the file was NOT re-parsed.
            from unittest.mock import patch
            with patch.object(_s, "cheat_file_is_empty", return_value=True):
                second = scan_downloaded_build_ids(out)
            self.assertEqual(second, first)

    def test_scan_cache_invalidated_on_change(self):
        import time as _t
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            tdir = out / "titles" / "0100000000000000" / "cheats"
            tdir.mkdir(parents=True)
            f = tdir / "AAAA000000000001.txt"
            f.write_text("[Inf HP]\n04000000 12345678 00000063\n", encoding="utf-8")
            self.assertIn("AAAA000000000001", scan_downloaded_build_ids(out))
            # Overwrite with a codeless placeholder (different size) — the
            # changed file must be re-parsed and drop out of the result.
            f.write_text("API quota exceeded", encoding="utf-8")
            self.assertNotIn("AAAA000000000001", scan_downloaded_build_ids(out))


class TestStubSkipping(unittest.TestCase):
    """Codeless stub files (ads/names without codes) must never reach disk."""

    def _run_import(self, cheat_content, stub_content):
        import io
        import zipfile as _zf
        from unittest.mock import patch, MagicMock
        from scraper import download_gbatemp_archive

        zbuf = io.BytesIO()
        with _zf.ZipFile(zbuf, "w") as z:
            z.writestr("titles/0100000000000000/cheats/AAAA000000000001.txt",
                       cheat_content)
            z.writestr("titles/0100000000000000/cheats/BBBB000000000002.txt",
                       stub_content)
        zbuf.seek(0)
        resp = MagicMock(); resp.content = zbuf.read()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            db = GameDatabase(out / "t.db")
            try:
                with patch("scraper._gbatemp_latest_asset",
                           return_value=("tag", "http://x/z.zip", 1234)), \
                     patch("requests.get", return_value=resp):
                    written, games = download_gbatemp_archive(out, db)
                real_exists = (out / "titles" / "0100000000000000" / "cheats"
                               / "AAAA000000000001.txt").exists()
                stub_exists = (out / "titles" / "0100000000000000" / "cheats"
                               / "BBBB000000000002.txt").exists()
                rows = {r["build_id"]: dict(r) for r in db.search()}
            finally:
                db.close()
        return written, games, real_exists, stub_exists, rows

    def test_stub_not_written_but_in_db(self):
        written, games, real_on_disk, stub_on_disk, rows = self._run_import(
            "[Inf HP]\n04000000 12345678 00000063\n",
            "[From MAX-CHEATS.com by someone]\nUNLIMITED MOJO\n")
        self.assertTrue(real_on_disk, "real cheat file must be written")
        self.assertFalse(stub_on_disk, "codeless stub must NOT be written")
        self.assertEqual(written, 1)
        # Both builds stay visible in the DB; the stub with 0 cheats.
        self.assertIn("AAAA000000000001", rows)
        self.assertIn("BBBB000000000002", rows)
        self.assertEqual(rows["BBBB000000000002"]["cheat_count"], 0)


class TestWriteRestrict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = GameDatabase(Path(self.tmp.name) / "r.db")
        for i in (1, 2, 3):
            tid = f"010000000000{i:04X}"
            self.db.upsert_game({"title_id": tid, "title": None, "sources": [
                {"build_id": f"BBBB00000000{i:04X}", "title_id": tid,
                 "version": None, "cheat_count": 1, "cheat_names": ["c"]}]},
                source="test")
        self.tids = [f"010000000000{i:04X}".upper() for i in (1, 2, 3)]

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def test_update_blocked_outside_restrict(self):
        self.db.set_write_restrict([self.tids[0]])
        self.assertEqual(self.db.update_game_fields(self.tids[1], {"game_title": "X"}), 0)
        self.assertGreaterEqual(self.db.update_game_fields(self.tids[0], {"game_title": "Y"}), 1)
        self.db.set_write_restrict(None)
        rows = {r["title_id"]: r["game_title"] for r in self.db.search()}
        self.assertEqual(rows[self.tids[0]], "Y")
        self.assertIsNone(rows[self.tids[1]])   # untouched

    def test_missing_queries_respect_restrict(self):
        self.db.set_write_restrict([self.tids[0]])
        self.assertEqual(self.db.title_ids_missing_meta(), [self.tids[0]])
        self.assertEqual([t for t, _ in self.db.builds_missing_version()], [self.tids[0]])
        self.assertEqual(self.db.title_ids_missing_version(), [self.tids[0]])
        self.db.set_write_restrict(None)
        self.assertEqual(len(self.db.title_ids_missing_meta()), 3)

    def test_set_build_version_blocked(self):
        self.db.set_write_restrict([self.tids[0]])
        self.assertEqual(self.db.set_build_version(self.tids[1], "BBBB000000000002", "1.0.0"), 0)
        self.assertGreaterEqual(self.db.set_build_version(self.tids[0], "BBBB000000000001", "1.0.0"), 1)

    def test_clear_restrict_restores_full_writes(self):
        self.db.set_write_restrict([self.tids[0]])
        self.db.set_write_restrict(None)
        self.assertGreaterEqual(self.db.update_game_fields(self.tids[2], {"game_title": "Z"}), 1)


class TestSDExport(unittest.TestCase):
    def _setup(self, d):
        from scraper import GameDatabase
        out = Path(d) / "cheatsdownload"
        # a real cheat file + a stub file
        real = out / "titles" / "0100000000000000" / "cheats" / "AAAA000000000001.txt"
        real.parent.mkdir(parents=True)
        real.write_text("[Inf HP]\n04000000 12345678 00000063\n", encoding="utf-8")
        stub = out / "titles" / "0100000000000000" / "cheats" / "BBBB000000000002.txt"
        stub.write_text("[From MAX-CHEATS.com]\nJUST A NAME\n", encoding="utf-8")
        db = GameDatabase(Path(d) / "t.db")
        db.upsert_game({"title_id": "0100000000000000", "sources": [
            {"build_id": "AAAA000000000001", "title_id": "0100000000000000",
             "cheat_count": 1, "cheat_names": ["Inf HP"]},
            {"build_id": "BBBB000000000002", "title_id": "0100000000000000",
             "cheat_count": 0, "cheat_names": []},
        ]}, source="test")
        sd = Path(d) / "sd"
        (sd / "atmosphere").mkdir(parents=True)
        return db, out, sd

    def test_atmosphere_layout_and_stub_skip(self):
        from scraper import export_cheats_to_sd
        with tempfile.TemporaryDirectory() as d:
            db, out, sd = self._setup(d)
            try:
                stats = export_cheats_to_sd(db, out, sd, mode="atmosphere")
            finally:
                db.close()
            good = sd / "atmosphere" / "contents" / "0100000000000000" / "cheats" / "AAAA000000000001.txt"
            stub = sd / "atmosphere" / "contents" / "0100000000000000" / "cheats" / "BBBB000000000002.txt"
            self.assertTrue(good.exists(), "real cheat not exported")
            self.assertFalse(stub.exists(), "stub must be skipped")
            self.assertEqual(stats["exported"], 1)
            self.assertEqual(stats["skipped_stub"], 1)

    def test_breeze_and_edizon_layout(self):
        from scraper import export_cheats_to_sd
        with tempfile.TemporaryDirectory() as d:
            db, out, sd = self._setup(d)
            try:
                export_cheats_to_sd(db, out, sd, mode="breeze")
                export_cheats_to_sd(db, out, sd, mode="edizon")
            finally:
                db.close()
            self.assertTrue((sd / "switch" / "breeze" / "cheats" / "0100000000000000"
                             / "AAAA000000000001.txt").exists())
            self.assertTrue((sd / "switch" / "EdiZon" / "cheats"
                             / "AAAA000000000001.txt").exists())

    def test_zip_export_layout_and_stub_skip(self):
        import zipfile as _zf
        from scraper import export_cheats_to_zip
        with tempfile.TemporaryDirectory() as d:
            db, out, _sd = self._setup(d)
            zpath = Path(d) / "export.zip"
            try:
                stats = export_cheats_to_zip(db, out, zpath, mode="atmosphere")
            finally:
                db.close()
            self.assertEqual(stats["exported"], 1)
            self.assertEqual(stats["skipped_stub"], 1)
            self.assertTrue(zpath.exists())
            with _zf.ZipFile(zpath) as z:
                names = z.namelist()
            self.assertEqual(
                names,
                ["atmosphere/contents/0100000000000000/cheats/AAAA000000000001.txt"])

    def test_zip_export_empty_removes_file(self):
        from scraper import export_cheats_to_zip
        with tempfile.TemporaryDirectory() as d:
            db, out, _sd = self._setup(d)
            zpath = Path(d) / "empty.zip"
            try:
                stats = export_cheats_to_zip(db, out, zpath, mode="atmosphere",
                                             title_ids=["FFFFFFFFFFFFFFFF"])
            finally:
                db.close()
            self.assertEqual(stats["exported"], 0)
            self.assertFalse(zpath.exists(), "empty zip must be removed")

    def test_zip_roundtrip_export_then_import(self):
        from scraper import (GameDatabase, export_cheats_to_zip,
                             import_cheats_from_zip, scan_downloaded_build_ids)
        for mode in ("atmosphere", "breeze"):
            with tempfile.TemporaryDirectory() as d:
                db, out, _sd = self._setup(d)
                zpath = Path(d) / f"exp_{mode}.zip"
                try:
                    export_cheats_to_zip(db, out, zpath, mode=mode)
                finally:
                    db.close()
                # import into a fresh db + output
                imp_out = Path(d) / "imp"
                idb = GameDatabase(Path(d) / "imp.db")
                try:
                    written, games = import_cheats_from_zip(imp_out, idb, zpath)
                    rows = {r["build_id"] for r in idb.search()}
                finally:
                    idb.close()
                self.assertEqual(written, 1)          # the real cheat, stub excluded
                self.assertEqual(games, 1)
                self.assertIn("AAAA000000000001", rows)
                self.assertIn("AAAA000000000001",
                              scan_downloaded_build_ids(imp_out))

    def test_zip_import_missing_file_raises(self):
        from scraper import import_cheats_from_zip
        with tempfile.TemporaryDirectory() as d:
            db, out, _sd = self._setup(d)
            try:
                with self.assertRaises(RuntimeError):
                    import_cheats_from_zip(out, db, Path(d) / "nope.zip")
            finally:
                db.close()

    def test_looks_like_sd_root(self):
        from scraper import looks_like_sd_root
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(looks_like_sd_root(d))
            (Path(d) / "atmosphere").mkdir()
            self.assertTrue(looks_like_sd_root(d))


class TestCheckOnline(unittest.TestCase):
    def _resp(self, status):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.status_code = status
        return m

    def test_2xx_4xx_is_online(self):
        from unittest.mock import patch
        from scraper import check_cheatslips_online
        for status in (200, 301, 403, 404):
            with patch("requests.get", return_value=self._resp(status)):
                self.assertTrue(check_cheatslips_online(), f"status {status}")

    def test_5xx_is_offline(self):
        from unittest.mock import patch
        from scraper import check_cheatslips_online
        for status in (500, 502, 503):
            with patch("requests.get", return_value=self._resp(status)):
                self.assertFalse(check_cheatslips_online(), f"status {status}")

    def test_connection_error_is_offline(self):
        from unittest.mock import patch
        from scraper import check_cheatslips_online
        with patch("requests.get", side_effect=OSError("no route")):
            self.assertFalse(check_cheatslips_online())


class TestLogRotation(unittest.TestCase):
    def test_oversized_log_is_truncated(self):
        import scraper as _s
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "scraper.log"
            line = b"x" * 99 + b"\n"
            log.write_bytes(line * ((_s.LOG_MAX_BYTES // len(line)) + 100))
            self.assertGreater(log.stat().st_size, _s.LOG_MAX_BYTES)
            _s._rotate_log(log)
            size = log.stat().st_size
            self.assertLessEqual(size, _s.LOG_KEEP_BYTES + 64)
            self.assertTrue(log.read_bytes().startswith(b"===== log truncated"))

    def test_small_log_untouched(self):
        import scraper as _s
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "scraper.log"
            log.write_bytes(b"hello\n")
            _s._rotate_log(log)
            self.assertEqual(log.read_bytes(), b"hello\n")


class TestDownloadIbnuxArchive(unittest.TestCase):
    def test_extracts_cheats_and_fills_names(self):
        import io
        import zipfile
        from unittest.mock import patch, MagicMock

        tid = "0100000000000000"
        bid = "AAAAAAAAAAAAAAAA"
        cheat = "[Max Money]\n04000000 12345678 000F423F\n"
        games_md = f"| 1 | Super Mario Test | [{tid}](https://example.com/{tid}) | {bid} |\n"

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr(f"switch-cheat-master/atmosphere/titles/{tid}/cheats/{bid}.txt", cheat)
            zf.writestr("switch-cheat-master/GAMES.md", games_md)
        zbuf.seek(0)

        mock_resp = MagicMock()
        mock_resp.content = zbuf.read()
        mock_resp.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            db = GameDatabase(out / "test.db")
            try:
                with patch("requests.get", return_value=mock_resp):
                    written, ngames = download_ibnux_archive(out, db)
                self.assertEqual(written, 1)
                self.assertEqual(ngames, 1)
                self.assertTrue((out / "titles" / tid / "cheats" / f"{bid}.txt").exists())
                rows = db.search()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["title_id"], tid)
                self.assertEqual(rows[0]["build_id"], bid)
                self.assertEqual(rows[0]["game_title"], "Super Mario Test")
                self.assertEqual(rows[0]["source"], "ibnux")
            finally:
                db.close()


class TestParseCheatNames(unittest.TestCase):
    def test_square_brackets(self):
        content = "[Inf HP]\n04000000 12345678 00000063\n\n[Max Money]\n04000000 ABCDEF00 000F423F\n"
        self.assertEqual(parse_cheat_names_from_content(content), ["Inf HP", "Max Money"])

    def test_curly_brackets(self):
        content = "{God Mode}\n04000000 00000000 00000001\n"
        self.assertEqual(parse_cheat_names_from_content(content), ["God Mode"])

    def test_empty_content(self):
        self.assertEqual(parse_cheat_names_from_content(""), [])

    def test_no_headers(self):
        self.assertEqual(parse_cheat_names_from_content("04000000 12345678 00000063\n"), [])

    def test_strips_whitespace_in_name(self):
        content = "[  Speed Hack  ]\n04000000 00000000 00000001\n"
        self.assertEqual(parse_cheat_names_from_content(content), ["Speed Hack"])


class TestVersionIntToStr(unittest.TestCase):
    def test_base_version(self):
        self.assertEqual(version_int_to_str(0), "1.0.0")

    def test_minor_increment(self):
        self.assertEqual(version_int_to_str(65536), "1.1.0")

    def test_two_minor(self):
        self.assertEqual(version_int_to_str(131072), "1.2.0")


class TestGameDatabaseMeta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = GameDatabase(Path(self.tmp.name) / "cheats.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _insert(self, tid, bid, title=None):
        self.db.upsert_build({
            "build_id": bid, "title_id": tid,
            "game_title": title, "slug": None,
            "version": None, "source_id": None,
            "upload_date": None, "cheat_count": 1, "cheat_names": "[]",
            "last_updated": None,
        })

    def test_title_ids_missing_meta_detects_no_name(self):
        self._insert("0100000000000001", "AAAA000000000001", title=None)
        # A fully-populated title (name + cover) must NOT count as missing meta;
        # title_ids_missing_meta flags rows missing a name OR a cover image.
        self._insert("0100000000000002", "BBBB000000000002", title="Known Game")
        self.db.update_game_fields("0100000000000002", {"image": "http://img/cover.png"})
        missing = self.db.title_ids_missing_meta()
        self.assertIn("0100000000000001", missing)
        self.assertNotIn("0100000000000002", missing)

    def test_update_game_fields_fills_name(self):
        self._insert("0100000000000001", "AAAA000000000001", title=None)
        self.db.update_game_fields("0100000000000001", {"game_title": "My Game"})
        rows = self.db.search(title_id="0100000000000001")
        self.assertEqual(rows[0]["game_title"], "My Game")

    def test_update_game_fields_does_not_overwrite_existing_name(self):
        self._insert("0100000000000001", "AAAA000000000001", title="Original")
        self.db.update_game_fields("0100000000000001", {"game_title": "New Name"})
        rows = self.db.search(title_id="0100000000000001")
        self.assertEqual(rows[0]["game_title"], "Original")  # COALESCE keeps old value

    def test_fill_game_meta_fills_empty(self):
        self._insert("0100000000000001", "AAAA000000000001", title=None)
        self.db.fill_game_meta("0100000000000001", name="Filled Name", image="http://img")
        rows = self.db.search(title_id="0100000000000001")
        self.assertEqual(rows[0]["game_title"], "Filled Name")
        self.assertEqual(rows[0]["image"], "http://img")

    def test_title_ids_missing_version_detects_null(self):
        self._insert("0100000000000003", "CCCC000000000003", title="Game")
        missing = self.db.title_ids_missing_version()
        self.assertIn("0100000000000003", missing)

    def test_title_ids_missing_version_excludes_set_version(self):
        self.db.upsert_build({
            "build_id": "DDDD000000000004", "title_id": "0100000000000004",
            "game_title": "Game", "slug": None, "version": "1.0.0",
            "source_id": None, "upload_date": None, "cheat_count": 1,
            "cheat_names": "[]", "last_updated": None,
        })
        missing = self.db.title_ids_missing_version()
        self.assertNotIn("0100000000000004", missing)

    def test_all_title_ids_returns_valid_only(self):
        self._insert("0100000000000001", "AAAA000000000001")
        self.db.upsert_build({
            "build_id": "EEEE000000000005", "title_id": "NONE",
            "game_title": None, "slug": None, "version": None,
            "source_id": None, "upload_date": None, "cheat_count": 0,
            "cheat_names": "[]", "last_updated": None,
        })
        tids = self.db.all_title_ids()
        self.assertIn("0100000000000001", tids)
        self.assertNotIn("NONE", tids)

    def test_set_game_meta_fills_slug_and_title(self):
        self._insert("0100000000000001", "AAAA000000000001", title=None)
        self.db.set_game_meta("0100000000000001", slug="my-game", game_title="My Game")
        rows = self.db.search(title_id="0100000000000001")
        self.assertEqual(rows[0]["game_title"], "My Game")
        self.assertEqual(rows[0]["slug"], "my-game")


class TestFindSourceBuildPairs(unittest.TestCase):
    def test_numeric_source_id(self):
        html = """
        <div class="card">
            <a href="/game/stardew-valley/4922">play</a>
            <div>Build Id FA3FB8D6C8B648EB</div>
        </div>
        """
        pairs = _find_source_build_pairs(html, "stardew-valley")
        self.assertEqual(pairs, [("4922", "FA3FB8D6C8B648EB")])

    def test_build_id_url(self):
        html = """
        <div class="card">
            <a href="/game/stardew-valley/FA3FB8D6C8B648EB">play</a>
            <div>Build Id FA3FB8D6C8B648EB</div>
        </div>
        """
        pairs = _find_source_build_pairs(html, "stardew-valley")
        self.assertEqual(pairs, [("FA3FB8D6C8B648EB", "FA3FB8D6C8B648EB")])

    def test_mixed_numeric_and_build_id_urls(self):
        html = """
        <div class="card">
            <a href="/game/stardew-valley/4922">play</a>
            <div>Build Id FA3FB8D6C8B648EB</div>
        </div>
        <div class="card">
            <a href="/game/stardew-valley/A5E2069AC7F0CFFB">play</a>
            <div>Build Id A5E2069AC7F0CFFB</div>
        </div>
        """
        pairs = _find_source_build_pairs(html, "stardew-valley")
        self.assertEqual(pairs, [
            ("4922", "FA3FB8D6C8B648EB"),
            ("A5E2069AC7F0CFFB", "A5E2069AC7F0CFFB"),
        ])

    def test_multiple_source_pages_same_build(self):
        # A build whose cheats are split across several upload/source pages
        # (like Dokapon Kingdom Connect A949900BA7FB9CB9 -> 4068..4072). All must
        # be returned so the browser download can fetch + merge every source.
        html = """
        <div class="card"><a href="/game/dokapon/4068">play</a><div>Build Id A949900BA7FB9CB9</div></div>
        <div class="card"><a href="/game/dokapon/4069">play</a><div>Build Id A949900BA7FB9CB9</div></div>
        <div class="card"><a href="/game/dokapon/4070">play</a><div>Build Id A949900BA7FB9CB9</div></div>
        """
        pairs = _find_source_build_pairs(html, "dokapon")
        self.assertEqual(pairs, [
            ("4068", "A949900BA7FB9CB9"),
            ("4069", "A949900BA7FB9CB9"),
            ("4070", "A949900BA7FB9CB9"),
        ])

    def test_fallback_when_no_cards(self):
        html = """
        <a href="/game/stardew-valley/4922">build 1</a>
        <a href="/game/stardew-valley/FA3FB8D6C8B648EB">build 2</a>
        """
        pairs = _find_source_build_pairs(html, "stardew-valley")
        self.assertEqual(sorted(pairs), [
            ("4922", None),
            ("FA3FB8D6C8B648EB", None),
        ])

    def test_skips_title_ids_in_card_text(self):
        html = """
        <div class="card">
            <a href="/game/stardew-valley/4922">play</a>
            <div>Title ID 0100655023B00000 BID FA3FB8D6C8B648EB</div>
        </div>
        """
        pairs = _find_source_build_pairs(html, "stardew-valley")
        self.assertEqual(pairs, [("4922", "FA3FB8D6C8B648EB")])

    def test_game_releases_table_builds_are_included(self):
        # Like Pokémon Shield: only one build is a featured card, the rest live
        # only in the "Game releases" table and must still be discovered.
        html = """
        <div class="card">
            <a href="/game/pokemon-shield/9999">play</a>
            <div>Build Id A16802625E7826BF</div>
        </div>
        <table>
            <thead><tr><th>Build ID</th><th>Available cheats</th></tr></thead>
            <tbody>
                <tr><td><a href="/game/pokemon-shield/A16802625E7826BF">A16802625E7826BF</a></td><td>6</td></tr>
                <tr><td><a href="/game/pokemon-shield/896900182175428B">896900182175428B</a></td><td>1</td></tr>
                <tr><td><a href="/game/pokemon-shield/42481AFD45D3D4F1">42481AFD45D3D4F1</a></td><td>1</td></tr>
            </tbody>
        </table>
        """
        pairs = _find_source_build_pairs(html, "pokemon-shield")
        # The card build keeps its numeric page id and is not duplicated; the
        # table-only builds are added via their build-id URLs.
        self.assertEqual(pairs, [
            ("9999", "A16802625E7826BF"),
            ("896900182175428B", "896900182175428B"),
            ("42481AFD45D3D4F1", "42481AFD45D3D4F1"),
        ])


class TestValidCheats(unittest.TestCase):
    """parse_valid_cheats counts only cheats that actually have code lines, so
    codeless 'preview' entries and empty files are correctly identified."""

    def test_counts_only_blocks_with_codes(self):
        content = ("[Inf HP]\n04000000 12345678 00000063\n\n"
                   "[Codeless]\n\n"
                   "[Max Money]\n04000000 ABCDEF00 000F423F\n")
        self.assertEqual(parse_valid_cheats(content), ["Inf HP", "Max Money"])

    def test_master_without_codes_ignored(self):
        content = "{Master}\n\n[Real]\n04000000 00000000 00000001\n"
        self.assertEqual(parse_valid_cheats(content), ["Real"])

    def test_section_markers_ignored(self):
        content = "[--- Section ---]\n04000000 00000000 00000001\n"
        self.assertEqual(parse_valid_cheats(content), [])

    def test_bom_prefix_does_not_break_parsing(self):
        # A leading UTF-8 BOM must not hide a real cheat (The Last Dragon Slayer).
        self.assertEqual(
            parse_valid_cheats("﻿[Inf Hp]\n58000000 02F52EC8\n64000000 00000000 000000C8\n"),
            ["Inf Hp"])

    def test_lenient_code_detection(self):
        # Non-standard ibnux code formatting (0x prefix / 10-digit groups) still
        # counts as a real cheat because at least one 8-hex word is present.
        self.assertEqual(parse_valid_cheats("[Diamonds]\n04100000 0xae91a3 000003E7\n"), ["Diamonds"])
        self.assertEqual(parse_valid_cheats("[Hit]\n04100000 008790D86C 60004A40\n"), ["Hit"])

    def test_named_but_no_codes_is_empty(self):
        # A cheat name with no code lines at all is still 0 (nothing to apply).
        self.assertEqual(parse_valid_cheats("[From MAX-CHEATS]\nUNLIMITED MOJO\n"), [])

    def test_empty_file_detection(self):
        self.assertTrue(cheat_file_is_empty(""))
        self.assertTrue(cheat_file_is_empty("   \n\n"))
        self.assertTrue(cheat_file_is_empty("API quota exceeded"))
        self.assertTrue(cheat_file_is_empty("[Only Name]\n[Another Name]\n"))
        self.assertFalse(cheat_file_is_empty("[Inf HP]\n04000000 12345678 00000063\n"))

    def test_find_empty_cheat_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            db = GameDatabase(out / "test.db")
            try:
                tid = "0100000000000000"
                good, empty = "AAAA000000000001", "BBBB000000000002"
                db.upsert_build({"build_id": good, "title_id": tid, "cheat_count": 1})
                db.upsert_build({"build_id": empty, "title_id": tid, "cheat_count": 3})
                cdir = out / "titles" / tid / "cheats"
                cdir.mkdir(parents=True)
                (cdir / f"{good}.txt").write_text("[Inf HP]\n04000000 12345678 00000063\n",
                                                  encoding="utf-8")
                (cdir / f"{empty}.txt").write_text("[Name only]\n[Another]\n", encoding="utf-8")
                found = find_empty_cheat_files(db, out)
                self.assertEqual(found, [(tid, empty)])
            finally:
                db.close()


class TestRecountFromDisk(unittest.TestCase):
    """The cheat file on disk is the source of truth for the count."""

    def test_file_count_overrides_wrong_db_count(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            db = GameDatabase(out / "test.db")
            try:
                tid, bid = "0100000000000000", "AAAA000000000001"
                # DB claims 2 cheats, but the file actually contains 3.
                db.upsert_build({"build_id": bid, "title_id": tid,
                                 "cheat_count": 2, "cheat_names": '["a", "b"]'})
                cdir = out / "titles" / tid / "cheats"
                cdir.mkdir(parents=True)
                (cdir / f"{bid}.txt").write_text(
                    "[One]\n04000000 00000000 00000001\n"
                    "[Two]\n04000000 00000000 00000002\n"
                    "[Three]\n04000000 00000000 00000003\n", encoding="utf-8")
                n = recount_cheats_from_disk(db, out, only_missing=False)
                self.assertEqual(n, 1)
                self.assertEqual(db.search(build_id=bid)[0]["cheat_count"], 3)
                # Second run is a no-op: the DB already matches the file.
                self.assertEqual(recount_cheats_from_disk(db, out, only_missing=False), 0)
            finally:
                db.close()

    def test_only_missing_leaves_known_counts_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            db = GameDatabase(out / "test.db")
            try:
                tid, bid = "0100000000000000", "AAAA000000000001"
                db.upsert_build({"build_id": bid, "title_id": tid,
                                 "cheat_count": 2, "cheat_names": '["a", "b"]'})
                cdir = out / "titles" / tid / "cheats"
                cdir.mkdir(parents=True)
                (cdir / f"{bid}.txt").write_text("[One]\n04000000 00000000 00000001\n",
                                                 encoding="utf-8")
                # only_missing=True skips rows that already have a count.
                self.assertEqual(recount_cheats_from_disk(db, out, only_missing=True), 0)
                self.assertEqual(db.search(build_id=bid)[0]["cheat_count"], 2)
            finally:
                db.close()


class TestScrapeGameDetailsTableCount(unittest.TestCase):
    """The 'Game releases' table has an 'Available cheats' count column; a
    table-only build must take that number instead of being recorded as 0."""

    _HTML = """
    <html><body>
      <h1>Pokemon Shield</h1>
      <li class="list-group-item"><span class="text-uppercase">0100ABCDEF012000</span></li>
      <table>
        <thead><tr><th>Build ID</th><th>Available cheats</th><th>Latest cheats</th></tr></thead>
        <tbody>
          <tr><td>A16802625E7826BF</td><td>6</td><td>19 Jun 2026</td></tr>
          <tr><td>896900182175428B</td><td>1</td><td>18 Jun 2026</td></tr>
        </tbody>
      </table>
    </body></html>
    """

    def test_available_cheats_column_sets_count(self):
        from unittest.mock import patch
        sc = CheatslipsMetadataScraper()
        with patch.object(CheatslipsMetadataScraper, "_get", return_value=self._HTML):
            info = sc.scrape_game_details("pokemon-shield")
        counts = {s["build_id"]: s["cheat_count"] for s in info["sources"]}
        self.assertEqual(counts["A16802625E7826BF"], 6)
        self.assertEqual(counts["896900182175428B"], 1)

    def test_no_available_column_is_unknown(self):
        from unittest.mock import patch
        html = self._HTML.replace("<th>Available cheats</th>", "<th>Notes</th>")
        sc = CheatslipsMetadataScraper()
        with patch.object(CheatslipsMetadataScraper, "_get", return_value=html):
            info = sc.scrape_game_details("pokemon-shield")
        counts = {s["build_id"]: s["cheat_count"] for s in info["sources"]}
        # No reliable count column -> None (unknown), NOT a misleading 0.
        self.assertIsNone(counts["A16802625E7826BF"])

    def test_available_zero_is_unknown_not_zero(self):
        # cheatslips sometimes reports 0 for a build that DOES have cheats;
        # such a build must be stored as unknown (None), not 0, so it stays
        # visible and gets downloaded.
        from unittest.mock import patch
        html = self._HTML.replace(
            "<tr><td>896900182175428B</td><td>1</td><td>18 Jun 2026</td></tr>",
            "<tr><td>896900182175428B</td><td>0</td><td>18 Jun 2026</td></tr>")
        sc = CheatslipsMetadataScraper()
        with patch.object(CheatslipsMetadataScraper, "_get", return_value=html):
            info = sc.scrape_game_details("pokemon-shield")
        counts = {s["build_id"]: s["cheat_count"] for s in info["sources"]}
        self.assertIsNone(counts["896900182175428B"])
        self.assertEqual(counts["A16802625E7826BF"], 6)  # positive count kept


class TestUrlToSlug(unittest.TestCase):
    def test_numeric_source_id_url(self):
        self.assertEqual(_url_to_slug("https://www.cheatslips.com/game/stardew-valley/4922"), "stardew-valley")

    def test_build_id_url(self):
        self.assertEqual(
            _url_to_slug("https://www.cheatslips.com/game/stardew-valley/FA3FB8D6C8B648EB"),
            "stardew-valley")

    def test_invalid_url_raises(self):
        with self.assertRaises(ValueError):
            _url_to_slug("https://www.cheatslips.com/not-a-game-url")


class TestRegionFromName(unittest.TestCase):
    def test_hiragana_is_jp(self):
        self.assertEqual(_region_from_name("モンスターハンターライズ"), "JP")

    def test_katakana_is_jp(self):
        self.assertEqual(_region_from_name("ペルソナ５ スクランブル"), "JP")

    def test_simplified_chinese_is_cn(self):
        self.assertEqual(_region_from_name("马力欧卡丁车8 豪华版"), "CN")

    def test_latin_name_is_unknown(self):
        self.assertIsNone(_region_from_name("The Witcher 3: Wild Hunt"))

    def test_empty_is_unknown(self):
        self.assertIsNone(_region_from_name(""))
        self.assertIsNone(_region_from_name(None))


class TestSwitchbrewRegionMap(unittest.TestCase):
    WIKI = (
        "{| class=\"wikitable sortable\"\n"
        "|-\n"
        "| 01003C100655A000 || Some Game || EUR USA || rest\n"
        "|-\n"
        "| 0100F8A004458000 || Another || EUR || rest\n"
        "|-\n"
        "| 010060200A4BE000 || Third || JPN KOR || rest\n"
        "|-\n"
        "| 0100000000000000 || NoRegion ||  || rest\n"
    )

    def _map(self, text):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "switchbrew_games.txt").write_text(text, encoding="utf-8")
            return _switchbrew_region_map(d)

    def test_maps_and_sorts_codes(self):
        m = self._map(self.WIKI)
        self.assertEqual(m["01003C100655A000"], "EU/US")
        self.assertEqual(m["0100F8A004458000"], "EU")
        self.assertEqual(m["010060200A4BE000"], "JP/KR")

    def test_blank_region_is_skipped(self):
        self.assertNotIn("0100000000000000", self._map(self.WIKI))

    def test_missing_cache_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_switchbrew_region_map(d), {})


class TestBlockedPair(unittest.TestCase):
    def test_build_id_equal_title_id_is_blocked(self):
        self.assertTrue(is_blocked_pair("010015100B514000", "010015100B514000"))

    def test_build_id_equal_title_id_case_insensitive(self):
        self.assertTrue(is_blocked_pair("010015100b514000", "010015100B514000"))

    def test_real_build_id_not_blocked(self):
        self.assertFalse(is_blocked_pair("010015100B514000", "FF773E90972D544E"))

    def test_none_inputs_not_blocked(self):
        self.assertFalse(is_blocked_pair(None, None))
        self.assertFalse(is_blocked_pair("010015100B514000", None))

    def test_upsert_skips_placeholder_and_keeps_real(self):
        with tempfile.TemporaryDirectory() as d:
            db = GameDatabase(Path(d) / "t.db")
            db.upsert_build({"title_id": "010015100B514000",
                             "build_id": "010015100B514000", "cheat_count": 9})
            db.upsert_build({"title_id": "010015100B514000",
                             "build_id": "FF773E90972D544E", "cheat_count": 4})
            bids = [r[0] for r in db._conn.execute(
                "SELECT build_id FROM builds WHERE title_id=?",
                ("010015100B514000",)).fetchall()]
            db.close()
            self.assertEqual(bids, ["FF773E90972D544E"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
