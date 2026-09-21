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
final class EngineSupervisor {

    /// Python exits with this when it is misconfigured (missing permission,
    /// broken whisper install). Restarting cannot help, so we do not.
    private static let exitConfig: Int32 = 78

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
    static func projectRoot() -> URL {
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
    static func locate() -> EngineLocation? {
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
        stop()                 // also bumps past any pending exit callback
        generation += 1
        restarts = 0
        stopping = false
        launch()
    }

    private func launch() {
        guard let engine = Self.locate() else {
            // The pill is the only channel a background install has, so name
            // the command that fixes it rather than the thing that is missing.
            onFatal("Run: halo setup"); return
        }

        let p = Process()
        p.executableURL = engine.python
        p.arguments = [engine.script.path]
        p.currentDirectoryURL = engine.cwd

        var env = ProcessInfo.processInfo.environment
        env["HALO_OVERLAY_CHILD"] = "1"        // do not spawn/kill the overlay
        env["PYTHONUNBUFFERED"] = "1"
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
            NSLog("HaloOverlay: engine started pid=\(p.processIdentifier)")
        } catch {
            onFatal("engine launch failed")
        }
    }

    private func engineExited(code: Int32, era: Int) {
        guard era == generation else {
            NSLog("HaloOverlay: ignoring exit from a superseded engine")
            return
        }
        process = nil
        if stopping { return }

        if code == Self.exitConfig {
            NSLog("HaloOverlay: engine reported a config error; not restarting")
            return   // the engine already showed its own error pill
        }

        // A run that lasted a while was healthy; reset the backoff.
        if Date().timeIntervalSince(lastLaunch) > 60 {
            restarts = 0
        }
        restarts += 1

        if restarts > 6 {
            onFatal("Dictation keeps crashing")
            NSLog("HaloOverlay: giving up after \(restarts) restarts")
            return
        }

        let delay = min(30.0, pow(2.0, Double(restarts - 1)))
        NSLog("HaloOverlay: engine exited (\(code)); restart #\(restarts) in \(delay)s")
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            // Re-check the era: a manual restart during the backoff already
            // started a new engine, and this retry would make a second one.
            guard let self, !self.stopping, era == self.generation else { return }
            self.launch()
        }
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
