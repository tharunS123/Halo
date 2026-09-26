"""Context Awareness: what app you are dictating into, and what is around the
cursor -- read once at key-down, held in memory for one dictation, then gone.

What it is for: "Jake" spelled the way the thread spells it, no capital when
you dictate into the middle of a sentence, no full stop on a Slack reply, an
email greeting on its own line, developer words cased right in an editor.

What it will never do, each covered by tests/test_context.py:

  - Read a password or other secure field. Before ANY text attribute is
    requested, three checks run: macOS Secure Event Input (on whenever a
    password field has focus, in any app), the AXSecureTextField role, and
    the field's own label ("Password", "One-time code", "API key"...). Any
    of them and Halo keeps only the app's category.
  - Keep more than it needs. At most 300 characters before the cursor, 100
    after and 500 selected -- never the whole document -- and the window
    title only long enough to classify the app.
  - Outlive the dictation. The Context lives on the engine for one
    record-transcribe-insert cycle and is cleared in `finally`.
  - Reach a log or a file. repr() is redacted, and the engine logs only the
    category. Nothing here is written anywhere.
  - Leave the machine. pipeline.py gives the local model names and the app
    category, never the text itself, and gives OpenRouter nothing at all.

It asks apps nothing they do not already publish to assistive technology,
and it never flips AXManualAccessibility / AXEnhancedUserInterface on
Chromium and Electron apps to make them publish more: that changes how
those apps behave for as long as they run. They get category-only context.
"""
import ctypes
import os
import re
import threading
import time
from dataclasses import dataclass

from backtrack import is_common

BEFORE_CHARS = 300
AFTER_CHARS = 100
SELECTED_CHARS = 500
MAX_TERMS = 30
# Whole AXValue is read only when AXStringForRange is unsupported AND the
# field is this small -- a search box, a chat input -- never a document.
SMALL_FIELD = 5000

CATEGORIES = ("chat", "email", "document", "terminal", "ide", "browser", "unknown")

_BUNDLES = {
    "chat": (
        "com.tinyspeck.slackmacgap", "com.apple.MobileSMS", "com.hnc.Discord",
        "com.microsoft.teams", "com.microsoft.teams2", "net.whatsapp.WhatsApp",
        "desktop.WhatsApp", "ru.keepcoder.Telegram", "org.telegram.desktop",
        "com.facebook.archon", "org.whispersystems.signal-desktop",
        "us.zoom.xos", "com.skype.skype", "com.openai.chat",
        "com.anthropic.claudefordesktop",
    ),
    "email": (
        "com.apple.mail", "com.microsoft.Outlook", "com.readdle.smartemail-Mac",
        "com.superhuman.electron", "it.bloop.airmail2", "com.freron.MailMate",
        "com.mimestream.Mimestream", "com.canarymail.mac", "com.postbox-inc.postbox",
    ),
    "document": (
        "com.apple.iWork.Pages", "com.microsoft.Word", "com.apple.Notes",
        "md.obsidian", "notion.id", "net.shinyfrog.bear", "com.apple.TextEdit",
        "com.ulyssesapp.mac", "pro.writer.mac", "com.literatureandlatte.scrivener3",
        "com.apple.iWork.Keynote", "com.microsoft.Powerpoint",
        "com.lukilabs.lukiapp", "com.agiletortoise.Drafts-OSX",
        "com.apple.reminders", "com.culturedcode.ThingsMac",
    ),
    "terminal": (
        "com.apple.Terminal", "com.googlecode.iterm2", "com.mitchellh.ghostty",
        "dev.warp.Warp-Stable", "net.kovidgoyal.kitty", "io.alacritty",
        "co.zeit.hyper", "com.github.wez.wezterm",
    ),
    "ide": (
        "com.microsoft.VSCode", "com.microsoft.VSCodeInsiders",
        "com.todesktop.230313mzl4w4u92", "com.apple.dt.Xcode", "dev.zed.Zed",
        "com.sublimetext.4", "com.exafunction.windsurf", "com.panic.Nova",
        "com.google.android.studio", "com.jetbrains.",
    ),
    "browser": (
        "com.apple.Safari", "com.google.Chrome", "com.google.Chrome.beta",
        "org.mozilla.firefox", "company.thebrowser.Browser", "com.brave.Browser",
        "com.microsoft.edgemac", "com.vivaldi.Vivaldi", "com.operasoftware.Opera",
        "app.zen-browser.zen", "com.kagi.kagimacOS",
    ),
}

