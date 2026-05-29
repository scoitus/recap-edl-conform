# recap-edl-conform

Avid EDL cross-reference → SubCap cut-point generator.

Compares two CMX3600 / File_128 EDLs exported from Avid Media Composer — a long
sequence and a shorter cutdown of the same production dialogue — and works out
whether and where each clip in the cutdown appears in the long sequence. The
primary output is an Avid SubCap caption file you import into the long sequence
to visualize cut points, plus two QC reports.

## Requirements
- Python 3 (standard library only — `argparse`, `re`, `csv`).
- EDLs exported at **23.98 fps NON-DROP** with **Source File Names comments ON**
  (every event must carry `*SOURCE FILE:` and `*FROM CLIP NAME:`).

> **Rate note:** Avid labels 23.98 timecode at 24 frames/sec, non-drop (frames
> field runs 00–23). All integer frame math here uses **24 fps non-drop**. If any
> timecode's frame field exceeds 23, the run aborts — that signals a wrong-rate
> export.

## Usage
```
python3 main.py --long "long.edl" --short "short.edl" --out-dir ./out
```
Writes three files into `--out-dir`:

| File | Contents |
|------|----------|
| `subcap.txt` | Avid SubCap caption file (one caption per matched cut point, source file as text). Guaranteed non-overlapping. |
| `no_match.csv` | Short events with **no** match in the long cut (new material). |
| `match_report.csv` | Every short event with status (FULL/PARTIAL/NONE) and, for matches, the mapped long-sequence record TC + matching long edit#. |

Example against the included samples:
```
python3 main.py --long "edltest/103 long.edl" --short "edltest/103 short.edl" --out-dir ./out
```

## How it works
- **Parsing** (`edl_parser.py`): asserts `FCM: NON-DROP FRAME`; tokenises event
  lines on whitespace (the last four tokens are always the four timecodes, so the
  wide File_128 reel field and dissolve duration tokens are handled); attaches
  `*SOURCE FILE:` / `*FROM CLIP NAME:` comments to the event above. Unparseable
  lines are flagged, never silently dropped.
- **Matching** (`matcher.py`): primary key is `*SOURCE FILE:` (falls back to
  `*FROM CLIP NAME:` with a warning). For each short event, finds every long
  event with the same key whose source TC range overlaps, classifies it
  **FULL / PARTIAL / NONE**, and maps the overlapping source range onto the long
  sequence's record timeline.
- **SubCap output** (`subcap_writer.py`): builds one caption per matched pair,
  then runs the **mandatory non-overlap guard** — sorts by start frame and
  truncates/drops overlaps, because Avid rejects the entire file if any two
  caption ranges overlap (A1–A4 dialogue routinely overlaps).
- **Reports** (`reports.py`): the two QC CSVs.

## Tests
```
python3 -m unittest discover -s tests
```
Covers TC↔frame conversion (incl. the FF≤23 abort), overlap detection,
FULL/PARTIAL/NONE classification, record-TC mapping math, the non-overlap guard,
parser quirks, and a full integration run that validates the generated SubCap and
asserts zero overlapping ranges. Synthetic test EDLs live in `sample_data/`.

## Layout
```
edl_parser.py     EDL parsing + TC<->frame conversion
matcher.py        source-file + TC-overlap matching, classification, mapping
subcap_writer.py  SubCap writer incl. non-overlap guard
reports.py        no-match and match-report CSVs
main.py           CLI
tests/            unit + integration tests
sample_data/      synthetic 23.98 NDF test EDLs
```
