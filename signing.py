"""A stable code-signing identity, so upgrades stop voiding permissions.

Ad-hoc signing makes the binary's code hash the app's identity, so macOS sees
a brand new app after any change at all -- including a plain version bump,
because CFBundleVersion lives in Info.plist, inside the bundle. Measured on the
same source:

    VERSION=0.2.0  ->  cdhash 124ed5d2...
    VERSION=0.3.0  ->  cdhash d8cc7900...

With a certificate the hash is not part of the identity:

    ad-hoc       designated => cdhash H"d8cc7900..."
    certificate  designated => identifier "io.github.tharuns123.halo"
                               and certificate leaf = H"662f5d97..."

So two builds that genuinely differ produce the *same* designated requirement,
and the TCC grant carries over. Verified directly: two bundles differing only
in CFBundleVersion (cdhash f12df4c0 vs 254ea514) signed with one certificate
both came out with an identical requirement.

The certificate is self-signed, untrusted, and never leaves this Mac. That is
enough. codesign accepts an untrusted certificate -- `security find-identity`
reports CSSMERR_TP_NOT_TRUSTED and signing succeeds anyway -- so this needs no
admin password and changes no trust settings. Gatekeeper does reject such a
signature, which does not matter here: Homebrew builds the app locally, so it
never carries com.apple.quarantine and Gatekeeper is never consulted. Shipping
a downloadable build would be a different story, and is exactly what
ARCHITECTURE.md rules out.

The private key lives in its own keychain rather than the login keychain, so
`halo uninstall` can remove it with a single file delete and nothing of ours is
left behind in the keychain someone actually uses.
"""
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

IDENTITY_CN = "Halo Signing"
KEYCHAIN = Path.home() / "Library" / "Keychains" / "halo-signing.keychain-db"
# `security` wants the path without the -db suffix when creating.
_KEYCHAIN_ARG = str(KEYCHAIN).removesuffix("-db")
# The keychain's own password, kept in the login keychain like the API key.
PW_SERVICE = "halo-signing"

_OPENSSL = "/usr/bin/openssl"   # LibreSSL; verified sufficient, no brew dep


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def available() -> bool:
    """Everything this needs is present on a stock Mac."""
    return Path(_OPENSSL).exists()


def _password() -> str | None:
    r = _run(["security", "find-generic-password", "-s", PW_SERVICE, "-w"])
    return r.stdout.strip() if r.returncode == 0 else None


def _store_password(pw: str) -> bool:
    return _run(["security", "add-generic-password", "-s", PW_SERVICE,
                 "-a", os.environ.get("USER", "halo"), "-U", "-w", pw]).returncode == 0


def identity_sha1() -> str | None:
    """SHA-1 of our signing identity, or None if there is not one yet.

    Deliberately NOT `find-identity -v`: the -v filter means "valid", and a
    self-signed certificate is never valid to the trust policy. It signs fine.
    """
    if not KEYCHAIN.exists():
        return None
    r = _run(["security", "find-identity", "-p", "codesigning", _KEYCHAIN_ARG])
    for line in r.stdout.splitlines():
        if IDENTITY_CN in line:
            m = re.search(r"\b([0-9A-F]{40})\b", line)
            if m:
                return m.group(1)
    return None


def unlock() -> bool:
    pw = _password()
    if not pw:
        return False
    return _run(["security", "unlock-keychain", "-p", pw,
                 _KEYCHAIN_ARG]).returncode == 0


def create_identity() -> str | None:
    """Generate the certificate and import it. Returns its SHA-1, or None."""
    existing = identity_sha1()
    if existing:
        return existing

    pw = _password() or secrets.token_urlsafe(24)
    tmp = Path(tempfile.mkdtemp(prefix="halo-signing-"))
    try:
        cnf = tmp / "openssl.cnf"
        # A config file rather than -addext: LibreSSL is what /usr/bin/openssl
        # is, and this form works on both it and OpenSSL 3.
        cnf.write_text(
            "[req]\ndistinguished_name = dn\nx509_extensions = v3\nprompt = no\n"
            f"[dn]\nCN = {IDENTITY_CN}\n"
            "[v3]\nbasicConstraints = critical,CA:false\n"
            "keyUsage = critical,digitalSignature\n"
            "extendedKeyUsage = critical,codeSigning\n"
        )
        key, crt, p12 = tmp / "k.pem", tmp / "c.pem", tmp / "i.p12"
        if _run([_OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-days", "3650", "-keyout", str(key), "-out", str(crt),
                 "-config", str(cnf)]).returncode != 0:
            return None
        # Apple's importer rejects OpenSSL 3's default PKCS12 algorithms, so
        # ask for the legacy ones. LibreSSL already uses them and ignores these.
        export = [_OPENSSL, "pkcs12", "-export", "-out", str(p12),
                  "-inkey", str(key), "-in", str(crt), "-passout", "pass:halo"]
        if _run(export + ["-macalg", "sha1", "-keypbe", "PBE-SHA1-3DES",
                          "-certpbe", "PBE-SHA1-3DES"]).returncode != 0 \
                and _run(export).returncode != 0:
            return None

        if not KEYCHAIN.exists():
            if _run(["security", "create-keychain", "-p", pw,
                     _KEYCHAIN_ARG]).returncode != 0:
                return None
            # No auto-lock: an upgrade re-signs unattended via `halo setup`.
            _run(["security", "set-keychain-settings", _KEYCHAIN_ARG])
        _run(["security", "unlock-keychain", "-p", pw, _KEYCHAIN_ARG])
        if _run(["security", "import", str(p12), "-k", _KEYCHAIN_ARG,
                 "-P", "halo", "-T", "/usr/bin/codesign",
                 "-A"]).returncode != 0:
            return None
        # Without this, codesign trips the "allow access" GUI prompt.
        _run(["security", "set-key-partition-list", "-S", "apple-tool:,apple:",
              "-s", "-k", pw, _KEYCHAIN_ARG])
        _store_password(pw)
        return identity_sha1()
    finally:
        for f in tmp.glob("*"):
            f.unlink(missing_ok=True)
        tmp.rmdir()


def sign(app: Path) -> bool:
    """Re-sign `app` with our identity. False if there is no identity."""
    sha = identity_sha1()
    if not sha or not app.is_dir():
        return False
    unlock()
    return _run(["codesign", "--force", "--deep", "--keychain", _KEYCHAIN_ARG,
                 "--sign", sha, str(app)]).returncode == 0


def requirement(app: Path) -> str | None:
    """The app's designated requirement: what TCC actually keys the grant on.

    This, not the cdhash, is the thing to compare across upgrades once a
    certificate is in use.
    """
    if not app.is_dir():
        return None
    r = _run(["codesign", "-d", "--requirements", "-", str(app)])
    for line in (r.stdout + r.stderr).splitlines():
        if "designated =>" in line:
            return line.split("designated =>", 1)[1].strip()
    return None


def is_adhoc(app: Path) -> bool:
    req = requirement(app)
    return bool(req and req.startswith("cdhash"))


def remove() -> None:
    """Drop the identity and its keychain. Used by `halo uninstall`."""
    if KEYCHAIN.exists():
        _run(["security", "delete-keychain", _KEYCHAIN_ARG])
        KEYCHAIN.unlink(missing_ok=True)
    _run(["security", "delete-generic-password", "-s", PW_SERVICE])
