"""Unit + integration tests for the EDL -> SubCap tool.

Run from the project root:  python -m unittest discover -s tests
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edl_parser import (tc_to_frames, frames_to_tc, parse_edl, EDLParseError,
                        Event, FPS)
from matcher import (match_events, ranges_overlap, FULL, PARTIAL, NONE)
from subcap_writer import (CaptionBlock, enforce_non_overlap, build_caption_text,
                           blocks_from_matches, write_subcap, HEADER, BEGIN, END)
from reports import write_no_match_report, write_match_report

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "sample_data")


def _mk_event(edit, reel, track, sin, sout, rin, rout, sf=None):
    ev = Event(edit, reel, track, "C", sin, sout, rin, rout, 0)
    ev.source_file = sf if sf is not None else reel
    return ev


# --------------------------------------------------------------------------
# Timecode <-> frame conversion (incl. the FF<=23 assertion).
# --------------------------------------------------------------------------
class TestTimecode(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(tc_to_frames("00:00:00:00"), 0)

    def test_one_second(self):
        self.assertEqual(tc_to_frames("00:00:01:00"), FPS)

    def test_24fps_math(self):
        # 01:00:00:00 at 24fps = 3600*24 frames
        self.assertEqual(tc_to_frames("01:00:00:00"), 3600 * FPS)

    def test_max_frame_field(self):
        # FF 23 is legal (24fps NDF, FF runs 00-23).
        self.assertEqual(tc_to_frames("00:00:00:23"), 23)

    def test_frame_field_24_aborts(self):
        # FF 24+ signals a wrong-rate export and must abort.
        with self.assertRaises(EDLParseError):
            tc_to_frames("00:00:00:24")

    def test_frame_field_29_aborts(self):
        with self.assertRaises(EDLParseError):
            tc_to_frames("00:00:00:29")

    def test_roundtrip(self):
        for tc in ["00:00:00:00", "01:23:45:11", "02:25:22:02", "10:00:05:23"]:
            self.assertEqual(frames_to_tc(tc_to_frames(tc)), tc)

    def test_malformed(self):
        with self.assertRaises(EDLParseError):
            tc_to_frames("1:2:3")

    def test_bad_seconds(self):
        with self.assertRaises(EDLParseError):
            tc_to_frames("00:00:60:00")


# --------------------------------------------------------------------------
# Overlap detection.
# --------------------------------------------------------------------------
class TestOverlap(unittest.TestCase):
    def test_clear_overlap(self):
        self.assertTrue(ranges_overlap(0, 10, 5, 15))

    def test_touching_is_not_overlap(self):
        # half-open intervals: [0,10) and [10,20) do not overlap.
        self.assertFalse(ranges_overlap(0, 10, 10, 20))

    def test_disjoint(self):
        self.assertFalse(ranges_overlap(0, 5, 10, 15))

    def test_contained(self):
        self.assertTrue(ranges_overlap(0, 100, 40, 50))


# --------------------------------------------------------------------------
# Classification + record-TC mapping math.
# --------------------------------------------------------------------------
class TestClassifyAndMap(unittest.TestCase):
    def test_full(self):
        long = [_mk_event("1", "R", "A", "10:00:00:00", "10:00:05:00",
                          "01:00:00:00", "01:00:05:00")]
        short = [_mk_event("1", "R", "A", "10:00:01:00", "10:00:02:00",
                           "02:00:00:00", "02:00:01:00")]
        res = match_events(short, long)
        self.assertEqual(res[0].status, FULL)
        m = res[0].matches[0]
        # short_in 10:00:01:00 maps to long.rec_in + (in - long.src_in)
        self.assertEqual(frames_to_tc(m.rec_in_f), "01:00:01:00")
        self.assertEqual(frames_to_tc(m.rec_out_f), "01:00:02:00")

    def test_partial(self):
        long = [_mk_event("1", "R", "A", "11:00:02:00", "11:00:06:00",
                          "01:00:05:00", "01:00:09:00")]
        short = [_mk_event("1", "R", "A", "11:00:04:00", "11:00:08:00",
                           "02:00:00:00", "02:00:04:00")]
        res = match_events(short, long)
        self.assertEqual(res[0].status, PARTIAL)
        m = res[0].matches[0]
        # overlap = [11:00:04:00, 11:00:06:00); maps onto long record.
        self.assertEqual(frames_to_tc(m.rec_in_f), "01:00:07:00")
        self.assertEqual(frames_to_tc(m.rec_out_f), "01:00:09:00")

    def test_none(self):
        long = [_mk_event("1", "REELX", "A", "10:00:00:00", "10:00:05:00",
                          "01:00:00:00", "01:00:05:00")]
        short = [_mk_event("1", "REELZ", "A", "10:00:01:00", "10:00:02:00",
                           "02:00:00:00", "02:00:01:00")]
        res = match_events(short, long)
        self.assertEqual(res[0].status, NONE)
        self.assertEqual(res[0].matches, [])

    def test_same_source_no_tc_overlap_is_none(self):
        long = [_mk_event("1", "R", "A", "10:00:00:00", "10:00:05:00",
                          "01:00:00:00", "01:00:05:00")]
        short = [_mk_event("1", "R", "A", "10:00:10:00", "10:00:12:00",
                           "02:00:00:00", "02:00:02:00")]
        res = match_events(short, long)
        self.assertEqual(res[0].status, NONE)

    def test_take_reused_twice(self):
        long = [
            _mk_event("1", "R", "A", "12:00:10:00", "12:00:14:00",
                      "01:00:09:00", "01:00:13:00"),
            _mk_event("2", "R", "A", "12:00:10:00", "12:00:14:00",
                      "01:01:00:00", "01:01:04:00"),
        ]
        short = [_mk_event("1", "R", "A", "12:00:11:00", "12:00:13:00",
                           "02:00:00:00", "02:00:02:00")]
        res = match_events(short, long)
        self.assertEqual(res[0].status, FULL)
        self.assertEqual(len(res[0].matches), 2)
        recs = sorted(frames_to_tc(m.rec_in_f) for m in res[0].matches)
        self.assertEqual(recs, ["01:00:10:00", "01:01:01:00"])


# --------------------------------------------------------------------------
# Non-overlap guard.
# --------------------------------------------------------------------------
class TestNonOverlapGuard(unittest.TestCase):
    def test_no_overlap_passthrough(self):
        blocks = [CaptionBlock(0, 10, "a"), CaptionBlock(20, 30, "b")]
        out = enforce_non_overlap(blocks)
        self.assertEqual([(b.start_f, b.end_f) for b in out],
                         [(0, 10), (20, 30)])

    def test_truncate_previous(self):
        blocks = [CaptionBlock(0, 100, "a"), CaptionBlock(50, 60, "b")]
        out = enforce_non_overlap(blocks)
        # previous end truncated to 50 - 1 = 49
        self.assertEqual([(b.start_f, b.end_f) for b in out],
                         [(0, 49), (50, 60)])

    def test_drop_collapsed(self):
        # second block starts at same frame -> previous collapses and drops.
        blocks = [CaptionBlock(10, 20, "a"), CaptionBlock(10, 30, "b")]
        log = []
        out = enforce_non_overlap(blocks, log=log)
        self.assertEqual([(b.start_f, b.end_f) for b in out], [(10, 30)])
        self.assertTrue(any("Dropped" in line for line in log))

    def test_zero_overlaps_in_result(self):
        # A messy stack must come out strictly non-overlapping.
        blocks = [
            CaptionBlock(0, 50, "a"), CaptionBlock(10, 60, "b"),
            CaptionBlock(55, 100, "c"), CaptionBlock(90, 95, "d"),
        ]
        out = enforce_non_overlap(blocks)
        for i in range(1, len(out)):
            self.assertGreater(out[i].start_f, out[i - 1].end_f,
                               "blocks must not overlap or touch")


# --------------------------------------------------------------------------
# Caption text assembly.
# --------------------------------------------------------------------------
class TestCaptionText(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(build_caption_text("REELA"), "REELA")

    def test_newline_escaped(self):
        self.assertEqual(build_caption_text("a\nb"), "a&a;b")

    def test_empty(self):
        self.assertEqual(build_caption_text(""), "(no source file)")


# --------------------------------------------------------------------------
# Parser quirks against the real Avid format.
# --------------------------------------------------------------------------
class TestParser(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".edl")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_no_space_after_asterisk(self):
        path = self._write(
            "TITLE: t\nFCM: NON-DROP FRAME\n"
            "000001  REELA  A  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n"
            "*FROM CLIP NAME:  SCENE_A*\n"
            "*SOURCE FILE: REELA\n")
        res = parse_edl(path)
        self.assertEqual(len(res.events), 1)
        self.assertEqual(res.events[0].source_file, "REELA")
        self.assertEqual(res.events[0].from_clip_name, "SCENE_A*")

    def test_wide_reel_field_tokenised(self):
        wide = "REELWITHAVERYLONGNAME_128" + " " * 80
        path = self._write(
            "FCM: NON-DROP FRAME\n"
            "000001  %s A2  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n"
            "*SOURCE FILE: REELWITHAVERYLONGNAME_128\n" % wide)
        res = parse_edl(path)
        self.assertEqual(res.events[0].track, "A2")
        self.assertEqual(res.events[0].reel, "REELWITHAVERYLONGNAME_128")

    def test_dissolve_with_duration_token(self):
        # D transition carries a duration token before the 4 TCs.
        path = self._write(
            "FCM: NON-DROP FRAME\n"
            "000001  REELA  A  D  030 10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n"
            "*SOURCE FILE: REELA\n")
        res = parse_edl(path)
        self.assertEqual(len(res.events), 1)
        self.assertEqual(res.events[0].src_in, "10:00:00:00")
        self.assertEqual(res.events[0].rec_out, "01:00:01:00")

    def test_to_clip_name_ignored(self):
        path = self._write(
            "FCM: NON-DROP FRAME\n"
            "000001  REELA  A  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n"
            "*FROM CLIP NAME:  SCENE_A*\n"
            "*TO CLIP NAME:  SCENE_A*\n"
            "*SOURCE FILE: REELA\n")
        res = parse_edl(path)
        self.assertEqual(res.events[0].source_file, "REELA")

    def test_drop_frame_aborts(self):
        path = self._write("FCM: DROP FRAME\n")
        with self.assertRaises(EDLParseError):
            parse_edl(path)

    def test_missing_fcm_aborts(self):
        path = self._write(
            "000001  REELA  A  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n")
        with self.assertRaises(EDLParseError):
            parse_edl(path)

    def test_blank_source_file_warns(self):
        path = self._write(
            "FCM: NON-DROP FRAME\n"
            "000001  REELA  A  C  10:00:00:00 10:00:01:00 01:00:00:00 01:00:01:00\n"
            "*FROM CLIP NAME:  SCENE_A*\n")
        res = parse_edl(path)
        self.assertEqual(res.events[0].key(), "SCENE_A*")  # falls back
        self.assertTrue(any("no SOURCE FILE" in w for w in res.warnings))

    def test_unparseable_line_flagged_not_dropped(self):
        path = self._write(
            "FCM: NON-DROP FRAME\n"
            "000001  REELA  A  C  not a timecode here at all xx yy\n"
            "*SOURCE FILE: REELA\n")
        res = parse_edl(path)
        self.assertEqual(len(res.events), 0)
        self.assertEqual(len(res.errors), 1)


# --------------------------------------------------------------------------
# SubCap format validator + full integration on synthetic data.
# --------------------------------------------------------------------------
TC_PAIR_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2}) (\d{2}:\d{2}:\d{2}:\d{2})$")


def validate_subcap(path):
    """Parse a SubCap file, assert format rules, and return the (start,end)
    frame ranges. Raises AssertionError on any violation."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert lines[0] == HEADER, "bad header line"
    assert lines[1] == BEGIN, "missing <begin subtitles>"
    assert END in lines, "missing <end subtitles>"

    ranges = []
    i = 2
    end_idx = lines.index(END)
    while i < end_idx:
        if lines[i] == "":
            i += 1
            continue
        m = TC_PAIR_RE.match(lines[i])
        assert m, "bad TC line: %r" % lines[i]
        # frames field must be <= 23
        for tc in m.groups():
            assert int(tc.split(":")[3]) <= 23, "FF > 23 in %r" % tc
        text = lines[i + 1]
        assert text != "", "empty caption text after %r" % lines[i]
        assert "\n" not in text, "caption text must be one line"
        ranges.append((tc_to_frames(m.group(1)), tc_to_frames(m.group(2))))
        i += 2
    return ranges


