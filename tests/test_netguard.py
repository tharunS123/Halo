"""netguard: the engine cannot reach anything off this Mac -- and can still
reach everything on it (llama-server on loopback, the overlay and control
sockets). Offline and hermetic: every "blocked" case must fail before a
packet is sent, so nothing here depends on the network being up or down.
"""
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import netguard  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


def blocked(fn) -> bool:
    try:
        fn()
    except netguard.NetworkBlocked:
        return True
    except OSError:
        return False        # got as far as the OS: not blocked by us
    return False


netguard.install()
netguard.install()          # idempotent: a second call must not double-wrap

print("=== off this Mac: refused before anything is sent ===")
check("TCP to a public address", blocked(
    lambda: socket.create_connection(("93.184.216.34", 443), timeout=1)))
check("TCP by name (the lookup itself is refused)", blocked(
    lambda: socket.create_connection(("openrouter.ai", 443), timeout=1)))
check("a bare DNS lookup", blocked(lambda: socket.getaddrinfo("example.com", 80)))
check("connect_ex", blocked(
    lambda: socket.socket().connect_ex(("8.8.8.8", 53))))
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
check("UDP sendto", blocked(lambda: udp.sendto(b"x", ("8.8.8.8", 53))))
udp.close()
check("IPv6 to a public address", blocked(
    lambda: socket.socket(socket.AF_INET6).connect(("2606:4700:4700::1111", 443))))
check("a private LAN address is still off this Mac", blocked(
    lambda: socket.create_connection(("192.168.1.1", 80), timeout=1)))

def requests_blocked() -> bool:
    import requests
    try:
        requests.get("https://example.com", timeout=1)
    except requests.ConnectionError as e:
        # requests wraps what the socket layer raised; find ours in the chain.
        err = e
        while err is not None:
            if isinstance(err, netguard.NetworkBlocked):
                return True
            err = err.__cause__ or err.__context__
        return "local-only" in str(e)
    return False


check("requests (the HTTP client Halo uses)", requests_blocked())
check("every refusal is recorded (host and port only)",
      len(netguard.attempts) >= 7 and all(len(a) == 3 for a in netguard.attempts),
      netguard.attempts)

print("\n=== on this Mac: untouched ===")
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen(4)
port = srv.getsockname()[1]
threading.Thread(target=lambda: [srv.accept() for _ in range(3)], daemon=True).start()
netguard.clear()
for host in ("127.0.0.1", "localhost"):
    try:
        socket.create_connection((host, port), timeout=2).close()
        check(f"loopback by {host}", True)
    except OSError as e:
        check(f"loopback by {host}", False, e)
check("resolving an address given as a number is not a lookup",
      socket.getaddrinfo("10.0.0.1", 80) is not None)

path = os.path.join(tempfile.mkdtemp(), "s.sock")
u = socket.socket(socket.AF_UNIX)
u.bind(path)
u.listen(1)
c = socket.socket(socket.AF_UNIX)
try:
    c.connect(path)
    check("a Unix socket (the overlay, the control socket)", True)
except OSError as e:
    check("a Unix socket (the overlay, the control socket)", False, e)
c.close()
u.close()
check("nothing local was counted as an attempt", netguard.attempts == [], netguard.attempts)

print("\n=== the rule itself ===")
for addr, want in ((("127.0.0.1", 1), True), (("::1", 1), True), (("127.8.9.1", 1), True),
                   (("localhost", 1), True), (("1.1.1.1", 1), False),
                   (("example.com", 1), False), (("::ffff:8.8.8.8", 1), False)):
    check(f"{addr[0]} is {'local' if want else 'off this Mac'}",
          netguard.allowed(socket.AF_INET, addr) == want)

netguard.uninstall()
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