_HOSTS = (
    ("mail.google.com", "email"), ("outlook.live.com", "email"),
    ("outlook.office.com", "email"), ("outlook.office365.com", "email"),
    ("mail.yahoo.com", "email"), ("app.fastmail.com", "email"),
    ("mail.proton.me", "email"), ("app.hey.com", "email"),
    ("slack.com", "chat"), ("discord.com", "chat"), ("web.whatsapp.com", "chat"),
    ("web.telegram.org", "chat"), ("teams.microsoft.com", "chat"),
    ("messenger.com", "chat"), ("chat.google.com", "chat"),
    ("chatgpt.com", "chat"), ("chat.openai.com", "chat"), ("claude.ai", "chat"),
    ("gemini.google.com", "chat"),
    ("docs.google.com", "document"), ("notion.so", "document"),
    ("notion.site", "document"), ("coda.io", "document"), ("quip.com", "document"),
    ("atlassian.net", "document"), ("medium.com", "document"),
    ("substack.com", "document"), ("paper.dropbox.com", "document"),
)

# Labels that mark a credential input even when the app did not use a secure
# text field -- web forms and custom controls often do not.
_CREDENTIAL = re.compile(
    r"pass(?:word|code|phrase)|\bpin\b|one[- ]?time|\botp\b|\b2fa\b|"
    r"two[- ]factor|verification\s+code|security\s+code|\bsecret\b|"
    r"api[\s_-]?key|\btoken\b|\bcvv\b|\bcvc\b|card\s+number|credit\s+card|"
    r"\bssn\b|social\s+security|private\s+key|seed\s+phrase|recovery\s+phrase",
    re.IGNORECASE)

_CODE_TITLE = re.compile(
    r"\.(?:py|js|ts|tsx|jsx|swift|go|rs|java|kt|c|cc|cpp|h|hpp|m|rb|php|sh|"
    r"zsh|sql|json|ya?ml|toml|lua|cs|scala)\b")


@dataclass(repr=False, eq=False)
class Context:
    category: str = "unknown"
    app_name: str = ""
    bundle_id: str = ""
    host: str = ""               # hostname only, never a path or query
    secure: bool = False
    before: str | None = None    # None = unknown, "" = at the very start
    after: str | None = None
    selected: str = ""
    terms: tuple = ()
    # The insertion target -- references and numbers, never text. Captured
    # even with Context Awareness off, because safe insertion needs to know
    # where the text was meant to go (insertion.py).
    pid: int | None = None
    element: object = None          # AXUIElement of the focused field
    window: object = None           # AXUIElement of its window
    selection: tuple | None = None  # (location, length) at key-down
    text_read: bool = False         # was Context Awareness on for this capture

    # Redacted on purpose: an accidental print(ctx) or log(f"{ctx}") must not
    # be able to write what was on screen.
    def __repr__(self) -> str:
        return (f"<Context {self.category} before={len(self.before or '')}ch "
                f"after={len(self.after or '')}ch selected={len(self.selected)}ch "
                f"terms={len(self.terms)} secure={self.secure}>")

    __str__ = __repr__

    def summary(self) -> str:
        """What the engine log may say: the category and flags, no text."""
        bits = [self.category]
        if self.secure:
            bits.append("secure field -- nothing read")
        elif self.before is not None or self.after is not None:
            bits.append("cursor text")
        if self.terms:
            bits.append(f"{len(self.terms)} terms")
        return ", ".join(bits)

    def clear(self) -> None:
        self.before = None
        self.after = None
        self.selected = ""
        self.terms = ()
        self.host = ""
        self.element = None
        self.window = None


