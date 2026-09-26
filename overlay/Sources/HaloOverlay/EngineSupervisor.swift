import AppKit
import Foundation

/// Runs the Python dictation engine as a child process and keeps it alive.
///
/// Being the PARENT is the whole point: a child inherits its nearest .app
/// ancestor as the TCC responsible process, so the engine's global key tap and
/// synthetic Cmd+V are attributed to this bundle. That means permissions are
/// granted once, to this app, instead of to whichever terminal happened to
/// launch Python.
@MainActor
final class EngineSupervisor: ObservableObject {

    /// The running supervisor, for Settings > Advanced. Nil in terminal mode,
    /// where the engine is our parent rather than our child.
    static weak var current: EngineSupervisor?

    /// Python exits with this when it is misconfigured (missing permission,
    /// no speech model). An immediate restart cannot help, so instead it is
    /// retried quietly every 20 seconds -- and at once when Accessibility is
    /// granted -- so fixing the cause in System Settings or Settings > Models
    /// brings dictation back without anyone running `halo restart`.
    private static let exitConfig: Int32 = 78

    /// What Settings > Advanced shows. Never contains dictated text.
    @Published private(set) var state = "starting"
    @Published private(set) var pid: Int32 = 0
    @Published private(set) var crashes: [Date] = []
    @Published private(set) var lastExit: Int32?
    @Published private(set) var startedAt: Date?
    private var configRetry: Timer?
    private var permissionWatch: Timer?

    private var process: Process?
    private var stopping = false
    private var restarts = 0
    /// Bumped on every launch. A terminationHandler or a delayed retry that
    /// belongs to an older generation is ignored, which is what stops
    /// `restart()` racing the dying process: without it the old engine's exit
    /// callback lands after the replacement is already running, clears
    /// `process`, and schedules a second launch.
    private var generation = 0
    private var lastLaunch = Date.distantPast
    private let onFatal: (String) -> Void

    init(onFatal: @escaping (String) -> Void) {
        self.onFatal = onFatal
        EngineSupervisor.current = self
    }

    /// A Python interpreter, the engine script, and where to run it.
    struct EngineLocation {
        let python: URL
        let script: URL
        let cwd: URL
    }

    /// <project root>/overlay/Halo.app  ->  <project root>
    ///
    /// Only meaningful inside a git checkout. An installed app lives in
    /// ~/Applications and has no project root, which is why `locate()` tries
    /// this last.
    nonisolated static func projectRoot() -> URL {
        if let override = ProcessInfo.processInfo.environment["HALO_PROJECT_DIR"] {
            return URL(fileURLWithPath: override)
        }
        return Bundle.main.bundleURL          // .../overlay/Halo.app
            .deletingLastPathComponent()      // .../overlay
            .deletingLastPathComponent()      // project root
    }

    /// Where the Python engine lives, in order of authority.
    ///
    /// The bundle used to derive this from its own path, which hard-wired it
    /// two levels inside a source checkout next to a `.venv`. An installed
    /// copy has neither, so the launcher tells us instead.
    nonisolated static func locate() -> EngineLocation? {
        let env = ProcessInfo.processInfo.environment
        let fm = FileManager.default

        func usable(_ python: URL, _ script: URL) -> EngineLocation? {
            guard fm.isExecutableFile(atPath: python.path),
                  fm.fileExists(atPath: script.path) else { return nil }
            return EngineLocation(python: python, script: script,
                                  cwd: script.deletingLastPathComponent())
        }

        // 1. What the LaunchAgent sets -- the normal background path.
        if let py = env["HALO_PYTHON"], let script = env["HALO_ENGINE"],
           let found = usable(URL(fileURLWithPath: py), URL(fileURLWithPath: script)) {
            return found
        }

        // 2. Pointer file written by `halo setup`, for a launch with no env:
        //    someone double-clicking Halo.app in Finder.
        let pointer = fm.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Halo/engine.json")
        if let data = try? Data(contentsOf: pointer),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: String],
           let py = obj["python"], let script = obj["script"],
           let found = usable(URL(fileURLWithPath: py), URL(fileURLWithPath: script)) {
            return found
        }

        // 3. A Homebrew install, at its version-stable opt path.
        for prefix in ["/opt/homebrew", "/usr/local"] {
            let libexec = URL(fileURLWithPath: prefix)
                .appendingPathComponent("opt/halo/libexec")
            if let found = usable(libexec.appendingPathComponent("venv/bin/python"),
                                  libexec.appendingPathComponent("engine/halo.py")) {
                return found
            }
        }

