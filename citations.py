"""Citation markers.

The model is asked to write markers such as [S1] or [C12] after each statement.
It is never asked for page or paragraph numbers. This module checks every marker
against the passages that were really supplied and removes the rest, so the
location the reader sees always comes from stored metadata.

Standard library only, so it can be tested on its own.
"""
import re


def _marker_pattern(prefix):
    # Matches [S1], [S 1], [S1, S2], [S1; S3], [s1]
    return re.compile(
        r"\[\s*" + re.escape(prefix) + r"\s*(\d+(?:\s*[,;]\s*(?:" + re.escape(prefix) + r")?\s*\d+)*)\s*\]",
        re.IGNORECASE,
    )


def normalize_markers(text, prefix, valid_ids):
    """Keep only markers whose number is in `valid_ids`.

    Grouped markers are split into single ones: "[S1, S2]" becomes "[S1][S2]".
    Markers with no valid number are removed. Returns (clean_text, used_ids)
    where used_ids lists valid ids in order of first appearance.
    """
    valid = {int(v) for v in valid_ids}
    used = []
    pattern = _marker_pattern(prefix)

    def replace(match):
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        kept = []
        for number in numbers:
            if number in valid and number not in kept:
                kept.append(number)
        for number in kept:
            if number not in used:
                used.append(number)
        return "".join(f"[{prefix.upper()}{n}]" for n in kept)

    cleaned = pattern.sub(replace, text or "")
    # A removed marker can leave a doubled space or a space before punctuation.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip(), used


def replace_markers(text, prefix, labels):
    """Swap [C12] markers for readable locations like [p.3 ¶2].

    `labels` maps id -> label. Markers whose id is unknown are dropped.
    """
    valid = set(labels)
    cleaned, _ = normalize_markers(text, prefix, valid)
    pattern = re.compile(r"\[" + re.escape(prefix.upper()) + r"(\d+)\]")
    return pattern.sub(lambda m: f"[{labels[int(m.group(1))]}]", cleaned)


def short_label(page, para_start, para_end, fallback):
    """Compact location for chips: 'p.3 ¶2', 'p.3 ¶2–4', '¶5', or the fallback label."""
    if page is None and para_start is None:
        return fallback
    parts = []
    if page is not None:
        parts.append(f"p.{page}")
    if para_start is not None:
        if para_end is not None and para_end != para_start:
            parts.append(f"¶{para_start}–{para_end}")
        else:
            parts.append(f"¶{para_start}")
    return " ".join(parts)


def long_label(page, para_start, para_end, fallback):
    """Full location: 'Page 3, Paragraph 2', 'Page 3, Paragraphs 2–4', 'Paragraph 5'."""
    if page is None and para_start is None:
        return fallback
    parts = []
    if page is not None:
        parts.append(f"Page {page}")
    if para_start is not None:
        if para_end is not None and para_end != para_start:
            parts.append(f"Paragraphs {para_start}–{para_end}")
        else:
            parts.append(f"Paragraph {para_start}")
    return ", ".join(parts)
