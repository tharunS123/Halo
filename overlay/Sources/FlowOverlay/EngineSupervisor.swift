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
    private var lastLaunch = Date.distantPast
    private let onFatal: (String) -> Void

    init(onFatal: @escaping (String) -> Void) {
        self.onFatal = onFatal
    }

    /// <project root>/overlay/WisprFlow.app  ->  <project root>
    static func projectRoot() -> URL {
        if let override = ProcessInfo.processInfo.environment["FLOW_PROJECT_DIR"] {
            return URL(fileURLWithPath: override)
        }
        return Bundle.main.bundleURL          // .../overlay/WisprFlow.app
            .deletingLastPathComponent()      // .../overlay
            .deletingLastPathComponent()      // project root
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

    private func launch() {
        let root = Self.projectRoot()
        let python = root.appendingPathComponent(".venv/bin/python")
        let script = root.appendingPathComponent("flow.py")

        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: python.path) else {
            onFatal("venv missing"); return
        }
        guard fm.fileExists(atPath: script.path) else {
            onFatal("flow.py missing"); return
        }

        let p = Process()
        p.executableURL = python
        p.arguments = [script.path]
        p.currentDirectoryURL = root

        var env = ProcessInfo.processInfo.environment
        env["FLOW_OVERLAY_CHILD"] = "1"        // do not spawn/kill the overlay
        env["PYTHONUNBUFFERED"] = "1"
        p.environment = env

        // Capture anything Python emits before it opens its own log (import
        // errors, tracebacks) -- otherwise early crashes are invisible.
        if let handle = Self.engineLogHandle() {
            p.standardOutput = handle
            p.standardError = handle
        }

        p.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            DispatchQueue.main.async { self?.engineExited(code: code) }
        }

        do {
            try p.run()
            process = p
            lastLaunch = Date()
            NSLog("FlowOverlay: engine started pid=\(p.processIdentifier)")
        } catch {
            onFatal("engine launch failed")
        }
    }

    private func engineExited(code: Int32) {
        process = nil
        if stopping { return }

        if code == Self.exitConfig {
            NSLog("FlowOverlay: engine reported a config error; not restarting")
            return   // the engine already showed its own error pill
        }

        // A run that lasted a while was healthy; reset the backoff.
        if Date().timeIntervalSince(lastLaunch) > 60 {
            restarts = 0
        }
        restarts += 1

        if restarts > 6 {
            onFatal("Dictation keeps crashing")
            NSLog("FlowOverlay: giving up after \(restarts) restarts")
            return
        }

        let delay = min(30.0, pow(2.0, Double(restarts - 1)))
        NSLog("FlowOverlay: engine exited (\(code)); restart #\(restarts) in \(delay)s")
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, !self.stopping else { return }
            self.launch()
        }
    }

    private static func engineLogHandle() -> FileHandle? {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/WisprFlowClone")
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