        // 4. A git checkout: HALO_PROJECT_DIR, or this bundle's own location.
        let root = projectRoot()
        return usable(root.appendingPathComponent(".venv/bin/python"),
                      root.appendingPathComponent("halo.py"))
    }

    func start() {
        stopping = false
        launch()
    }

    func stop() {
        stopping = true
        guard let p = process, p.isRunning else { return }
        p.terminate()
        // Give it a moment to close the mic and clean up, then insist.
        let deadline = Date().addingTimeInterval(2.0)
        while p.isRunning && Date() < deadline {
            usleep(50_000)
        }
        if p.isRunning { kill(p.processIdentifier, SIGKILL) }
        process = nil
    }

    /// Stop and start, resetting the backoff. Used by the menu bar item, and
    /// by anything else that means "try again now" rather than "recover from
    /// a crash" -- the crash path deliberately backs off, and reusing it here
    /// would make a manual restart take up to 30 seconds.
    func restart() {
        configRetry?.invalidate()
        permissionWatch?.invalidate()
        stop()                 // also bumps past any pending exit callback
        generation += 1
        restarts = 0
        stopping = false
        launch()
    }

    private func launch(quiet: Bool = false) {
        guard let engine = Self.locate() else {
            // The pill is the only channel a background install has, so name
            // the command that fixes it rather than the thing that is missing.
            state = "engine not found"
            onFatal("Run: halo setup"); return
        }

        let p = Process()
        p.executableURL = engine.python
        p.arguments = [engine.script.path]
        p.currentDirectoryURL = engine.cwd

        var env = ProcessInfo.processInfo.environment
        env["HALO_OVERLAY_CHILD"] = "1"        // do not spawn/kill the overlay
        env["PYTHONUNBUFFERED"] = "1"
        if quiet { env["HALO_QUIET_START"] = "1" }   // a retry: no repeat error pill
        // A login-item or Finder launch has launchd's bare PATH; the engine
        // looks in Homebrew itself, but this keeps any subprocess honest.
        if !(env["PATH"] ?? "").contains("/opt/homebrew/bin") {
            env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin")
        }
        p.environment = env

        // Capture anything Python emits before it opens its own log (import
        // errors, tracebacks) -- otherwise early crashes are invisible.
        if let handle = Self.engineLogHandle() {
            p.standardOutput = handle
            p.standardError = handle
        }

        generation += 1
        let era = generation
        p.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            DispatchQueue.main.async { self?.engineExited(code: code, era: era) }
        }

        do {
            try p.run()
            process = p
            lastLaunch = Date()
            startedAt = lastLaunch
            pid = p.processIdentifier
            state = "running"
            writeDiagnostics()
            NSLog("HaloOverlay: engine started pid=\(p.processIdentifier)")
        } catch {
            state = "could not start"
            onFatal("engine launch failed")
        }
    }

    private func engineExited(code: Int32, era: Int) {
        guard era == generation else {
            NSLog("HaloOverlay: ignoring exit from a superseded engine")
            return
        }
        process = nil
        pid = 0
        lastExit = code
        if stopping {
            state = "stopped"
            writeDiagnostics()
            return
        }

        if code == Self.exitConfig {
            // The engine already showed its own error pill. Try again quietly
            // later, and at once if the missing permission shows up.
            state = "waiting: needs a permission or a model"
            NSLog("HaloOverlay: engine reported a config error; retrying in 20s")
            writeDiagnostics()
            scheduleConfigRetry(era: era)
            return
        }

        // A run that lasted a while was healthy; reset the backoff.
        if Date().timeIntervalSince(lastLaunch) > 60 {
            restarts = 0
        }
        restarts += 1
        crashes = (crashes + [Date()]).suffix(20)
        state = "restarting after a crash"
        writeDiagnostics()

        // Never give up for good: a hotkey that silently stops working is the
        // worst failure Halo has. After six quick crashes, slow right down
        // and say so once.
        if restarts == 7 {
            onFatal("Dictation keeps crashing")
        }
        let delay = restarts > 6 ? 60.0 : min(30.0, pow(2.0, Double(restarts - 1)))
        NSLog("HaloOverlay: engine exited (\(code)); restart #\(restarts) in \(delay)s")
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            // Re-check the era: a manual restart during the backoff already
            // started a new engine, and this retry would make a second one.
            guard let self, !self.stopping, era == self.generation else { return }
            self.launch()
        }
    }

    private func scheduleConfigRetry(era: Int) {
        configRetry?.invalidate()
        configRetry = Timer.scheduledTimer(withTimeInterval: 20, repeats: false) { [weak self] _ in
            Task { @MainActor in
                guard let self, !self.stopping, era == self.generation, self.process == nil else { return }
                self.launch(quiet: true)
            }
        }
        let trustedAtFailure = Permissions.accessibility
        permissionWatch?.invalidate()
        permissionWatch = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] t in
            Task { @MainActor in
                guard let self, !self.stopping, era == self.generation, self.process == nil else {
                    t.invalidate(); return
                }
                if !trustedAtFailure && Permissions.accessibility {
                    t.invalidate()
                    NSLog("HaloOverlay: Accessibility granted; starting the engine")
                    self.configRetry?.invalidate()
                    self.launch()
                }
            }
        }
    }

    /// Crash notes for Settings > Advanced and bug reports: times and exit
    /// codes only. The engine log holds the details, and it holds no text.
    private func writeDiagnostics() {
        let f = ISO8601DateFormatter()
        JSONFile.write([
            "state": state, "pid": Int(pid), "restarts": restarts,
            // NSNull, not a nil Optional: JSONSerialization throws on the latter.
            "last_exit": lastExit.map { Int($0) as Any } ?? NSNull(),
            "crashes": crashes.map { f.string(from: $0) },
            "started_at": startedAt.map { f.string(from: $0) as Any } ?? NSNull(),
            "updated": f.string(from: Date()),
        ], to: HaloPaths.diagnostics)
    }

    private static func engineLogHandle() -> FileHandle? {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Halo")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("engine.log")
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let h = try? FileHandle(forWritingTo: url) else { return nil }
        h.seekToEndOfFile()
        return h
    }
}
