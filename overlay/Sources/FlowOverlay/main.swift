import AppKit

// .accessory == no Dock icon, no menu bar, never becomes the active app.
let app = NSApplication.shared
app.setActivationPolicy(.accessory)

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let controller = OverlayController()
    private var server: SocketServer?
    private var supervisor: EngineSupervisor?
    private var sigterm: DispatchSourceSignal?

    func applicationDidFinishLaunching(_ note: Notification) {
        controller.makePanelIfNeeded()

        let path = SocketServer.defaultPath()
        let s = SocketServer(path: path) { [weak self] line in
            self?.handle(line)
        }
        if let err = s.start() {
            log("FATAL: could not listen on \(path): \(err)")
            NSApp.terminate(nil)
            return
        }
        server = s
        log("FlowOverlay ready. socket=\(path)")
        log("commands: listening | processing | done | hide | status | quit | level <0..1>")

        readStdin()
        installSignalHandler()
        requestMicrophoneIfNeeded()

        // Background mode: we own the engine. Terminal mode leaves this off so
        // `python flow.py` keeps behaving exactly as before.
        if ProcessInfo.processInfo.environment["FLOW_SUPERVISE"] == "1" {
            let sup = EngineSupervisor { [weak self] msg in
                self?.controller.flashError(msg)
            }
            supervisor = sup
            log("supervising the Python engine")
            sup.start()
        }
    }

    /// The engine records through us (it is our child), so the microphone grant
    /// belongs to this bundle. Ask on first run: until something asks, the app
    /// is not even listed in System Settings > Privacy & Security > Microphone,
    /// and that pane offers no way to add it manually.
    private func requestMicrophoneIfNeeded() {
        switch Permissions.microphone {
        case .authorized:
            return
        case .notDetermined:
            log("requesting microphone access...")
            Permissions.requestMicrophone { [weak self] granted in
                self?.log("microphone access granted: \(granted)")
                if !granted { self?.controller.flashError("Microphone denied") }
            }
        default:
            log("microphone access is \(Permissions.microphoneText)")
            controller.flashError("Microphone \(Permissions.microphoneText)")
        }
    }

    /// launchd stops agents with SIGTERM, which Cocoa does not turn into a
    /// clean shutdown on its own. Without this the engine would be orphaned.
    private func installSignalHandler() {
        signal(SIGTERM, SIG_IGN)
        let src = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        src.setEventHandler { NSApp.terminate(nil) }
        src.resume()
        sigterm = src
    }

    func applicationWillTerminate(_ note: Notification) {
        supervisor?.stop()
        server?.stop()
    }

    private func log(_ s: String) {
        FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
    }

    /// One command parser shared by the socket and stdin. Returns text to send
    /// back to a socket client, or nil.
    @discardableResult
    private func handle(_ raw: String) -> String? {
        let cmd = raw.trimmingCharacters(in: .whitespaces).lowercased()
        switch cmd {
        case "listening":  controller.show(.listening)
        case "processing": controller.show(.processing)
        case "done":       controller.flashDone()
        case "hide":       controller.hide()
        case "quit":       NSApp.terminate(nil)
        case "status":     return controller.status()
        default:
            if raw.lowercased().hasPrefix("flash ") {
                controller.flashInfo(
                    String(raw.dropFirst("flash ".count))
                        .trimmingCharacters(in: .whitespaces))
                return nil
            }
            if cmd.hasPrefix("privacy ") {
                controller.setPrivacy(cmd.hasSuffix("1") || cmd.hasSuffix("on"))
                return nil
            }
            // `error <message>` keeps the original casing of the message.
            if raw.lowercased().hasPrefix("error ") {
                let msg = String(raw.dropFirst("error ".count))
                    .trimmingCharacters(in: .whitespaces)
                controller.flashError(msg)
                return nil
            }
            let parts = cmd.split(separator: " ")
            if parts.count == 2, parts[0] == "level", let v = Double(parts[1]) {
                controller.pushLevel(CGFloat(v))
            } else {
                log("unknown command: \(raw)")
            }
        }
        return nil
    }

    /// Kept for manual debugging; the socket is the real interface.
    private func readStdin() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            while let line = readLine(strippingNewline: true) {
                DispatchQueue.main.async { self?.handle(line) }
            }
        }
    }
}

let delegate = MainActor.assumeIsolated { AppDelegate() }
app.delegate = delegate
app.run()
