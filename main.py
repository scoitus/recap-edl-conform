"""CLI: cross-reference a long Avid EDL against a short cutdown and emit an
Avid SubCap caption file plus two QC reports.

    python main.py --long long.edl --short short.edl --out-dir ./out

Produces subcap.txt, no_match.csv, match_report.csv. Stdlib only.
"""

import argparse
import os
import sys

from edl_parser import parse_edl, EDLParseError
from matcher import match_events, FULL, PARTIAL, NONE
from subcap_writer import blocks_from_matches, write_subcap
from reports import write_no_match_report, write_match_report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Avid EDL cross-reference -> SubCap cut-point generator "
                    "(23.98 fps NON-DROP, 24fps integer math).")
    ap.add_argument("--long", required=True, help="Long sequence EDL")
    ap.add_argument("--short", required=True, help="Short cutdown EDL")
    ap.add_argument("--out-dir", default="./out", help="Output directory")
    args = ap.parse_args(argv)

    try:
        long_res = parse_edl(args.long)
        short_res = parse_edl(args.short)
    except EDLParseError as e:
        print("ABORT: %s" % e, file=sys.stderr)
        return 2

    _report_parse(args.long, long_res)
    _report_parse(args.short, short_res)

    short_results = match_events(short_res.events, long_res.events)

    counts = {FULL: 0, PARTIAL: 0, NONE: 0}
    for sr in short_results:
        counts[sr.status] += 1
    print("Classification: %d FULL, %d PARTIAL, %d NONE (of %d short events)"
          % (counts[FULL], counts[PARTIAL], counts[NONE], len(short_results)))

    os.makedirs(args.out_dir, exist_ok=True)
    subcap_path = os.path.join(args.out_dir, "subcap.txt")
    no_match_path = os.path.join(args.out_dir, "no_match.csv")
    match_report_path = os.path.join(args.out_dir, "match_report.csv")

    blocks = blocks_from_matches(short_results)
    guard_log = []
    emitted = write_subcap(blocks, subcap_path, log=guard_log)
    for line in guard_log:
        print("  " + line)
    print("Wrote %s (%d caption blocks from %d matched pairs)"
          % (subcap_path, len(emitted), len(blocks)))

    n_nomatch = write_no_match_report(short_results, no_match_path)
    print("Wrote %s (%d no-match rows)" % (no_match_path, n_nomatch))

    n_match = write_match_report(short_results, match_report_path)
    print("Wrote %s (%d rows)" % (match_report_path, n_match))

    return 0


def _report_parse(path, res):
    print("Parsed %s: %d events, %d warnings, %d errors"
          % (path, len(res.events), len(res.warnings), len(res.errors)))
    for w in res.warnings:
        print("  WARN: %s" % w)
    for e in res.errors:
        print("  ERROR (unparsed): %s" % e)


if __name__ == "__main__":
    sys.exit(main())
