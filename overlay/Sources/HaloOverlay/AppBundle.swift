import AppKit
import Foundation

/// What this copy of Halo.app is, and the chores only a downloaded copy has.
///
/// The .dmg ships a self-contained bundle: the engine, a Python runtime and
/// whisper-cli / llama-server all live inside it (scripts/make-app.sh). The
/// Homebrew and checkout builds carry only the Swift app and find the engine
/// elsewhere, so everything here is a no-op for them.
enum AppBundle {
    static var contents: URL { Bundle.main.bundleURL.appendingPathComponent("Contents") }
    static var helpers: URL { contents.appendingPathComponent("Helpers") }
    static var resources: URL { contents.appendingPathComponent("Resources") }

    /// True for the downloaded app: it carries its own engine.
    static var isSelfContained: Bool {
        FileManager.default.fileExists(atPath: resources.appendingPathComponent("engine/halo.py").path)
    }

    /// The bundled interpreter and engine, or nil outside the downloaded app.
    static var engine: (python: URL, script: URL)? {
        guard isSelfContained else { return nil }
        return (resources.appendingPathComponent("python/bin/python3"),
                resources.appendingPathComponent("engine/halo.py"))
    }

    /// Running straight off the disk image, or from a quarantined folder that
    /// macOS "translocated" to a random read-only path. Either way the bundle
    /// cannot be written, so its helpers keep their quarantine and Gatekeeper
    /// kills them on launch -- and a login item would point at a path that
    /// vanishes on eject.
    static var isMisplaced: Bool {
        // Both are read-only mounts; an Applications folder on an external
        // drive is not, and is fine.
        let url = Bundle.main.bundleURL
        let readOnly = (try? url.resourceValues(forKeys: [.volumeIsReadOnlyKey]))?
            .volumeIsReadOnly ?? false
        return readOnly || url.path.contains("/AppTranslocation/")
    }

    /// Drop com.apple.quarantine from everything inside the bundle.
    ///
    /// By the time this runs the user has already let Halo open (System
    /// Settings › Privacy & Security › Open Anyway), but that approval covers
    /// the app, not the programs it starts: a quarantined python3 or
    /// whisper-cli is killed outright (SIGKILL, measured) the moment the
    /// engine execs it. The attribute is not part of the code signature, so
    /// removing it leaves the seal intact -- `codesign --verify --strict` still
    /// passes afterwards.
    static func clearQuarantine() {
        guard isSelfContained, !isMisplaced else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/xattr")
        p.arguments = ["-dr", "com.apple.quarantine", Bundle.main.bundlePath]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
        p.waitUntilExit()
    }

    /// Explain the one thing that has to happen first, then quit. Opening
    /// Applications in Finder beside the disk image leaves the user one drag
    /// from done.
    @MainActor
    static func askToMoveToApplications() {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Move Halo to Applications first"
        alert.informativeText = """
            Halo is running from the disk image or your Downloads folder, where \
            macOS will not let it start its speech engine.

            Drag Halo into the Applications folder, then open it from there.
            """
        alert.addButton(withTitle: "Show Applications")
        alert.addButton(withTitle: "Quit")
        if alert.runModal() == .alertFirstButtonReturn {
            NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications"))
        }
        NSApp.terminate(nil)
    }
}
