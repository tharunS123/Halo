import Foundation

/// Every location the app shares with the Python engine. Mirrors paths.py,
/// including its environment overrides, so a test instance pointed at a
/// throwaway directory never touches the real ones.
enum HaloPaths {
    private static func env(_ name: String, _ fallback: URL) -> URL {
        if let v = ProcessInfo.processInfo.environment[name], !v.isEmpty {
            return URL(fileURLWithPath: (v as NSString).expandingTildeInPath)
        }
        return fallback
    }

    static var home: URL { FileManager.default.homeDirectoryForCurrentUser }
    static var configDir: URL { env("HALO_CONFIG_DIR", home.appendingPathComponent(".config/halo")) }
    static var dataDir: URL {
        env("HALO_DATA_DIR", home.appendingPathComponent("Library/Application Support/Halo"))
    }
    static var modelsDir: URL { env("HALO_MODELS_DIR", dataDir.appendingPathComponent("models")) }
    static var logDir: URL { env("HALO_LOG_DIR", home.appendingPathComponent("Library/Logs/Halo")) }

    static var settings: URL { configDir.appendingPathComponent("settings.json") }
    static var dictionary: URL { configDir.appendingPathComponent("dictionary.json") }
    static var styles: URL { configDir.appendingPathComponent("styles.json") }
    static var transforms: URL { configDir.appendingPathComponent("transforms.json") }
    static var state: URL { dataDir.appendingPathComponent("state.json") }
    static var suggestions: URL { dataDir.appendingPathComponent("suggestions.json") }
    static var history: URL { dataDir.appendingPathComponent("history.sqlite3") }
    static var historyAudio: URL { dataDir.appendingPathComponent("history-audio") }
    static var engineSocket: URL { dataDir.appendingPathComponent("engine.sock") }
    static var diagnostics: URL { dataDir.appendingPathComponent("diagnostics.json") }
    static var localModelStatus: URL { dataDir.appendingPathComponent("local_model.json") }
    static var engineLog: URL { logDir.appendingPathComponent("engine.log") }
    static var legacyAgent: URL {
        home.appendingPathComponent("Library/LaunchAgents/io.github.tharuns123.halo.plist")
    }
}

/// Small JSON-file helpers shared by the stores: missing is not malformed,
/// writes are atomic and key-sorted, and a merge never drops unknown keys.
enum JSONFile {
    enum Read {
        case missing
        case ok([String: Any])
        case malformed(String)
    }

    static func read(_ url: URL) -> Read {
        guard FileManager.default.fileExists(atPath: url.path) else { return .missing }
        guard let data = try? Data(contentsOf: url) else { return .malformed("unreadable") }
        if data.isEmpty { return .missing }
        do {
            guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return .malformed("not a JSON object") }
            return .ok(obj)
        } catch {
            return .malformed(error.localizedDescription)
        }
    }

    static func object(_ url: URL) -> [String: Any] {
        if case .ok(let o) = read(url) { return o }
        return [:]
    }

    @discardableResult
    static func write(_ object: [String: Any], to url: URL) -> Bool {
        guard let data = try? JSONSerialization.data(
            withJSONObject: object, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
        else { return false }
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            // Write-then-rename: the engine polls these on mtime and must
            // never catch one half-written.
            try (data + Data("\n".utf8)).write(to: url, options: .atomic)
            return true
        } catch {
            NSLog("Halo: could not write \(url.lastPathComponent)")
            return false
        }
    }
}

/// The `halo` command line, run with the engine's own interpreter -- one
/// code path for downloads, verification and imports, whichever way the user
/// starts them.
enum HaloCLI {
    static func command(_ args: [String]) -> Process? {
        guard let engine = EngineSupervisor.locate() else { return nil }
        let cli = engine.script.deletingLastPathComponent().appendingPathComponent("cli.py")
        let p = Process()
        p.executableURL = engine.python
        p.arguments = [cli.path] + args
        p.currentDirectoryURL = engine.cwd
        return p
    }

    /// Run to completion off the main thread; `done` gets (exit status, stdout).
    static func run(_ args: [String], done: @escaping @MainActor (Int32, String) -> Void) {
        guard let p = command(args) else {
            Task { @MainActor in done(-1, "") }
            return
        }
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        DispatchQueue.global(qos: .userInitiated).async {
            do { try p.run() } catch {
                Task { @MainActor in done(-1, "") }
                return
            }
            let data = out.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            let text = String(data: data, encoding: .utf8) ?? ""
            let status = p.terminationStatus
            Task { @MainActor in done(status, text) }
        }
    }
}

/// The engine's control socket (control.py): one JSON object per line each
/// way. Used only for what needs the engine itself -- reinserting, retrying,
/// health -- never for configuration, which stays in the JSON files.
enum EngineClient {
    static func request(_ req: [String: Any], timeout: TimeInterval = 90,
                        done: @escaping @MainActor ([String: Any]?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let reply = send(req, timeout: timeout)
            Task { @MainActor in done(reply) }
        }
    }

    private static func send(_ req: [String: Any], timeout: TimeInterval) -> [String: Any]? {
        let path = HaloPaths.engineSocket.path
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { close(fd) }
        var tv = timeval(tv_sec: Int(timeout), tv_usec: 0)
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8)
        let cap = MemoryLayout.size(ofValue: addr.sun_path)
        guard bytes.count < cap else { return nil }
        withUnsafeMutablePointer(to: &addr.sun_path) { p in
            p.withMemoryRebound(to: CChar.self, capacity: cap) { dst in
                for (i, b) in bytes.enumerated() { dst[i] = CChar(bitPattern: b) }
                dst[bytes.count] = 0
            }
        }
        let ok = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard ok == 0,
              var data = try? JSONSerialization.data(withJSONObject: req) else { return nil }
        data.append(0x0A)
        let sent = data.withUnsafeBytes { write(fd, $0.baseAddress, data.count) }
        guard sent == data.count else { return nil }
        var buffer = Data()
        var chunk = [UInt8](repeating: 0, count: 65536)
        while !buffer.contains(0x0A) {
            let n = read(fd, &chunk, chunk.count)
            if n <= 0 { break }
            buffer.append(chunk, count: n)
        }
        guard let line = buffer.split(separator: 0x0A).first else { return nil }
        return try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any]
    }
}
