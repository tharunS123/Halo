"""What the engine log may say about the things you dictate.

engine.log is a diagnostic file: people paste it into bug reports, and it
lives in ~/Library/Logs where any app running as you can read it. So by
default it records the SHAPE of text -- how long, how many words -- never
the text: not transcripts, not what the model returned, not selected text,
clipboard contents, dictionary words or spoken commands.

`debug.log_content` in settings.json (Settings > Advanced, labelled as a
debugging aid) turns the real text back on for someone chasing a bug. It is
off by default and says so every time it is on.
"""
import config


def content(text, what: str = "text") -> str:
    """The text itself only in debug mode; otherwise a redacted summary."""
    if text is None:
        return f"<no {what}>"
    text = str(text)
    if config.DEBUG_LOG_CONTENT:
        return repr(text[:300]) + ("..." if len(text) > 300 else "")
    words = len(text.split())
    return f"<{what}: {len(text)} chars, {words} word{'s' if words != 1 else ''}>"


def count(items, what: str) -> str:
    """For lists of words (dictionary fixes, terms): how many, never which."""
    n = len(items)
    if config.DEBUG_LOG_CONTENT:
        return f"{n} {what}: {list(items)[:10]!r}"
    return f"{n} {what}"


def banner() -> str:
    return ("DEBUG CONTENT LOGGING IS ON -- dictated text is being written to this "
            "log. Turn it off in Settings > Advanced." if config.DEBUG_LOG_CONTENT else "")
