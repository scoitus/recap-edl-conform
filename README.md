# recap-edl-conform

Avid EDL cross-reference → SubCap cut-point generator.

Compares two CMX3600 / File_128 EDLs exported from Avid Media Composer — a long
sequence and a shorter cutdown of the same production dialogue — and works out
whether and where each clip in the cutdown appears in the long sequence. The
primary output is an Avid SubCap caption file you import into the long sequence
to visualize cut points, plus two QC reports.

## What you need

**To run the tool**
- **Python 3.8 or newer.** Check with `python3 --version`.
- No third-party packages — the tool uses only the Python standard library, so
  there is nothing to `pip install`.
- The double-click GUI also needs **tkinter** (ships with most Python builds; see
  [Install](#install) if the GUI won't open). The command-line version does not
  need tkinter.

**For your EDLs**
- Export at **23.98 fps NON-DROP**.
- Turn **Source File Names comments ON** so every event carries a `*SOURCE FILE:`
  and `*FROM CLIP NAME:` line. These are how clips are matched.

> **Rate note:** Avid labels 23.98 timecode at 24 frames/sec, non-drop (the
> frames field runs 00–23). All integer frame math here uses **24 fps non-drop**.
> If any timecode's frame field exceeds 23, the run aborts — that signals a
> wrong-rate export.

## Install

```bash
git clone https://github.com/scoitus/recap-edl-conform.git
cd recap-edl-conform
python3 --version          # confirm Python 3.8+
```

That's it for the command line — there are no dependencies to install.

**If you want the double-click GUI** and it won't open ("No module named
`tkinter`"), install tkinter for your platform:

| Platform | Command |
|----------|---------|
| macOS (Homebrew Python) | `brew install python-tk` |
| Debian / Ubuntu | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Windows / python.org installer | already included |

## Usage

### Double-click (GUI)
- **macOS:** double-click **`EDL SubCap.command`** in Finder.
- **Any platform:** run `python3 gui.py`.

A window opens where you browse for the long EDL, the short EDL, and an output
folder, then click **Generate**. Progress, warnings, and the output location are
shown in the window.

> macOS Gatekeeper note: the first time you double-click `EDL SubCap.command`,
> macOS may warn it's from an unidentified developer. Right-click the file →
> **Open** once (or go to *System Settings → Privacy & Security → Open Anyway*),
> and it will run normally afterward. If Finder reports it isn't executable, run
> `chmod +x "EDL SubCap.command"` once in the repo folder.

### Command line
```bash
python3 main.py --long path/to/long.edl --short path/to/short.edl --out-dir ./out
```
Quote paths that contain spaces.

### Output
Either way, three files are written into the output folder:

| File | Contents |
|------|----------|
| `subcap.txt` | Avid SubCap caption file. One caption per appearance of a short clip in the long cut (`[short rec HH:MM:SS:FF] clip_name  FULL/PARTIAL`); contiguous matches are merged into a single spanning caption, separate reuse spots stay distinct. Guaranteed non-overlapping. |
| `no_match.csv` | Short events with **no** match in the long cut (new material). |
| `match_report.csv` | Every short event with status (FULL/PARTIAL/NONE) and, for matches, the mapped long-sequence record TC + matching long edit#. |

Import `subcap.txt` into the long sequence in Avid to see the cut points.

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
- **SubCap output** (`subcap_writer.py`): merges each short event's contiguous
  matches into one caption per appearance (separate reuse spots stay distinct),
  then runs the **mandatory non-overlap guard** — sorts by start frame and
  truncates/drops overlaps, because Avid rejects the entire file if any two
  caption ranges overlap (A1–A4 dialogue routinely overlaps).
- **Reports** (`reports.py`): the two QC CSVs.

## Tests
```bash
python3 -m unittest discover -s tests
```
Covers TC↔frame conversion (incl. the FF≤23 abort), overlap detection,
FULL/PARTIAL/NONE classification, record-TC mapping math, the non-overlap guard,
parser quirks, and a full integration run that validates the generated SubCap and
asserts zero overlapping ranges. Synthetic test EDLs live in `sample_data/`, so
the suite runs without any real footage.

## Layout
```
edl_parser.py        EDL parsing + TC<->frame conversion
matcher.py           source-file + TC-overlap matching, classification, mapping
subcap_writer.py     SubCap writer incl. non-overlap guard
reports.py           no-match and match-report CSVs
main.py              CLI + shared run() pipeline
gui.py               tkinter GUI (file pickers + Generate button)
EDL SubCap.command   double-click launcher for the GUI (macOS)
tests/               unit + integration tests
sample_data/         synthetic 23.98 NDF test EDLs
```
