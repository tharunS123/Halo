"""Developer Mode: dictating into code editors, terminals and AI prompts.

On automatically in editors and terminals (developer_mode = "auto"), or
forced on or off in Settings > Intelligence. What it adds, all local rules:

  vocabulary      "super base" -> Supabase, "swift UI" -> SwiftUI,
                  "post grass" -> Postgres, "async await" -> async/await
  case cues       "camel case user id" -> userId, and pascal, snake, kebab,
                  constant ("screaming snake") case
  dot notation    "config dot json" -> config.json, "self dot view" -> self.view
  paths           "tilde slash projects slash halo" -> ~/projects/halo
  flags           "dash dash verbose" -> --verbose, "dash v" -> -v
  commands        "Git status." in a terminal -> git status
  identifiers     "user view controller" -> UserViewController, when that
                  identifier is on screen near the cursor

The last one uses the names Context Awareness already extracted from the few
hundred characters around the cursor -- nothing is read from source files,
and nothing is kept after the dictation.

It runs before spoken punctuation, because "dash dash verbose" must not
become " -  - verbose" first.
"""
import re

# spoken (lower case, space separated) -> written. Longest first at use.
VOCAB = {
    "swift ui": "SwiftUI", "swift you i": "SwiftUI", "swift data": "SwiftData",
    "type script": "TypeScript", "java script": "JavaScript",
    "post grass": "Postgres", "post gres": "Postgres", "postgres": "Postgres",
    "post gres q l": "PostgreSQL", "postgres q l": "PostgreSQL",
    "postgre sql": "PostgreSQL", "postgres sql": "PostgreSQL",
    "super base": "Supabase", "supa base": "Supabase", "soup a base": "Supabase",
    "cloud flare": "Cloudflare", "async await": "async/await",
    "a sync await": "async/await", "ui view controller": "UIViewController",
    "u i view controller": "UIViewController", "you i view controller": "UIViewController",
    "ui kit": "UIKit", "app kit": "AppKit", "core data": "Core Data",
    "graph q l": "GraphQL", "graph ql": "GraphQL", "n p m": "npm", "p n p m": "pnpm",
    "git hub": "GitHub", "git lab": "GitLab", "a p i": "API", "j son": "JSON",
    "x code": "Xcode", "next js": "Next.js", "next dot js": "Next.js",
    "node js": "Node.js", "node dot js": "Node.js", "vue js": "Vue.js",
    "react native": "React Native", "tailwind css": "Tailwind CSS",
    "cube control": "kubectl", "cube c t l": "kubectl", "k8s": "k8s",
    "pie torch": "PyTorch", "num pie": "NumPy", "sci pie": "SciPy",
    "fast api": "FastAPI", "open ai": "OpenAI", "lang chain": "LangChain",
    "home brew": "Homebrew", "dot env": ".env", "read me": "README",
    "web socket": "WebSocket", "o auth": "OAuth", "j w t": "JWT",
    "s q l": "SQL", "sequel": "SQL", "no sequel": "NoSQL", "my sequel": "MySQL",
    "sequel lite": "SQLite", "s q lite": "SQLite", "redis": "Redis",
    "docker file": "Dockerfile", "make file": "Makefile", "yaml": "YAML",
    "tom l": "TOML", "c i": "CI", "c d": "CD", "p r": "PR", "l l m": "LLM",
    "claude code": "Claude Code", "v s code": "VS Code", "vs code": "VS Code",
}
_VOCAB_RE = [(re.compile(r"(?<![\w./-])" + r"[\s-]+".join(map(re.escape, k.split()))
                         + r"(?![\w/-])", re.IGNORECASE), v)
             for k, v in sorted(VOCAB.items(), key=lambda kv: -len(kv[0]))]

# Words that end a case-cued identifier: "camel case user id to five" is
# userId, then " to five".
_STOP = {"to", "is", "are", "the", "a", "an", "and", "or", "with", "in", "on",
         "for", "from", "equals", "equal", "as", "at", "of", "into", "then",
         "if", "which", "that", "please", "so", "but",
         # spoken symbols end an identifier too
         "dash", "slash", "dot", "underscore", "comma", "period", "colon"}

