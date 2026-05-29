"""CMX3600 / File_128 EDL parser for 23.98 fps NON-DROP Avid exports.

CRITICAL: Avid labels 23.98 timecode at 24 frames/sec, non-drop (frames run
00-23). ALL integer frame math uses 24 fps non-drop. We assert that no frame
field exceeds 23; a value of 24+ signals a wrong-rate export and aborts the run.
"""

import re

FPS = 24  # 23.98 NDF is counted at 24 integer frames/sec, FF 00-23.

# A timecode token: HH:MM:SS:FF
TC_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}:\d{2}$")
# Event line begins with a (zero-padded) edit number.
EVENT_RE = re.compile(r"^(\d+)\s+(.*)$")
# Comment matchers. Avid writes "*SOURCE FILE:" with NO space after the
# asterisk; we allow an optional space to be tolerant of either style.
SOURCE_FILE_RE = re.compile(r"^\*\s*SOURCE FILE:\s*(.*)$", re.IGNORECASE)
FROM_CLIP_RE = re.compile(r"^\*\s*FROM CLIP NAME:\s*(.*)$", re.IGNORECASE)


class EDLParseError(Exception):
    """Raised for unrecoverable EDL problems (wrong rate, bad header, etc.)."""


class Event:
    """One EDL edit event plus its attached comments."""

    __slots__ = (
        "edit_num", "reel", "track", "transition",
        "src_in", "src_out", "rec_in", "rec_out",
        "src_in_f", "src_out_f", "rec_in_f", "rec_out_f",
        "source_file", "from_clip_name", "line_no",
    )

    def __init__(self, edit_num, reel, track, transition,
                 src_in, src_out, rec_in, rec_out, line_no):
        self.edit_num = edit_num
        self.reel = reel
        self.track = track
        self.transition = transition
        self.src_in = src_in
        self.src_out = src_out
        self.rec_in = rec_in
        self.rec_out = rec_out
        self.src_in_f = tc_to_frames(src_in)
        self.src_out_f = tc_to_frames(src_out)
        self.rec_in_f = tc_to_frames(rec_in)
        self.rec_out_f = tc_to_frames(rec_out)
        self.source_file = ""
        self.from_clip_name = ""
        self.line_no = line_no

    def key(self):
        """Matching key: SOURCE FILE, falling back to FROM CLIP NAME."""
        if self.source_file:
            return self.source_file
        return self.from_clip_name

    def __repr__(self):
        return ("Event(#%s %s %s src %s-%s rec %s-%s sf=%r)" % (
            self.edit_num, self.track, self.transition,
            self.src_in, self.src_out, self.rec_in, self.rec_out,
            self.source_file))


def tc_to_frames(tc):
    """Convert HH:MM:SS:FF (24fps NDF) to an integer frame count.

    Asserts the frames field is <= 23; anything higher means the EDL was
    exported at the wrong rate (e.g. 30fps) and must abort.
    """
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2}):(\d{2})$", tc)
    if not m:
        raise EDLParseError("Malformed timecode: %r" % (tc,))
    hh, mm, ss, ff = (int(x) for x in m.groups())
    if ff > FPS - 1:
        raise EDLParseError(
            "Frame field %02d in %r exceeds %d (24fps NDF max). "
            "This signals a wrong-rate EDL export." % (ff, tc, FPS - 1))
    if mm > 59 or ss > 59:
        raise EDLParseError("Invalid minutes/seconds in timecode: %r" % (tc,))
    return ((hh * 60 + mm) * 60 + ss) * FPS + ff