def classify(bundle_id: str, overrides: dict | None = None) -> str:
    if overrides and bundle_id in overrides and overrides[bundle_id] in CATEGORIES:
        return overrides[bundle_id]
    for category, bundles in _BUNDLES.items():
        for b in bundles:
            if bundle_id == b or (b.endswith(".") and bundle_id.startswith(b)):
                return category
    return "unknown"


def classify_host(host: str) -> str | None:
    host = host.lower()
    for suffix, category in _HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return category
    return None


def extract_terms(*texts: str) -> tuple:
    """Names and identifiers worth spelling the way the screen spells them.

    Proper nouns that are not ordinary words (the system word list keeps
    names capitalised, so "Jake" is absent from its lower-case entries),
    CamelCase, snake_case and dotted names. Nearest the cursor first. No
    emails, URLs or numbers: those are exactly the things that should not
    be copied around.
    """
    seen: dict[str, None] = {}
    for text in texts:
        if not text:
            continue
        for m in re.finditer(r"[A-Za-z][\w'.-]*[A-Za-z0-9_]|[A-Z]", text):
            word = m.group(0).rstrip(".'")
            if len(word) < 2 or len(word) > 40 or "@" in word or "://" in word:
                continue
            if re.search(r"\.(?:com|org|net|io|dev|ai|app)$", word, re.I):
                continue
            prev = text[:m.start()].rstrip()
            initial = not prev or prev[-1] in ".!?\n:\"'"
            keep = (re.search(r"[a-z][A-Z]", word) is not None          # CamelCase
                    or ("_" in word and not word.startswith("_"))       # snake_case
                    or re.fullmatch(r"[A-Za-z]\w*(?:\.\w+)+", word) is not None)
            if not keep and word[0].isupper() and word != "I":
                # Mid-sentence, a capital marks a name even when the word is
                # also English ("Jake", "Will"). At a sentence start it only
                # counts if the word is not ordinary English.
                keep = not initial or not is_common(word)
                if word.isupper() and len(word) > 6:
                    keep = False                                        # SHOUTING
            if keep:
                seen.setdefault(word, None)
            if len(seen) >= MAX_TERMS:
                return tuple(seen)
    return tuple(seen)


# --- the Accessibility side ----------------------------------------------------

