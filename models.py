"""Whisper model catalog and downloader.

Homebrew deliberately ships no models (they are hundreds of megabytes and
change independently of the code), so Halo fetches them itself into
~/Library/Application Support/Halo/models/.

Downloads go to a .part file and are only renamed into place after the
checksum matches, so an interrupted download can never masquerade as a
working model -- whisper.cpp's failure on a truncated file is obscure.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

import paths

BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

# sha256 as published by HuggingFace (the LFS object id of each file).
CATALOG = {
    "small.en": {
        "size": 487614201,
        "sha256": "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
        "note": "English only. The default: best accuracy for its size.",
    },
    "small": {
        "size": 487601967,
        "sha256": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
        "note": "99 languages. Needed for any language other than English.",
    },
    "base.en": {
        "size": 147964211,
        "sha256": "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002",
        "note": "English only, a third the size. Faster, noticeably rougher.",
    },
    "base": {
        "size": 147951465,
        "sha256": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        "note": "99 languages, smaller and rougher than small.",
    },
    "tiny.en": {
        "size": 77704715,
        "sha256": "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f",
        "note": "English only. Fastest, least accurate; fine for testing.",
    },
    "medium.en": {
        "size": 1533774781,
        "sha256": "cc37e93478338ec7700281a7ac30a10128929eb8f427dda2e865faa8f6da4356",
        "note": "English only, 1.5GB. Slower than realtime on some Macs.",
    },
}


# Local cleanup models (GGUF, run by llama.cpp's llama-server). Opt-in: Halo
# works without one, and they are 1-2.5GB. Both are Apache-2.0 licensed, so
# nothing about using them depends on terms Halo cannot pass on. sha256 is the
# HuggingFace LFS object id.
LLM_CATALOG = {
    "qwen2.5-1.5b": {
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
               "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size": 1117320736,
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        # Measured on an M1 Pro: 0.1-0.55s per utterance, 1.2s to load.
        "note": "The default. Fast enough for every utterance.",
    },
    "qwen3-4b": {
        "file": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "url": "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/"
               "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "size": 2497281120,
        "sha256": "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
        # Measured on an M1 Pro: 0.25-1.2s per utterance, 1.7s to load.
        "note": "Better grammar and rewrites; 2-3x slower.",
    },
}


class ModelError(RuntimeError):
    pass


def human(size: int) -> str:
    mb = size / 1_000_000
    return f"{mb/1000:.1f}GB" if mb >= 1000 else f"{mb:.0f}MB"


def filename(name: str) -> str:
    return f"ggml-{name}.bin"


def installed_path(name: str) -> Path | None:
    """Where this model already is, managed dir first, then a pre-1.0
    ~/whisper.cpp checkout so an existing download is reused, not re-fetched."""
    for d in (paths.MODELS_DIR, paths.LEGACY_WHISPER_MODELS):
        p = d / filename(name)
        if p.exists() and p.stat().st_size > 1_000_000:
            return p
    return None


def installed() -> dict[str, Path]:
    return {n: p for n in CATALOG if (p := installed_path(n))}


def sha256_of(path: Path, progress: bool = False) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
            done += len(chunk)
            if progress and total:
                pct = 100 * done / total
                print(f"\r  verifying... {pct:5.1f}%", end="", flush=True)
    if progress:
        print("\r  verifying... done   ")
    return h.hexdigest()


def download(name: str, force: bool = False, quiet: bool = False) -> Path:
    """Fetch a model, verify it, and put it in the managed models dir."""
    if name not in CATALOG:
        raise ModelError(f"unknown model {name!r}. Known: {', '.join(CATALOG)}")

    existing = installed_path(name)
    if existing and not force:
        if not quiet:
            print(f"  {filename(name)} already installed at {existing}")
        return existing

    spec = CATALOG[name]
    return _fetch(f"{BASE_URL}/{filename(name)}", paths.MODELS_DIR / filename(name),
                  spec["size"], spec["sha256"], quiet)


def _fetch(url: str, target: Path, size: int, sha256: str, quiet: bool) -> Path:
    paths.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")

    if not quiet:
        print(f"  downloading {target.name} ({human(size)})")
        print(f"  from {url}")

    # curl rather than urllib: a free progress bar and -C - resume, both of
    # which matter for a 465MB file on a hotel connection.
    cmd = ["curl", "-L", "--fail", "-C", "-", "-o", str(part), url]
    cmd.insert(1, "--progress-bar" if not quiet and sys.stderr.isatty() else "--silent")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise ModelError(
            f"download failed (curl exit {r.returncode}). The partial file is "
            f"kept at {part}; run the same command again to resume.")

    actual = sha256_of(part, progress=not quiet and sys.stdout.isatty())
    if actual != sha256:
        part.unlink(missing_ok=True)
        raise ModelError(
            f"checksum mismatch for {target.name}\n"
            f"  expected {sha256}\n"
            f"  got      {actual}\n"
            "The download was corrupted or the file upstream changed; "
            "the partial file has been deleted.")

    part.replace(target)
    if not quiet:
        print(f"  installed {target}")
    return target


# --- local cleanup models -------------------------------------------------

def llm_path(name: str) -> Path | None:
    """The installed GGUF for `name`, or None. A size check, not a hash: this
    runs before every server start, and hashing 2.5GB takes seconds. The hash
    was checked when the file was downloaded; a truncated or replaced file
    fails the size check or fails to load, and either reports itself."""
    spec = LLM_CATALOG.get(name)
    if not spec:
        return None
    p = paths.MODELS_DIR / spec["file"]
    try:
        if p.stat().st_size == spec["size"]:
            return p
    except OSError:
        pass
    return None


def download_llm(name: str, force: bool = False, quiet: bool = False) -> Path:
    if name not in LLM_CATALOG:
        raise ModelError(f"unknown local model {name!r}. Known: {', '.join(LLM_CATALOG)}")
    existing = llm_path(name)
    if existing and not force:
        if not quiet:
            print(f"  {existing.name} already installed at {existing}")
        return existing
    spec = LLM_CATALOG[name]
    return _fetch(spec["url"], paths.MODELS_DIR / spec["file"], spec["size"],
                  spec["sha256"], quiet)


def verify_llm(name: str) -> bool:
    spec = LLM_CATALOG.get(name)
    p = paths.MODELS_DIR / spec["file"] if spec else None
    if not p or not p.exists():
        print(f"  {name}: not installed")
        return False
    ok = sha256_of(p, progress=sys.stdout.isatty()) == spec["sha256"]
    print(f"  {name}: {'OK' if ok else 'CHECKSUM MISMATCH'} ({p})")
    return ok


def remove_llm(name: str) -> bool:
    spec = LLM_CATALOG.get(name)
    if not spec:
        return False
    removed = False
    for p in (paths.MODELS_DIR / spec["file"],
              paths.MODELS_DIR / (spec["file"] + ".part")):
        if p.exists():
            p.unlink()
            removed = True
    return removed


def print_llm_catalog(current: str = "") -> None:
    print("  model          size    status      notes")
    for name, spec in LLM_CATALOG.items():
        status = "installed" if llm_path(name) else "-"
        mark = "*" if name == current else " "
        print(f" {mark}{name:<13} {human(spec['size']):>6}  {status:<11} {spec['note']}")


def print_catalog() -> None:
    have = installed()
    print("  model       size    status      notes")
    for name, spec in CATALOG.items():
        path = have.get(name)
        status = "installed" if path else "-"
        print(f"  {name:<11} {human(spec['size']):>6}  {status:<11} {spec['note']}")
    if have:
        print()
        for name, path in have.items():
            print(f"  {name}: {path}")


def verify(name: str) -> bool:
    path = installed_path(name)
    if not path:
        print(f"  {name}: not installed")
        return False
    ok = sha256_of(path, progress=sys.stdout.isatty()) == CATALOG[name]["sha256"]
    print(f"  {name}: {'OK' if ok else 'CHECKSUM MISMATCH'} ({path})")
    return ok


if __name__ == "__main__":       # small convenience for development
    if len(sys.argv) > 1:
        download(sys.argv[1])
    else:
        print_catalog()
