"""Avid SubCap (.txt) caption writer, including the mandatory non-overlap guard.

Avid rejects the ENTIRE file if any two caption timecode ranges overlap. A1-A4
dialogue WILL produce overlapping mapped record ranges, so after building all
blocks we sort them and truncate any overlap before emitting. The output is
intentionally minimal (one source-file string per caption) but the guard is
non-negotiable.
"""

from edl_parser import frames_to_tc

BEGIN = "<begin subtitles>"
END = "<end subtitles>"


class CaptionBlock:
    __slots__ = ("start_f", "end_f", "text", "source")

    def __init__(self, start_f, end_f, text, source=None):
        self.start_f = start_f
        self.end_f = end_f
        self.text = text
        self.source = source  # optional provenance for QC/logging


def build_caption_text(clip_name, source_file=None, short_rec_in=None,
                       status=None, track=None, **extra):
    """Assemble the single-line caption text for a block.

    Produces e.g. `[A1/V] [short rec 01:00:02:00] take_07A_03  FULL`: the
    LONG-sequence track(s) the clip lands on (multiple are joined with `/`),
    the short sequence's record in-point, the clip name, then the match status
    (FULL/PARTIAL). The name falls back to the Source File when FROM CLIP NAME
    is absent. Kept tiny and in one place so fields can be added later. A SubCap
    caption must be ONE line; a literal line break has to be escaped as `&a;`.
    """
    name = clip_name or source_file or "(no clip name)"
    parts = []
    if track:
        parts.append("[%s]" % track)
    if short_rec_in:
        parts.append("[short rec %s]" % short_rec_in)
    parts.append(name)
    if status:
        parts.append(" %s" % status)
    text = " ".join(parts)
    return text.replace("\r\n", "&a;").replace("\n", "&a;").replace("\r", "&a;")


def _merge_contiguous(matches):
    """Group a short event's matches into contiguous spans.

    A take that continues across consecutive long events maps to touching /
    overlapping record ranges; those become a single caption spanning the
    whole appearance. This also collapses a clip that lives on several long
    tracks at the same record position (e.g. V + A1) into one group, so the
    caption can list every track the appearance touches. A take genuinely
    reused at a separate spot in the long sequence leaves a gap and stays a
    separate group. Returns a list of (start_f, end_f, [long_event, ...])
    tuples, where the long_event list carries every long edit in the group.
    """
    ordered = sorted(matches, key=lambda m: (m.rec_in_f, m.rec_out_f))
    groups = []
    for m in ordered:
        if groups and m.rec_in_f <= groups[-1][1]:  # touching or overlapping
            start, end, evs = groups[-1]
            groups[-1] = (start, max(end, m.rec_out_f),
                          evs + [m.long_event])
        else:
            groups.append((m.rec_in_f, m.rec_out_f, [m.long_event]))
    return groups


def blocks_from_matches(short_results):
    """Build CaptionBlocks for matched short events.

    NONE-classified short events produce no caption. Each short event yields
    ONE caption per contiguous appearance in the long sequence: matches that
    are contiguous (a take split across adjacent long events) merge into a
    single block spanning their full record range, while matches at separate
    spots in the long cut stay as separate blocks.
    """
    blocks = []
    for sr in short_results:
        for start_f, end_f, long_events in _merge_contiguous(sr.matches):
            edits = [le.edit_num for le in long_events]
            # The LONG-sequence track(s) this appearance lands on. A clip cut
            # to several tracks (V + A1 + A2) collapses into one group, so we
            # list every distinct track it touches.
            tracks = sorted({le.track for le in long_events if le.track})
            track_label = "/".join(tracks)
            text = build_caption_text(
                sr.short_event.from_clip_name,
                source_file=sr.short_event.source_file,
                short_rec_in=sr.short_event.rec_in,
                status=sr.status,
                track=track_label)
            blocks.append(CaptionBlock(
                start_f, end_f, text,
                source="short#%s ->long#%s [%s]" % (
                    sr.short_event.edit_num, ",".join(edits), track_label)))
    return blocks


def enforce_non_overlap(blocks, log=None):
    """Sort blocks by start frame and remove all overlaps in place.

    Rule (per spec): if a block starts before the previous block ends,
    truncate the previous block's end to (next start - 1 frame). If that
    leaves the previous block <= 0 frames, drop it and log it. Returns the
    cleaned, non-overlapping list sorted by start frame.
    """
    if log is None:
        log = []

    ordered = sorted(blocks, key=lambda b: (b.start_f, b.end_f))
    result = []
    overlap_count = 0
    total_truncation = 0
    dropped = 0

    for block in ordered:
        if result:
            prev = result[-1]
            if block.start_f <= prev.end_f:  # overlap (touching counts)
                overlap_count += 1
                new_end = block.start_f - 1
                total_truncation += (prev.end_f - new_end)
                prev.end_f = new_end
                if prev.end_f - prev.start_f <= 0:
                    # Truncation collapsed the previous block; drop it.
                    log.append(
                        "Dropped zero/negative-length caption after "
                        "truncation: %s (start %s)"
                        % (prev.source, frames_to_tc(prev.start_f)))
                    result.pop()
                    dropped += 1
                else:
                    log.append(
                        "Truncated caption %s to end %s (overlap with next "
                        "start %s)" % (prev.source, frames_to_tc(prev.end_f),
                                       frames_to_tc(block.start_f)))
        result.append(block)

    log.append("Non-overlap guard: %d overlaps resolved, %d frames truncated, "
               "%d block(s) dropped." % (overlap_count, total_truncation,
                                         dropped))
    return result


def write_subcap(blocks, out_path, log=None):
    """Write a strict, import-safe SubCap file. Always runs the guard first.

    Returns the list of blocks actually emitted (post-guard).
    """
    clean = enforce_non_overlap(blocks, log=log)

    lines = [BEGIN, ""]
    for b in clean:
        lines.append("%s %s" % (frames_to_tc(b.start_f),
                                frames_to_tc(b.end_f)))
        lines.append(b.text)
        lines.append("")
    lines.append(END)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return clean
