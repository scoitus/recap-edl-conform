"""Cross-reference SHORT events against LONG events by source file + TC overlap.

For each SHORT event, find every LONG event with the same matching key whose
source timecode range overlaps, classify the relationship (FULL / PARTIAL /
NONE), and map the overlapping source range to the LONG sequence's record TC.
"""

FULL = "FULL"
PARTIAL = "PARTIAL"
NONE = "NONE"


class Match:
    """One (short event, long event) overlapping pair with mapped record TC."""

    __slots__ = (
        "long_event", "overlap_src_in_f", "overlap_src_out_f",
        "rec_in_f", "rec_out_f",
    )

    def __init__(self, long_event, overlap_src_in_f, overlap_src_out_f,
                 rec_in_f, rec_out_f):
        self.long_event = long_event
        self.overlap_src_in_f = overlap_src_in_f
        self.overlap_src_out_f = overlap_src_out_f
        self.rec_in_f = rec_in_f
        self.rec_out_f = rec_out_f


class ShortResult:
    """Classification + all matches for a single SHORT event."""

    __slots__ = ("short_event", "status", "matches")

    def __init__(self, short_event, status, matches):
        self.short_event = short_event
        self.status = status
        self.matches = matches


def ranges_overlap(a_in, a_out, b_in, b_out):
    """True if [a_in,a_out) and [b_in,b_out) overlap (half-open intervals)."""
    return max(a_in, b_in) < min(a_out, b_out)


def _index_long(long_events):
    """Group LONG events by matching key for fast lookup."""
    index = {}
    for ev in long_events:
        index.setdefault(ev.key(), []).append(ev)
    return index


def match_events(short_events, long_events):
    """Return a list of ShortResult, one per SHORT event, in input order."""
    index = _index_long(long_events)
    results = []

    for se in short_events:
        key = se.key()
        candidates = index.get(key, []) if key else []
        matches = []

        for le in candidates:
            if not ranges_overlap(se.src_in_f, se.src_out_f,
                                  le.src_in_f, le.src_out_f):
                continue

            overlap_in = max(se.src_in_f, le.src_in_f)
            overlap_out = min(se.src_out_f, le.src_out_f)

            # Map the overlapping source range onto the LONG sequence's record
            # timeline. Import TCs match the long sequence with no offset.
            rec_in = le.rec_in_f + (overlap_in - le.src_in_f)
            rec_out = le.rec_in_f + (overlap_out - le.src_in_f)

            matches.append(Match(le, overlap_in, overlap_out, rec_in, rec_out))

        status = _classify(se, matches)
        results.append(ShortResult(se, status, matches))

    return results


def _classify(short_event, matches):
    """FULL if the short range sits entirely inside some long range;
    PARTIAL if it overlaps but spills beyond every match; NONE if no match."""
    if not matches:
        return NONE

    for m in matches:
        le = m.long_event
        if le.src_in_f <= short_event.src_in_f and \
                short_event.src_out_f <= le.src_out_f:
            return FULL

    return PARTIAL