_CASES = {
    "camel case": "camel", "camelcase": "camel", "lower camel case": "camel",
    "pascal case": "pascal", "upper camel case": "pascal", "title case": None,
    "snake case": "snake", "kebab case": "kebab", "dash case": "kebab",
    "constant case": "constant", "screaming snake case": "constant",
    "upper snake case": "constant", "all caps snake case": "constant",
}
_CASE_RE = re.compile(
    r"(?<![\w'])(" + "|".join(re.escape(k).replace(r"\ ", r"\s+")
                              for k in sorted((k for k, v in _CASES.items() if v),
                                              key=len, reverse=True))
    + r")[\s,:]+((?:[A-Za-z0-9']+[\s,]*){1,6})", re.IGNORECASE)


def join_case(words: list[str], style: str) -> str:
    words = [re.sub(r"[^\w]", "", w) for w in words if re.sub(r"[^\w]", "", w)]
    if not words:
        return ""
    low = [w.lower() for w in words]
    if style == "camel":
        return low[0] + "".join(w[:1].upper() + w[1:] for w in low[1:])
    if style == "pascal":
        return "".join(w[:1].upper() + w[1:] for w in low)
    if style == "snake":
        return "_".join(low)
    if style == "kebab":
        return "-".join(low)
    if style == "constant":
        return "_".join(w.upper() for w in low)
    return " ".join(words)


def _case_cues(text: str) -> str:
    def sub(m: re.Match) -> str:
        style = _CASES[" ".join(m.group(1).lower().split())]
        raw = m.group(2)
        words = re.findall(r"[A-Za-z0-9']+", raw)
        taken = []
        for w in words:
            if w.lower() in _STOP and taken:
                break
            taken.append(w)
        # Give back what was not part of the identifier, and the pause after it.
        consumed = 0
        for w in taken:
            consumed = raw.lower().find(w.lower(), consumed) + len(w)
        rest = raw[consumed:]
        return join_case(taken, style) + rest
    return _CASE_RE.sub(sub, text)


_IDENT = r"[A-Za-z_][\w]*"
_EXTS = ("swift", "py", "js", "ts", "tsx", "jsx", "json", "md", "yml", "yaml",
         "toml", "txt", "sh", "zsh", "rb", "go", "rs", "java", "kt", "c", "h",
         "cpp", "m", "mm", "html", "css", "scss", "sql", "env", "lock", "xml",
         "plist", "gguf", "bin", "csv", "log", "cfg", "ini", "vue", "svelte")


_RECEIVERS = {"self", "this", "super", "os", "sys", "np", "pd", "console",
              "window", "document", "math", "json", "app", "request", "response",
              "req", "res", "props", "state", "ctx", "config", "settings",
              "process", "module", "exports", "navigator", "event", "error",
              "result", "data", "model", "view", "user", "item", "node", "obj"}


def _code_like(word: str) -> bool:
    return bool(re.search(r"[a-z][A-Z]|_|\d", word))


def _dots(text: str) -> str:
    """"config dot json" -> config.json; "self dot view dot frame" ->
    self.view.frame. Needs a reason: a file extension, a receiver like
    `self`, a code-shaped word, or a chain of three -- "polka dot dress"
    stays a dress."""
    pattern = re.compile(r"(?<![\w.])(" + _IDENT + r")((?:\s+dot\s+" + _IDENT + r")+)(?![\w])",
                         re.IGNORECASE)

    def sub(m: re.Match) -> str:
        parts = [m.group(1)] + re.findall(r"dot\s+(" + _IDENT + ")", m.group(2),
                                          flags=re.IGNORECASE)
        reason = (parts[-1].lower() in _EXTS or parts[0].lower() in _RECEIVERS
                  or any(_code_like(p) for p in parts) or len(parts) >= 3)
        return ".".join(parts) if reason else m.group(0)
    return pattern.sub(sub, text)