def frames_to_tc(frames):
    """Convert an integer frame count back to HH:MM:SS:FF (24fps NDF)."""
    if frames < 0:
        raise EDLParseError("Negative frame count: %d" % frames)
    ff = frames % FPS
    total_secs = frames // FPS
    ss = total_secs % 60
    mm = (total_secs // 60) % 60
    hh = total_secs // 3600
    return "%02d:%02d:%02d:%02d" % (hh, mm, ss, ff)


class ParseResult:
    def __init__(self):
        self.events = []
        self.warnings = []   # non-fatal issues (e.g. event keyed by clip name)
        self.errors = []     # lines that could not be parsed


def parse_edl(path):
    """Parse an EDL file. Returns a ParseResult.

    Lines that cannot be parsed are recorded in result.errors rather than
    silently dropped. A wrong FCM rate or wrong-rate timecode aborts with
    EDLParseError.
    """
    result = ParseResult()
    fcm_seen = False
    current = None

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            stripped = line.strip()

            if not stripped:
                continue

            # Header: FCM rate declaration.
            if stripped.upper().startswith("FCM:"):
                fcm_seen = True
                if "NON-DROP" not in stripped.upper():
                    raise EDLParseError(
                        "FCM is not NON-DROP FRAME (line %d): %r. This tool "
                        "requires non-drop." % (line_no, stripped))
                continue

            if stripped.upper().startswith("TITLE:"):
                continue

            # Comment lines belong to the event immediately above.
            if stripped.startswith("*"):
                if current is None:
                    # A comment with no preceding event; record and move on.
                    result.warnings.append(
                        "Comment before any event (line %d): %r"
                        % (line_no, stripped))
                    continue
                m = SOURCE_FILE_RE.match(stripped)
                if m:
                    current.source_file = m.group(1).strip()
                    continue
                m = FROM_CLIP_RE.match(stripped)
                if m:
                    current.from_clip_name = m.group(1).strip()
                    continue
                # Other comments (*TO CLIP NAME:, effects, etc.) are ignored.
                continue

            # Otherwise it should be an event line.
            event = _parse_event_line(stripped, line_no, result)
            if event is not None:
                result.events.append(event)
                current = event

    if not fcm_seen:
        raise EDLParseError(
            "No FCM header found in %s; cannot confirm non-drop." % path)

    # Resolve matching keys and warn for any event keyed by clip name.
    for ev in result.events:
        if not ev.source_file:
            if ev.from_clip_name:
                result.warnings.append(
                    "Event #%s (line %d) has no SOURCE FILE; keyed by FROM "
                    "CLIP NAME %r." % (ev.edit_num, ev.line_no,
                                       ev.from_clip_name))
            else:
                result.warnings.append(
                    "Event #%s (line %d) has neither SOURCE FILE nor FROM "
                    "CLIP NAME; cannot be keyed."
                    % (ev.edit_num, ev.line_no))

    return result


def _parse_event_line(line, line_no, result):
    """Parse a single event line via whitespace tokenisation.

    Layout: <edit#> <reel> <channel> <transition> [dur ...] <src_in>
    <src_out> <rec_in> <rec_out>. We do NOT assume fixed-width columns
    (File_128 widens the reel field). The last four tokens are always the
    four timecodes; anything between the transition and those TCs (a
    dissolve duration, for example) is ignored.
    """
    m = EVENT_RE.match(line)
    if not m:
        result.errors.append("Unparseable line %d: %r" % (line_no, line))
        return None

    tokens = line.split()
    if len(tokens) < 8:
        result.errors.append(
            "Event line %d has too few fields (%d): %r"
            % (line_no, len(tokens), line))
        return None

    edit_num = tokens[0]
    reel = tokens[1]
    track = tokens[2]
    transition = tokens[3]

    tcs = tokens[-4:]
    for tc in tcs:
        if not TC_RE.match(tc):
            result.errors.append(
                "Event line %d: expected 4 trailing timecodes, found %r in "
                "%r" % (line_no, tc, line))
            return None

    # Transitions: any non-C code (D, W, ...) is treated as a plain cut on the
    # incoming event's record-in. We keep the code for reference but do not act
    # on it differently.
    try:
        return Event(edit_num, reel, track, transition,
                     tcs[0], tcs[1], tcs[2], tcs[3], line_no)
    except EDLParseError:
        # Re-raise wrong-rate / malformed TC: these are fatal by design.
        raise
