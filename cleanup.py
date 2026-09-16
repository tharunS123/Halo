"""LLM cleanup of a raw transcript via OpenRouter. Never fatal: always
returns usable text, falling back to the raw transcript on any failure."""
import concurrent.futures
import difflib
import os
import re
import time

import requests

import config


class _HardTimeout(Exception):
    pass


def _post_bounded(headers, body, budget: float):
    """POST with a HARD wall-clock bound.

    requests' `timeout` is a between-bytes read timeout: a server that trickles
    bytes can keep a request alive far past it (measured: a 45s call under a
    nominal 10s timeout). Dictation cannot tolerate that, so the request runs
    on a worker thread we simply abandon when the budget expires.
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(
            requests.post, config.OPENROUTER_URL,
            headers=headers, json=body,
            timeout=(3, min(config.OPENROUTER_TIMEOUT, budget)),
        )
        try:
            return fut.result(timeout=budget)
        except concurrent.futures.TimeoutError:
            raise _HardTimeout(f"exceeded {budget:.1f}s wall clock")
    finally:
        # Never block on the abandoned thread; requests' own timeout reaps it.
        ex.shutdown(wait=False, cancel_futures=True)


class CleanupResult:
    def __init__(self, text: str, source: str, detail: str = ""):
        self.text = text          # text to inject
        self.source = source      # "llm" | "raw"
        self.detail = detail      # why, for console output

    def __repr__(self):
        return f"<CleanupResult {self.source}: {self.detail}>"


def _system_prompt(vocabulary: str = "", language: str = "en") -> str:
    """Cleanup prompt, adapted to the spoken language and personal vocabulary."""
    parts = [config.SYSTEM_PROMPT]
    if language and language != "en":
        name = config.LANGUAGE_NAMES.get(language, language)
        parts.append(
            f"The transcript is in {name}. Reply in {name}, using {name} "
            f"punctuation and capitalisation conventions. Do NOT translate.")
    if vocabulary:
        parts.append(vocabulary)
    return "\n".join(parts)


AI_COMMAND_PROMPT = (
    "You edit text on request. You are given TEXT and an INSTRUCTION.\n"
    "Apply the instruction to the text and output ONLY the resulting text.\n"
    "No preamble, no explanation, no quotes, no markdown fences.\n"
    "If the instruction asks a question rather than an edit, still answer with "
    "text suitable for pasting directly into a document."
)


def ai_command(instruction: str, context: str, language: str = "en"):
    """Feature 4: 'hey halo, <instruction>' applied to recent dictation.

    Returns a CleanupResult whose .source is 'llm' on success, or 'raw' with a
    reason on failure -- callers must not inject anything on failure.
    """
    api_key = config.get_api_key()
    if not api_key:
        return CleanupResult("", "raw", "no API key for AI command")
    if not instruction.strip():
        return CleanupResult("", "raw", "empty instruction")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/halo",
        "X-Title": "Halo",
    }
    user = f"TEXT:\n{context}\n\nINSTRUCTION:\n{instruction}"
    deadline = time.time() + config.OPENROUTER_AI_BUDGET

    last_err = "no models attempted"
    for model in config.OPENROUTER_MODELS:
        remaining = deadline - time.time()
        if remaining <= 0.5:
            break
        try:
            resp = _post_bounded(
                headers,
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": AI_COMMAND_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1200,
                    "reasoning": {"enabled": False},
                },
                budget=remaining,
            )
        except _HardTimeout as e:
            last_err = f"{model}: {e}"
            continue
        except requests.RequestException as e:
            last_err = f"{model}: {type(e).__name__}"
            continue

        if resp.status_code != 200:
            last_err = f"{model}: HTTP {resp.status_code}"
            continue
        try:
            choice = resp.json()["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            last_err = f"{model}: malformed response"
            continue
        if not content:
            last_err = f"{model}: empty response"
            continue

        text = deduplicate(_strip_wrappers(content))
        if not text:
            last_err = f"{model}: empty after cleanup"
            continue
        return CleanupResult(text, "llm", model)

    return CleanupResult("", "raw", last_err)


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


def _looks_wrong(raw: str, cleaned: str) -> str:
    """Return a reason string if the cleaned text should be rejected."""
    if not cleaned:
        return "model returned empty text"
    rw, cw = len(raw.split()), len(cleaned.split())
    if cw > rw * 2 + 15:
        return f"model added content ({rw}w -> {cw}w), likely commentary"
    if cw < rw * 0.4 and rw > 8:
        return f"model dropped content ({rw}w -> {cw}w)"
    # Guard against the model answering a question instead of transcribing it.
    if difflib.SequenceMatcher(None, _norm(raw), _norm(cleaned)).ratio() < 0.55:
        return "output diverges too far from the transcript"
    return ""


def clean(raw: str, verbose: bool = True, vocabulary: str = "",
          language: str = "en") -> CleanupResult:
    api_key = config.get_api_key()
    if not api_key:
        return CleanupResult(
            raw, "raw",
            "no API key (set OPENROUTER_API_KEY or add it to the Keychain)")
    if not raw.strip():
        return CleanupResult(raw, "raw", "empty transcript")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/halo",
        "X-Title": "Halo",
    }
    last_err = "no models attempted"
    deadline = time.time() + config.OPENROUTER_TOTAL_BUDGET

    for model in config.OPENROUTER_MODELS:
        for attempt in range(config.OPENROUTER_MAX_RETRIES + 1):
            remaining = deadline - time.time()
            if remaining <= 0.5:
                return CleanupResult(
                    raw, "raw",
                    f"total budget {config.OPENROUTER_TOTAL_BUDGET}s exhausted "
                    f"(last: {last_err})")
            try:
                resp = _post_bounded(
                    headers,
                    {
                        "model": model,
                        "messages": [
                            {"role": "system",
                             "content": _system_prompt(vocabulary, language)},
                            {"role": "user", "content": raw},
                        ],
                        "temperature": 0,
                        "max_tokens": min(2000, len(raw.split()) * 4 + 100),
                        # CRITICAL: these are reasoning models. Left on, the
                        # chain-of-thought takes 50-80s and eats max_tokens,
                        # silently truncating the transcript. Off: ~0.8s.
                        "reasoning": {"enabled": False},
                    },
                    budget=remaining,
                )
            except _HardTimeout as e:
                last_err = f"{model}: {e}"
                break  # don't retry; the user is waiting
            except requests.Timeout:
                last_err = f"{model}: timeout after {config.OPENROUTER_TIMEOUT}s"
                break  # don't retry a timeout; latency matters more
            except requests.RequestException as e:
                last_err = f"{model}: network error ({type(e).__name__})"
                break

            if resp.status_code == 429:
                last_err = f"{model}: rate limited (429)"
                if attempt < config.OPENROUTER_MAX_RETRIES:
                    time.sleep(1.0)
                    continue
                break
            if resp.status_code == 401:
                return CleanupResult(raw, "raw", "OPENROUTER_API_KEY rejected (401)")
            if resp.status_code >= 500:
                last_err = f"{model}: server error ({resp.status_code})"
                if attempt < config.OPENROUTER_MAX_RETRIES:
                    time.sleep(0.5)
                    continue
                break
            if resp.status_code != 200:
                last_err = f"{model}: HTTP {resp.status_code}"
                break

            try:
                body = resp.json()
                choice = body["choices"][0]
                content = choice["message"]["content"]
                finish = choice.get("finish_reason")
            except (ValueError, KeyError, IndexError, TypeError):
                last_err = f"{model}: malformed response"
                break

            if content is None:
                last_err = f"{model}: null content"
                break

            # A 'length' finish means the model was cut off mid-sentence.
            # Injecting that would silently drop the end of your dictation.
            if finish == "length":
                last_err = f"{model}: response truncated (finish_reason=length)"
                break

            text = deduplicate(_strip_wrappers(content))
            reason = _looks_wrong(raw, text)
            if reason:
                last_err = f"{model}: {reason}"
                break  # try the next model

            return CleanupResult(text, "llm", model)

    return CleanupResult(raw, "raw", last_err)
