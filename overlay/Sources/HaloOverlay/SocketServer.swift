import Darwin
import Foundation

/// Minimal Unix-domain-socket line server.
///
/// Protocol is newline-delimited plain text, identical to the stdin commands,
/// so the overlay can be driven by `nc -U <sock>` for debugging:
///     listening | processing | done | hide | status | quit | level <0..1>
final class SocketServer {
    private let path: String
    private let onLine: (String) -> String?
    private var listenFD: Int32 = -1
    private let acceptQueue = DispatchQueue(label: "overlay.accept", qos: .userInitiated)
    // MUST be concurrent. The engine holds a persistent connection whose
    // readLoop blocks in read() for the life of the process; on a serial queue
    // that single client starves every other connection (haloctl, nc, a second
    // engine after a restart) forever.
    private let connQueue = DispatchQueue(
        label: "overlay.conn", qos: .userInitiated, attributes: .concurrent)

    init(path: String, onLine: @escaping (String) -> String?) {
        self.path = path
        self.onLine = onLine
    }

    static func defaultPath() -> String {
        if let env = ProcessInfo.processInfo.environment["HALO_OVERLAY_SOCKET"] {
            return env
        }
        return NSHomeDirectory() + "/.halo-overlay.sock"
    }

    func start() -> String? {
        // A stale socket file from a previous crash would make bind() fail.
        unlink(path)

        listenFD = socket(AF_UNIX, SOCK_STREAM, 0)
        guard listenFD >= 0 else { return "socket() failed: \(errno)" }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8)
        let cap = MemoryLayout.size(ofValue: addr.sun_path)
        guard bytes.count < cap else {
            return "socket path too long (\(bytes.count) >= \(cap)): \(path)"
        }
        withUnsafeMutablePointer(to: &addr.sun_path) { p in
            p.withMemoryRebound(to: CChar.self, capacity: cap) { dst in
                for (i, b) in bytes.enumerated() { dst[i] = CChar(bitPattern: b) }
                dst[bytes.count] = 0
            }
        }

        let size = socklen_t(MemoryLayout<sockaddr_un>.size)
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(listenFD, $0, size)
            }
        }
        guard bound == 0 else {
            close(listenFD)
            return "bind() failed: \(String(cString: strerror(errno)))"
        }
        // Only this user may drive the overlay.
        chmod(path, 0o600)

        guard listen(listenFD, 8) == 0 else {
            close(listenFD)
            return "listen() failed: \(String(cString: strerror(errno)))"
        }

        acceptQueue.async { [weak self] in self?.acceptLoop() }
        return nil
    }

    private func acceptLoop() {
        while true {
            let conn = accept(listenFD, nil, nil)
            if conn < 0 {
                if errno == EINTR { continue }
                break
            }
            // Each client gets its own reader; a wedged client cannot block
            // the accept loop or another client.
            connQueue.async { [weak self] in self?.readLoop(conn) }
        }
    }

    private func readLoop(_ conn: Int32) {
        defer { close(conn) }
        var pending = ""
        var buf = [UInt8](repeating: 0, count: 4096)
        while true {
            let n = read(conn, &buf, buf.count)
            if n <= 0 { break }
            pending += String(decoding: buf[0..<n], as: UTF8.self)
            while let idx = pending.firstIndex(of: "\n") {
                let line = String(pending[pending.startIndex..<idx])
                pending = String(pending[pending.index(after: idx)...])
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if !trimmed.isEmpty {
                    // Hop to main for the handler, then write any reply back
                    // so callers like `haloctl status` get a real answer.
                    let reply = DispatchQueue.main.sync { self.onLine(trimmed) }
                    if let reply, let data = (reply + "\n").data(using: .utf8) {
                        _ = data.withUnsafeBytes {
                            Darwin.write(conn, $0.baseAddress, data.count)
                        }
                    }
                }
            }
            // Guard against a client that never sends a newline.
            if pending.count > 64_000 { pending = "" }
        }
    }

    func stop() {
        if listenFD >= 0 { close(listenFD) }
        unlink(path)
    }
}