class TestIntegration(unittest.TestCase):
    def test_synthetic_end_to_end(self):
        out_dir = tempfile.mkdtemp()
        long_res = parse_edl(os.path.join(SAMPLE, "synthetic_long.edl"))
        short_res = parse_edl(os.path.join(SAMPLE, "synthetic_short.edl"))
        self.assertEqual(len(long_res.errors), 0)
        self.assertEqual(len(short_res.errors), 0)

        results = match_events(short_res.events, long_res.events)
        by_edit = {r.short_event.edit_num: r for r in results}

        self.assertEqual(by_edit["000001"].status, FULL)
        self.assertEqual(by_edit["000002"].status, PARTIAL)
        self.assertEqual(by_edit["000003"].status, NONE)
        # take reused twice in the long cut -> two matches
        self.assertEqual(by_edit["000004"].status, FULL)
        self.assertEqual(len(by_edit["000004"].matches), 2)

        subcap = os.path.join(out_dir, "subcap.txt")
        blocks = blocks_from_matches(results)
        write_subcap(blocks, subcap)

        ranges = validate_subcap(subcap)
        # MANDATORY: zero overlapping ranges in the final file.
        for j in range(1, len(ranges)):
            self.assertGreater(ranges[j][0], ranges[j - 1][1],
                               "SubCap file contains overlapping ranges")

        n_nomatch = write_no_match_report(
            results, os.path.join(out_dir, "no_match.csv"))
        self.assertEqual(n_nomatch, 1)  # only REELZ_NOMATCH
        write_match_report(results, os.path.join(out_dir, "match_report.csv"))

    def test_real_edls_if_present(self):
        long_p = os.path.join(os.path.dirname(SAMPLE), "edltest", "103 long.edl")
        short_p = os.path.join(os.path.dirname(SAMPLE), "edltest", "103 short.edl")
        if not (os.path.exists(long_p) and os.path.exists(short_p)):
            self.skipTest("real sample EDLs not present")
        long_res = parse_edl(long_p)
        short_res = parse_edl(short_p)
        self.assertEqual(len(long_res.errors), 0)
        self.assertEqual(len(short_res.errors), 0)
        results = match_events(short_res.events, long_res.events)
        out_dir = tempfile.mkdtemp()
        subcap = os.path.join(out_dir, "subcap.txt")
        write_subcap(blocks_from_matches(results), subcap)
        ranges = validate_subcap(subcap)
        for j in range(1, len(ranges)):
            self.assertGreater(ranges[j][0], ranges[j - 1][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