class _AX:
    """Thin wrapper over PyObjC's ApplicationServices. Swapped for a fake in
    tests, which is how they prove what is and is not read."""

    def __init__(self):
        import ApplicationServices as AS
        import Quartz
        from AppKit import NSRunningApplication
        self.AS, self.Quartz, self.NSRunningApplication = AS, Quartz, NSRunningApplication
        self.system = AS.AXUIElementCreateSystemWide()
        # Default is ~6s. An app that has stopped responding would otherwise
        # hold the capture thread that long; setting it on the system-wide
        # element sets it for every element this process talks to.
        AS.AXUIElementSetMessagingTimeout(self.system, 0.2)
        carbon = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/Carbon.framework/Carbon")
        self._secure = carbon.IsSecureEventInputEnabled
        self._secure.restype = ctypes.c_bool

    def secure_input(self) -> bool:
        return bool(self._secure())

    def focused_app(self):
        """(app element, pid) for the app with keyboard focus, or None.

        The system-wide AXFocusedApplication is the direct answer but fails
        with kAXErrorCannotComplete in some sessions (measured). The fallback
        is the owner of the frontmost normal window, which Quartz reports
        without Screen Recording. NSWorkspace.frontmostApplication is NOT
        used: it is refreshed by notifications on a main run loop, and the
        engine's main thread is pynput's key tap, not a run loop.
        """
        AS = self.AS
        err, app = AS.AXUIElementCopyAttributeValue(self.system, "AXFocusedApplication", None)
        if not err and app is not None:
            err, pid = AS.AXUIElementGetPid(app, None)
            if not err:
                return app, pid
        Q = self.Quartz
        windows = Q.CGWindowListCopyWindowInfo(
            Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements,
            Q.kCGNullWindowID) or []
        ours = {os.getpid(), os.getppid()}
        for w in windows:
            if w.get("kCGWindowLayer", 1) != 0:
                continue
            pid = w.get("kCGWindowOwnerPID")
            if not pid or pid in ours or w.get("kCGWindowOwnerName") == "Halo":
                continue
            return AS.AXUIElementCreateApplication(pid), pid
        return None

    def app_info(self, pid: int) -> tuple[str, str]:
        app = self.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is None:
            return "", ""
        return str(app.bundleIdentifier() or ""), str(app.localizedName() or "")

    def attr(self, elem, name: str):
        err, value = self.AS.AXUIElementCopyAttributeValue(elem, name, None)
        return None if err or value is None else value

    def selected_range(self, elem) -> tuple[int, int] | None:
        value = self.attr(elem, "AXSelectedTextRange")
        if value is None:
            return None
        ok, rng = self.AS.AXValueGetValue(value, self.AS.kAXValueCFRangeType, None)
        if not ok:
            return None
        return int(rng.location), int(rng.length)

    def string_for_range(self, elem, location: int, length: int) -> str | None:
        if length <= 0:
            return ""
        rng = self.AS.AXValueCreate(self.AS.kAXValueCFRangeType, (location, length))
        err, value = self.AS.AXUIElementCopyParameterizedAttributeValue(
            elem, "AXStringForRange", rng, None)
        return None if err or value is None else str(value)

    def settable(self, elem, name: str) -> bool:
        err, ok = self.AS.AXUIElementIsAttributeSettable(elem, name, None)
        return not err and bool(ok)

    def set_attr(self, elem, name: str, value) -> bool:
        return self.AS.AXUIElementSetAttributeValue(elem, name, value) == 0

    def set_selected_range(self, elem, location: int, length: int) -> bool:
        rng = self.AS.AXValueCreate(self.AS.kAXValueCFRangeType, (location, length))
        return self.set_attr(elem, "AXSelectedTextRange", rng)

    def focused_element(self, app):
        return self.attr(app, "AXFocusedUIElement")

    @staticmethod
    def same(a, b) -> bool:
        """CFEqual, through PyObjC: two proxies for one element compare equal."""
        if a is None or b is None:
            return False
        try:
            return bool(a == b)
        except Exception:
            return False

    def url_host(self, value) -> str:
        try:
            host = value.host()
            return str(host) if host else ""
        except AttributeError:
            return ""


_ax: _AX | None = None
_ax_lock = threading.Lock()


def _backend():
    """The AX wrapper, built once. Importing PyObjC costs ~0.6s, so the engine
    calls warm_up() at start and the first dictation does not pay it."""
    global _ax
    with _ax_lock:
        if _ax is None:
            _ax = _AX()
        return _ax


def warm_up() -> None:
    try:
        _backend()
    except Exception as e:                      # never fatal: context is optional
        print(f"[context] unavailable: {type(e).__name__}")


def _is_secure(ax, elem) -> bool:
    role = ax.attr(elem, "AXRole")
    subrole = ax.attr(elem, "AXSubrole")
    if "AXSecureTextField" in (str(role or ""), str(subrole or "")):
        return True
    for name in ("AXPlaceholderValue", "AXTitle", "AXDescription",
                 "AXIdentifier", "AXRoleDescription", "AXHelp"):
        label = ax.attr(elem, name)
        if label is not None and _CREDENTIAL.search(str(label)):
            return True
    return False


def _web_host(ax, elem) -> str:
    """Hostname of the page holding the focused element, if the browser
    publishes one (Safari does; Chromium only when its tree is already on)."""
    node = elem
    for _ in range(30):
        if node is None:
            break
        if str(ax.attr(node, "AXRole") or "") == "AXWebArea":
            url = ax.attr(node, "AXURL")
            return ax.url_host(url) if url is not None else ""
        node = ax.attr(node, "AXParent")
    return ""


