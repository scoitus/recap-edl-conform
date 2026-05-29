"""Avid SubCap (.txt) caption writer, including the mandatory non-overlap guard.

Avid rejects the ENTIRE file if any two caption timecode ranges overlap. A1-A4
dialogue WILL produce overlapping mapped record ranges, so after building all
blocks we sort them and truncate any overlap before emitting. The output is
intentionally minimal (one source-file string per caption) but the guard is
non-negotiable.
"""

from edl_parser import frames_to_tc

HEADER = "@ This file written with the Avid Caption plugin, version 1."
BEGIN = "<begin subtitles>"
END = "<end subtitles>"


class CaptionBlock:
    __slots__ = ("start_f", "end_f", "text", "source")

    def __init__(self, start_f, end_f, text, source=None):
        self.start_f = start_f
        self.end_f = end_f
        self.text = text
        self.source = source  # optional provenance for QC/logging


def build_caption_text(clip_name, **extra):
    """Assemble the single-line caption text for a block.

    Kept deliberately tiny and in one place so additional fields can be folded
    in later. A SubCap caption must be ONE line; a literal line break has to be
    escaped as `&a;`.
    """
    text = clip_name if clip_name else "(no clip name)"
    return text.replace("\r\n", "&a;").replace("\n", "&a;").replace("\r", "&a;")


def blocks_from_matches(short_results):
    """Build one CaptionBlock per matched (short, long) pair.

    NONE-classified short events produce no caption. A short event matching
    several long events yields one block per match (each reuse point).
    """
    blocks = []
    for sr in short_results:
        for m in sr.matches:
            text = build_caption_text(sr.short_event.from_clip_name)
            blocks.append(CaptionBlock(
                m.rec_in_f, m.rec_out_f, text,
                source="short#%s->long#%s" % (
                    sr.short_event.edit_num, m.long_event.edit_num)))
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

    lines = [HEADER, BEGIN, ""]
    for b in clean:
        lines.append("%s %s" % (frames_to_tc(b.start_f),
                                frames_to_tc(b.end_f)))
        lines.append(b.text)
        lines.append("")
    lines.append(END)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return clean
