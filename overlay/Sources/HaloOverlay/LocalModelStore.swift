import Foundation

/// The local cleanup model, as the Settings window sees it.
///
/// The engine owns the model: it downloads through `halo model local install`
/// (resumable, checksum-verified in models.py) and runs llama-server itself.
/// This window only reads the status file the engine writes and, for the
/// Download button, runs that same CLI command -- one code path for the
/// download, whichever way you start it.
///
/// The status file never holds dictated text, only "loading", "ready" and
/// why not, so reading it here is not a privacy question.
@MainActor
final class LocalModelStore: ObservableObject {

    static let shared = LocalModelStore()

    /// Mirrors `models.LLM_CATALOG`: the file name and size are how this
    /// window tells "installed" from "half downloaded" without asking Python.
    struct Model: Identifiable {
        let id: String
        let file: String
        let size: Int64
        let label: String
    }

    static let catalog: [Model] = [
        Model(id: "qwen2.5-1.5b", file: "qwen2.5-1.5b-instruct-q4_k_m.gguf",
              size: 1_117_320_736, label: "Qwen2.5 1.5B — 1.1 GB, fast (default)"),
        Model(id: "qwen3-4b", file: "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
              size: 2_497_281_120, label: "Qwen3 4B — 2.5 GB, better rewrites, slower"),
    ]

    @Published private(set) var state = ""          // engine's word for it
    @Published private(set) var detail = ""
    @Published private(set) var serverFound = false
    @Published private(set) var downloading: String?
    @Published private(set) var progress: Double = 0
    @Published private(set) var message: String?
    @Published private(set) var failed = false
    /// Bumped on every refresh so views re-ask `installed(_:)`.
    @Published private(set) var revision = 0

    private var poll: Timer?
    private var process: Process?

    static var dataDir: URL {
        if let override = ProcessInfo.processInfo.environment["HALO_DATA_DIR"] {
            return URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Halo")
    }

    static var modelsDir: URL {
        if let override = ProcessInfo.processInfo.environment["HALO_MODELS_DIR"] {
            return URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
        }
        return dataDir.appendingPathComponent("models")
    }

    func installed(_ id: String) -> Bool {
        guard let m = Self.catalog.first(where: { $0.id == id }) else { return false }
        let url = Self.modelsDir.appendingPathComponent(m.file)
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size]
                    as? NSNumber)?.int64Value
        return size == m.size
    }

    /// Re-read the status file and check for llama-server. Cheap: two stats
    /// and a small JSON read.
    func refresh() {
        let url = Self.dataDir.appendingPathComponent("local_model.json")
        if let data = try? Data(contentsOf: url),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            state = obj["state"] as? String ?? ""
            detail = obj["detail"] as? String ?? ""
        } else {
            state = ""
            detail = ""
        }
        serverFound = ["/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"]
            .contains { FileManager.default.isExecutableFile(atPath: $0) }
        revision += 1
    }

    /// Poll while the window shows this section, so "loading" turns into
    /// "ready" in front of you. Stopped on disappear: nothing ticks while
    /// the window is closed.
    func startWatching() {
        refresh()
        poll?.invalidate()
        poll = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    func stopWatching() {
        poll?.invalidate()
        poll = nil
    }

    private func tick() {
        refresh()
        guard let id = downloading,
              let m = Self.catalog.first(where: { $0.id == id }) else { return }
        let part = Self.modelsDir.appendingPathComponent(m.file + ".part")
        let done = (try? FileManager.default.attributesOfItem(atPath: part.path)[.size]
                    as? NSNumber)?.int64Value ?? 0
        progress = min(1, Double(done) / Double(m.size))
    }

    func download(_ id: String) {
        guard downloading == nil else { return }
        guard let engine = EngineSupervisor.locate() else {
            report("Could not find Halo's engine. Run `halo model local install` "
                   + "in Terminal instead.", failed: true)
            return
        }
        let cli = engine.script.deletingLastPathComponent().appendingPathComponent("cli.py")
        let p = Process()
        p.executableURL = engine.python
        p.arguments = [cli.path, "model", "local", "install", id]
        p.currentDirectoryURL = engine.cwd
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        p.terminationHandler = { [weak self] proc in
            let status = proc.terminationStatus
            Task { @MainActor in self?.finished(id, status: status) }
        }
        do {
            try p.run()
        } catch {
            report("Could not start the download: \(error.localizedDescription)", failed: true)
            return
        }
        process = p
        downloading = id
        progress = 0
        message = nil
        if poll == nil { startWatching() }
    }

    func cancelDownload() {
        process?.terminate()
    }

    private func finished(_ id: String, status: Int32) {
        process = nil
        downloading = nil
        refresh()
        if installed(id) {
            report("Downloaded and verified. Halo loads it on your next dictation.",
                   failed: false)
        } else if status == 15 {
            report("Download stopped. Start it again to resume where it left off.",
                   failed: true)
        } else {
            report("The download did not finish. `halo model local install` in "
                   + "Terminal resumes it and says why.", failed: true)
        }
    }

    func remove(_ id: String) {
        guard let m = Self.catalog.first(where: { $0.id == id }) else { return }
        for name in [m.file, m.file + ".part"] {
            try? FileManager.default.removeItem(
                at: Self.modelsDir.appendingPathComponent(name))
        }
        refresh()
        report("Removed. Cleanup falls back to the local rules.", failed: false)
    }

    private func report(_ text: String, failed: Bool) {
        message = text
        self.failed = failed
    }

    /// One line for the status row.
    func describe(_ id: String) -> String {
        if let d = downloading, d == id {
            return String(format: "Downloading… %.0f%%", progress * 100)
        }
        guard installed(id) else { return "Not downloaded" }
        if !serverFound { return "Downloaded — needs llama.cpp: brew install llama.cpp" }
        switch state {
        case "ready": return "Loaded and ready"
        case "loading": return "Loading into memory…"
        case "failed": return "Failed: \(detail)"
        case "stopped":
            return detail.isEmpty ? "Downloaded — loads when you next dictate" : detail
        default: return "Downloaded — loads when you next dictate"
        }
    }
}
