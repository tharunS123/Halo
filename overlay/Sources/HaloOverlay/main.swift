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
    private var menuBar: MenuBarItem?

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
        log("HaloOverlay ready. socket=\(path)")
        log("commands: listening | processing | done | hide | status | settings "
            + "| quit | level <0..1>")

        installMenuBar()

        readStdin()
        installSignalHandler()
        requestMicrophoneIfNeeded()

        // Background mode: we own the engine. Terminal mode leaves this off so
        // `python halo.py` keeps behaving exactly as before.
        if ProcessInfo.processInfo.environment["HALO_SUPERVISE"] == "1" {
            let sup = EngineSupervisor { [weak self] msg in
                self?.controller.flashError(msg)
            }
            supervisor = sup
            log("supervising the Python engine")
            sup.start()
        }
    }

    /// The menu bar item is opt-in, so this usually installs nothing. The
    /// closure on the store is what makes the checkbox take effect live
    /// instead of at the next launch.
    private func installMenuBar() {
        let item = MenuBarItem(
            onSettings: { SettingsWindowController.shared.show() },
            onRestart: { [weak self] in self?.restartEngine() },
            onPrivacy: { [weak self] on in self?.setPrivacyFromUI(on) })
        menuBar = item
        item.setVisible(SettingsStore.shared.menuBar)
        SettingsStore.shared.onMenuBarChanged = { [weak item] visible in
            item?.setVisible(visible)
        }
    }

    /// Only meaningful in background mode, where we own the engine. In
    /// terminal mode the engine is our PARENT, and killing it from here would
    /// take down the thing that started us.
    private func restartEngine() {
        guard let supervisor else {
            controller.flashInfo("Run: halo restart")
            return
        }
        controller.flashInfo("Restarting dictation")
        supervisor.restart()
    }

    /// Privacy Mode flipped from the menu rather than by voice.
    ///
    /// The engine owns this state, and we cannot reach into another process,
    /// so we write the state file it reloads on mtime (privacy.py) and update
    /// our own indicators immediately. The engine picks it up before the next
    /// utterance is cleaned.
    private func setPrivacyFromUI(_ on: Bool) {
        controller.setPrivacy(on)
        menuBar?.setPrivacy(on)
        controller.flashInfo(on ? "Privacy ON" : "Privacy OFF")

        let url = Self.stateFileURL()
        var obj = (try? Data(contentsOf: url))
            .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            ?? [:]
        obj["privacy_mode"] = on
        guard let data = try? JSONSerialization.data(
            withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]) else { return }
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        do {
            try data.write(to: url, options: .atomic)
        } catch {
            log("could not persist privacy mode: \(error)")
        }
    }

    private static func stateFileURL() -> URL {
        let env = ProcessInfo.processInfo.environment
        if let dir = env["HALO_DATA_DIR"] {
            return URL(fileURLWithPath: (dir as NSString).expandingTildeInPath)
                .appendingPathComponent("state.json")
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Halo/state.json")
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
        // `halo settings` reaches the window without a menu bar icon, which is
        // what lets the icon stay off by default.
        case "settings":
            SettingsWindowController.shared.show()
            return "opened"
        default:
            if raw.lowercased().hasPrefix("flash ") {
                controller.flashInfo(
                    String(raw.dropFirst("flash ".count))
                        .trimmingCharacters(in: .whitespaces))
                return nil
            }
            if cmd.hasPrefix("privacy ") {
                let on = cmd.hasSuffix("1") || cmd.hasSuffix("on")
                controller.setPrivacy(on)
                // Keep the menu's checkmark honest when the engine flips this
                // by voice.
                menuBar?.setPrivacy(on)
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
