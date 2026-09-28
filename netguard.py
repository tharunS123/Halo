"""Nothing leaves this Mac: the engine refuses every connection off it.

Halo's promise since 0.5 is that dictation is local, full stop. A promise
kept by "no code path happens to call out" is one refactor from broken, so
the engine enforces it instead: `install()` wraps the socket layer so that a
connection to anything but this machine -- or a DNS lookup that would tell a
resolver what we were about to reach -- raises `NetworkBlocked` before a
packet is sent.

Allowed, because they never leave the machine:

  - Unix sockets (the overlay, the control socket)
  - loopback addresses: llama-server on 127.0.0.1, or an Ollama / LM Studio /
    mlx_lm.server endpoint on this Mac
  - resolving "localhost", or an address given as a number

Model downloads are not affected: they run in `halo model ...`, a separate
process the Settings window starts on request, never in the engine.

`attempts` records what was refused (host and port only, never a payload)
so tests can prove the count is zero and `halo doctor` can say so.
"""
import ipaddress
import socket
import threading

_lock = threading.Lock()
_installed = False
_original: dict = {}

# (what, host, port) for every refused attempt, newest last. Bounded.
attempts: list[tuple[str, str, int]] = []

_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class NetworkBlocked(ConnectionRefusedError):
    """Raised instead of opening a connection off this Mac."""


def _is_local_host(host) -> bool:
    if host is None:
        return True          # getaddrinfo(None, port): the local wildcard
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip().lower().rstrip(".")
    if host in _LOCAL_NAMES or host == "":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _is_numeric(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        ipaddress.ip_address(str(host).split("%", 1)[0])
        return True
    except ValueError:
        return False


def allowed(family, address) -> bool:
    """Whether a connect()/sendto() to `address` stays on this machine."""
    if family == getattr(socket, "AF_UNIX", object()):
        return True
    if isinstance(address, tuple) and address:
        return _is_local_host(address[0])
    if isinstance(address, (str, bytes)):
        # An AF_UNIX path handed to a socket whose family we could not read.
        return True
    return False


def _refuse(what: str, host, port) -> None:
    with _lock:
        attempts.append((what, str(host), int(port or 0)))
        del attempts[:-50]
    raise NetworkBlocked(f"Halo is local-only: refused {what} to {host}:{port}")


def _port(address) -> int:
    try:
        return int(address[1]) if isinstance(address, tuple) and len(address) > 1 else 0
    except (TypeError, ValueError):
        return 0


def install() -> None:
    """Idempotent. Call once, as early as possible in the engine."""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
        sock = socket.socket
        _original.update(connect=sock.connect, connect_ex=sock.connect_ex,
                         sendto=sock.sendto, getaddrinfo=socket.getaddrinfo)

    def connect(self, address):
        if not allowed(self.family, address):
            _refuse("connect", address[0] if isinstance(address, tuple) else address,
                    _port(address))
        return _original["connect"](self, address)

    def connect_ex(self, address):
        if not allowed(self.family, address):
            _refuse("connect", address[0] if isinstance(address, tuple) else address,
                    _port(address))
        return _original["connect_ex"](self, address)

    def sendto(self, data, *args):
        address = args[-1] if args else None
        if address is not None and not allowed(self.family, address):
            _refuse("sendto", address[0] if isinstance(address, tuple) else address,
                    _port(address))
        return _original["sendto"](self, data, *args)

    def getaddrinfo(host, port, *args, **kwargs):
        # A lookup is itself a disclosure: the resolver learns the name.
        if not _is_local_host(host) and not _is_numeric(host):
            _refuse("lookup", host, port if isinstance(port, int) else 0)
        return _original["getaddrinfo"](host, port, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = getaddrinfo


def uninstall() -> None:
    """For tests only."""
    global _installed
    with _lock:
        if not _installed:
            return
        socket.socket.connect = _original["connect"]
        socket.socket.connect_ex = _original["connect_ex"]
        socket.socket.sendto = _original["sendto"]
        socket.getaddrinfo = _original["getaddrinfo"]
        _installed = False


def installed() -> bool:
    return _installed


def clear() -> None:
    with _lock:
        attempts.clear()