def _paths(text: str) -> str:
    """"tilde slash projects slash halo" -> ~/projects/halo."""
    seg = r"[\w.-]+"
    pattern = re.compile(
        r"(?<![\w/])(?:(tilde|dot|dot dot)\s+)?slash\s+(" + seg + r"(?:\s+slash\s+" + seg + r")*)"
        r"(\s+slash)?(?![\w])", re.IGNORECASE)

    def sub(m: re.Match) -> str:
        lead = {"tilde": "~", "dot": ".", "dot dot": ".."}.get(
            (m.group(1) or "").lower(), "")
        body = "/".join(re.split(r"\s+slash\s+", m.group(2), flags=re.I))
        return f"{lead}/{body}" + ("/" if m.group(3) else "")
    return pattern.sub(sub, text)


def _flags(text: str) -> str:
    """"dash dash verbose" -> --verbose; "dash v" -> -v."""
    text = re.sub(r"(?<![\w-])(?:dash\s+dash|double\s+dash)\s+([a-z][\w-]*)",
                  lambda m: "--" + m.group(1).lower(), text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![\w-])dash\s+([a-zA-Z])(?![\w])",
                  lambda m: "-" + m.group(1), text, flags=re.IGNORECASE)
    # "--dry dash run" -> --dry-run: a flag keeps joining on spoken dashes.
    joined = re.compile(r"(?<![\w-])(--?[a-z][\w-]*)\s+dash\s+([a-z][\w]*)", re.IGNORECASE)
    while joined.search(text):
        text = joined.sub(lambda m: m.group(1) + "-" + m.group(2).lower(), text)
    return re.sub(r"(?<=\w)\s+underscore\s+(?=\w)", "_", text, flags=re.IGNORECASE)


_COMMANDS = {"git", "npm", "npx", "pnpm", "yarn", "ls", "cd", "brew", "python",
             "python3", "pip", "pip3", "docker", "kubectl", "make", "cargo",
             "swift", "xcodebuild", "curl", "grep", "cat", "echo", "mkdir", "rm",
             "mv", "cp", "ssh", "open", "code", "halo", "go", "node", "uv",
             "gh", "sudo", "chmod", "touch", "export", "source", "vim", "nano"}


def _terminal_command(text: str) -> str:
    """In a terminal, "Git status." is a command: lower case, no full stop."""
    m = re.match(r"\s*([A-Za-z][\w-]*)", text)
    if not m or m.group(1).lower() not in _COMMANDS:
        return text
    text = text[:m.start(1)] + m.group(1).lower() + text[m.end(1):]
    stripped = text.rstrip()
    if stripped.endswith(".") and not stripped.endswith(".."):
        text = stripped[:-1]
    return text


def split_identifier(ident: str) -> list[str]:
    """UserViewController -> [user, view, controller]; fetch_data -> [fetch, data]."""
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|\d+", ident)
    return [p.lower() for p in parts if p]


def snap_identifiers(text: str, identifiers) -> str:
    """Replace spoken word runs that spell an on-screen identifier with it."""
    for ident in sorted({i for i in identifiers if i}, key=len, reverse=True):
        base = ident.rsplit(".", 1)[-1]
        parts = split_identifier(base)
        if len(parts) < 2 or not re.search(r"[a-z][A-Z]|_|^[A-Z]{2}", base):
            continue
        pattern = re.compile(r"(?<![\w.])" + r"[\s_-]*".join(map(re.escape, parts))
                             + r"(?![\w])", re.IGNORECASE)
        text = pattern.sub(base, text)
    return text


def active(ctx) -> bool:
    import config
    if config.DEVELOPER_MODE == "on":
        return True
    if config.DEVELOPER_MODE == "off" or ctx is None:
        return False
    if getattr(ctx, "category", "") in ("ide", "terminal"):
        return True
    from formatting import DEV_HOSTS
    host = getattr(ctx, "host", "") or ""
    return any(host == h or host.endswith("." + h) for h in DEV_HOSTS)


def apply(text: str, ctx=None) -> str:
    """The whole Developer Mode pass. Call only when active(ctx)."""
    if not text:
        return text
    for pattern, written in _VOCAB_RE:
        text = pattern.sub(written, text)
    text = _case_cues(text)
    text = _paths(text)
    text = _flags(text)
    text = _dots(text)
    terms = getattr(ctx, "terms", ()) if ctx is not None else ()
    if terms:
        text = snap_identifiers(text, terms)
    if ctx is not None and getattr(ctx, "category", "") == "terminal":
        text = _terminal_command(text)
    return text
