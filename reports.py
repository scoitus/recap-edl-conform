"""CSV QC reports: the no-match report and the full match report."""

import csv

from matcher import NONE


def write_no_match_report(short_results, out_path):
    """Output 2: SHORT events classified NONE (in the cutdown, not in the long
    cut). Columns: short edit#, track, source file, from-clip-name, short rec
    in, short rec out. Returns the number of rows written."""
    rows = 0
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["short_edit", "track", "source_file", "from_clip_name",
                    "short_rec_in", "short_rec_out"])
        for sr in short_results:
            if sr.status != NONE:
                continue
            se = sr.short_event
            w.writerow([se.edit_num, se.track, se.source_file,
                        se.from_clip_name, se.rec_in, se.rec_out])
            rows += 1
    return rows


def write_match_report(short_results, out_path):
    """Output 3: every SHORT event, with mapped long record TCs for matches.

    One row per (short event, matching long event) pair so a take reused
    several times is fully visible; NONE events get a single row with blank
    long fields. Returns the number of rows written.
    """
    from edl_parser import frames_to_tc

    rows = 0
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["short_edit", "track", "source_file", "from_clip_name",
                    "short_rec_in", "short_rec_out", "status",
                    "long_edit", "mapped_rec_in", "mapped_rec_out"])
        for sr in short_results:
            se = sr.short_event
            short_cols = [se.edit_num, se.track, se.source_file,
                          se.from_clip_name, se.rec_in, se.rec_out, sr.status]
            if sr.status == NONE or not sr.matches:
                w.writerow(short_cols + ["", "", ""])
                rows += 1
                continue
            for m in sr.matches:
                w.writerow(short_cols + [m.long_event.edit_num,
                                         frames_to_tc(m.rec_in_f),
                                         frames_to_tc(m.rec_out_f)])
                rows += 1
    return rows