def capture(ax, overrides: dict | None = None, budget: float = 0.25,
            read_text: bool = True) -> Context:
    """Read context through `ax`. Stops early, keeping what it has, when the
    budget runs out.

    With read_text=False (Context Awareness off) only the insertion target is
    recorded -- app, window, focused element, selection range -- and no text,
    title or web address is read at all.
    """
    deadline = time.monotonic() + budget
    ctx = Context(text_read=read_text)
    found = ax.focused_app()
    if not found:
        return ctx
    app, pid = found
    ctx.pid = pid
    ctx.bundle_id, ctx.app_name = ax.app_info(pid)
    ctx.category = classify(ctx.bundle_id, overrides)
    ctx.window = ax.attr(app, "AXFocusedWindow")

    # 1. Secure Event Input is global: if any password field has focus, the
    #    safe answer is to read nothing from anywhere.
    if ax.secure_input():
        ctx.secure = True
        return ctx

    elem = ax.attr(app, "AXFocusedUIElement")
    if elem is None:
        return ctx                              # Chromium/Electron: category only
    ctx.element = elem
    # 2 and 3. The field itself, before a single character of it is read.
    if _is_secure(ax, elem):
        ctx.secure = True
        return ctx
    ctx.selection = ax.selected_range(elem)
    if not read_text or time.monotonic() > deadline:
        return ctx

    if ctx.category == "browser":
        host = _web_host(ax, elem)
        if host:
            ctx.host = host.lower()
            ctx.category = classify_host(ctx.host) or "browser"
    elif ctx.category == "unknown":
        window = ax.attr(app, "AXFocusedWindow")
        title = ax.attr(window, "AXTitle") if window is not None else None
        if title and _CODE_TITLE.search(str(title)):
            ctx.category = "ide"
        del title                               # used to classify, not kept
    if time.monotonic() > deadline:
        return ctx

    rng = ctx.selection
    if rng is not None:
        loc, length = rng
        total = ax.attr(elem, "AXNumberOfCharacters")
        total = int(total) if isinstance(total, int) else None
        start = max(0, loc - BEFORE_CHARS)
        before = ax.string_for_range(elem, start, loc - start)
        end = loc + length
        after_len = AFTER_CHARS if total is None else max(0, min(AFTER_CHARS, total - end))
        after = ax.string_for_range(elem, end, after_len)
        if (before is None or after is None) and total is not None and total <= SMALL_FIELD:
            value = ax.attr(elem, "AXValue")
            if isinstance(value, str):
                before = value[start:loc] if before is None else before
                after = value[end:end + AFTER_CHARS] if after is None else after
            del value
        ctx.before = before
        ctx.after = after
        if length > 0:
            selected = ax.attr(elem, "AXSelectedText")
            ctx.selected = str(selected)[:SELECTED_CHARS] if selected is not None else ""
    ctx.terms = extract_terms(ctx.before, ctx.after, ctx.selected)
    return ctx


class Pending:
    """A capture running on its own thread. `get()` waits a bounded time and
    otherwise gives up -- context is never worth delaying a dictation."""

    def __init__(self, overrides: dict | None, budget: float, read_text: bool = True):
        self.read_text = read_text
        self._done = threading.Event()
        self._ctx: Context | None = None
        self._abandoned = False
        self._lock = threading.Lock()
        threading.Thread(target=self._run, args=(overrides, budget), daemon=True,
                         name="context-capture").start()

    def _run(self, overrides, budget):
        ctx = None
        try:
            ctx = capture(_backend(), overrides, budget, self.read_text)
        except Exception:
            # Deliberately silent about the details: an exception from an AX
            # call can carry the value it was handling.
            ctx = None
        with self._lock:
            if self._abandoned and ctx is not None:
                ctx.clear()
                ctx = None
            self._ctx = ctx
        self._done.set()

    def get(self, timeout: float) -> Context | None:
        self._done.wait(timeout)
        with self._lock:
            if not self._done.is_set():
                self._abandoned = True
                return None
            return self._ctx

    def discard(self) -> None:
        with self._lock:
            self._abandoned = True
            if self._ctx is not None:
                self._ctx.clear()
                self._ctx = None


def capture_async(overrides: dict | None = None, budget: float = 0.25,
                  read_text: bool = True) -> Pending:
    return Pending(overrides, budget, read_text)
