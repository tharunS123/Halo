"""What every language-model answer must survive before Halo types it.

Shared by cleanup (pipeline.py) and Command Mode (transforms.py): the hard
wall-clock bound on a request to the model on this Mac, and the checks that
catch a model adding a preamble, repeating itself, or answering the text
instead of cleaning it.

Before 0.4 this module was also the OpenRouter client. Halo no longer sends
text anywhere: every model it talks to runs on this Mac (local_llm.py), and
netguard.py refuses any connection that would leave it.
"""
import concurrent.futures
import difflib
import re

import requests


class _HardTimeout(Exception):
    pass


def _post_bounded(headers, body, budget: float, url: str,
                  read_timeout: float | None = None):
    """POST with a HARD wall-clock bound.

    requests' `timeout` is a between-bytes read timeout: a server that trickles
    bytes can keep a request alive far past it (measured: a 45s call under a
    nominal 10s timeout). Dictation cannot tolerate that, so the request runs
    on a worker thread we simply abandon when the budget expires.
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(
            requests.post, url,
            headers=headers, json=body,
            timeout=(3, min(read_timeout or budget, budget)),
        )
        try:
            return fut.result(timeout=budget)
        except concurrent.futures.TimeoutError as e:
            raise _HardTimeout(f"exceeded {budget:.1f}s wall clock") from e
    finally:
        # Never block on the abandoned thread; requests' own timeout reaps it.
        ex.shutdown(wait=False, cancel_futures=True)


# --- preamble the model may prepend despite instructions ---
_PREAMBLE = re.compile(
    r"^\s*(?:"
    r"here(?:'s| is)\s+(?:the\s+|your\s+)?"
    r"(?:cleaned(?:[-\s]?up)?\s+|corrected\s+|revised\s+|final\s+)*"
    r"(?:transcript|text|version)\s*:?\s*"
    r"|(?:cleaned(?:[-\s]?up)?\s+)?(?:transcript|output|result)\s*:\s*"
    r")",
    re.IGNORECASE,
)


def _strip_wrappers(text: str) -> str:
    text = text.strip()
    for _ in range(3):
        stripped = _PREAMBLE.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    # fenced code block
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    # fully wrapped in quotes
    if len(text) >= 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        inner = text[1:-1]
        if text[0] not in inner and text[-1] not in inner:
            text = inner.strip()
    return text


def _norm(s: str) -> str:
    """Normalize for similarity comparison: lowercase, strip punct/space."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def deduplicate(text: str) -> str:
    """Collapse a response that repeats its own output.

    Handles: 'A A', 'A\n\nA', 'A. A.', and near-identical repeats where the
    second copy differs only in punctuation.
    """
    text = text.strip()
    if not text:
        return text

    # 1. Split on blank lines: if all blocks are near-identical, keep the first.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) > 1:
        first = _norm(blocks[0])
        if first and all(
            difflib.SequenceMatcher(None, first, _norm(b)).ratio() > 0.90
            for b in blocks[1:]
        ):
            return blocks[0]

    # 2. Identical consecutive lines.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        deduped = [lines[0]]
        for ln in lines[1:]:
            if _norm(ln) != _norm(deduped[-1]):
                deduped.append(ln)
        if len(deduped) == 1:
            return deduped[0]
        text = " ".join(deduped) if len(deduped) < len(lines) else text

    # 3. The whole text is one unit repeated N times (token-level, so that
    #    trailing punctuation on the better-punctuated copy survives).
    tokens = text.split()
    n = len(tokens)
    if n >= 4:
        for parts in (2, 3):
            if n % parts:
                continue
            unit = n // parts
            chunks = [" ".join(tokens[i * unit:(i + 1) * unit]) for i in range(parts)]
            first = _norm(chunks[0])
            if first and all(_norm(c) == first for c in chunks[1:]):
                # keep the longest rendering (most punctuation retained)
                return max(chunks, key=len).strip()

    # 4. Near-identical halves (second copy differs only slightly).
    if n >= 6 and n % 2 == 0:
        mid = n // 2
        a, b = " ".join(tokens[:mid]), " ".join(tokens[mid:])
        if difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio() > 0.95:
            return max(a, b, key=len).strip()

    return text


def _looks_wrong(raw: str, cleaned: str, min_similarity: float = 0.55) -> str:
    """Return a reason string if the cleaned text should be rejected.

    `min_similarity` is lower for Polished mode, which is allowed to reword;
    the invention check in pipeline.py is what keeps a rewrite honest.
    """
    if not cleaned:
        return "model returned empty text"
    rw, cw = len(raw.split()), len(cleaned.split())
    if cw > rw * 2 + 15:
        return f"model added content ({rw}w -> {cw}w), likely commentary"
    if cw < rw * 0.4 and rw > 8:
        return f"model dropped content ({rw}w -> {cw}w)"
    # Guard against the model answering a question instead of transcribing it.
    if difflib.SequenceMatcher(None, _norm(raw), _norm(cleaned)).ratio() < min_similarity:
        return "output diverges too far from the transcript"
    return ""
