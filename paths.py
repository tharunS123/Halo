"""Where Halo keeps things.

Every location has an environment override, because the same code runs from
three different layouts: a git checkout (development), a Homebrew install
(`$(brew --prefix)/opt/halo/libexec`), and a test harness pointed at a temp
directory.

The split that matters: code and defaults are installed and replaced on
upgrade; user data is seeded once and never touched again. Before this
existed, `dictionary.json` lived next to `config.py` in the repo, so every
`git pull` conflicted with the user's own vocabulary.
"""
import os
import shutil
from pathlib import Path

HOME = Path.home()


def _env_dir(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


# --- user-owned: seeded once, never overwritten by an upgrade -------------
CONFIG_DIR = _env_dir("HALO_CONFIG_DIR", HOME / ".config" / "halo")
DATA_DIR = _env_dir("HALO_DATA_DIR", HOME / "Library" / "Application Support" / "Halo")
MODELS_DIR = _env_dir("HALO_MODELS_DIR", DATA_DIR / "models")
LOG_DIR = _env_dir("HALO_LOG_DIR", HOME / "Library" / "Logs" / "Halo")

SETTINGS_FILE = CONFIG_DIR / "settings.json"
DICTIONARY_FILE = CONFIG_DIR / "dictionary.json"
SNIPPETS_FILE = CONFIG_DIR / "snippets.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"

STATE_FILE = DATA_DIR / "state.json"
# Where the Swift app looks up the interpreter and script when launchd did not
# tell it (someone double-clicked Halo.app in Finder).
ENGINE_POINTER = DATA_DIR / "engine.json"

ENGINE_LOG = LOG_DIR / "engine.log"
OVERLAY_LOG = LOG_DIR / "overlay.log"

# The TCC identity. It lives outside the Cellar on purpose: Homebrew paths are
# versioned, so an upgrade would void the Accessibility grant, and this path is
# one click away in the System Settings file picker.
INSTALLED_APP = HOME / "Applications" / "Halo.app"

# --- pre-1.0 locations, still read so an existing install keeps working ---
LEGACY_STATE_FILE = HOME / ".halo-state.json"
LEGACY_WHISPER_DIR = HOME / "whisper.cpp"
LEGACY_WHISPER_MODELS = LEGACY_WHISPER_DIR / "models"

_HERE = Path(__file__).resolve().parent

# --- install-owned: replaced wholesale on upgrade -------------------------
# Homebrew lays the engine out as libexec/engine/*.py beside libexec/share/,
# while a checkout keeps defaults/ next to the code.
DEFAULTS_DIR = next(
    (p for p in (_HERE.parent / "share" / "defaults", _HERE / "defaults") if p.is_dir()),
    _HERE / "defaults",
)

_PLIST_NAME = "io.github.tharuns123.halo.plist.template"
LAUNCHD_TEMPLATE = next(
    (p for p in (_HERE.parent / "share" / "launchd" / _PLIST_NAME,
                 _HERE / "launchd" / _PLIST_NAME) if p.is_file()),
    _HERE / "launchd" / _PLIST_NAME,
)

# The app bundle shipped with this install: libexec/Halo.app when installed by
# Homebrew, overlay/Halo.app in a checkout. `halo setup` copies it to
# INSTALLED_APP, and only when its code hash actually differs.
BUNDLED_APP = next(
    (p for p in (_HERE.parent / "Halo.app", _HERE / "overlay" / "Halo.app")
     if p.is_dir()),
    None,
)

SEEDED_FILES = ("settings.json", "dictionary.json", "snippets.json", "commands.json")


def seed_user_config() -> list[Path]:
    """Copy any missing default into the user's config dir. Returns what was
    created. Copy-if-absent, per file: an upgrade must never overwrite a
    vocabulary someone has been editing for months."""
    created = []
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for name in SEEDED_FILES:
        src, dst = DEFAULTS_DIR / name, CONFIG_DIR / name
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            created.append(dst)
    return created


def migrate_legacy_state() -> bool:
    """Move ~/.halo-state.json into the data dir. Privacy Mode persists across
    restarts by design, so a silent reset on upgrade would be a broken promise."""
    if STATE_FILE.exists() or not LEGACY_STATE_FILE.exists():
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_STATE_FILE, STATE_FILE)
    return True


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, MODELS_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
