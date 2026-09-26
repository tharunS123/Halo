import Foundation
import ServiceManagement

/// "Launch Halo at Login", with exactly one startup mechanism at a time.
///
/// Two can exist, and must never both be on:
///
///   legacy   ~/Library/LaunchAgents/io.github.tharuns123.halo.plist, written
///            by `halo setup`. launchd starts the app with HALO_SUPERVISE=1
///            and restarts it if it crashes (KeepAlive).
///   modern   SMAppService.mainApp: a login item macOS manages and lists in
///            System Settings > General > Login Items.
///
/// An existing legacy agent IS the setting: turning it off deletes the plist
/// (no `launchctl bootout`, which would kill this very process), and turning
/// it back on uses the modern API. So the migration happens only when the
/// user touches the switch, and nothing is registered twice.
///
/// A login-item launch has no environment, so the app supervises the engine
/// whenever it was not started by `python halo.py` (see main.swift), and
/// finds the engine through the engine.json pointer `halo setup` writes.
enum LoginItem {
    static var legacyInstalled: Bool {
        FileManager.default.fileExists(atPath: HaloPaths.legacyAgent.path)
    }

    static var modernStatus: SMAppService.Status { SMAppService.mainApp.status }

    static var enabled: Bool { legacyInstalled || modernStatus == .enabled }

    static var needsApproval: Bool { !legacyInstalled && modernStatus == .requiresApproval }

    static var mechanism: String {
        if legacyInstalled { return "Login agent from `halo setup`" }
        switch modernStatus {
        case .enabled: return "macOS login item"
        case .requiresApproval: return "Waiting for approval in System Settings"
        default: return "Off"
        }
    }

    /// Returns an error message, or nil on success.
    static func set(_ on: Bool) -> String? {
        do {
            if on {
                if legacyInstalled || modernStatus == .enabled { return nil }
                try SMAppService.mainApp.register()
                if modernStatus == .requiresApproval {
                    SMAppService.openSystemSettingsLoginItems()
                    return "Approve Halo in System Settings › General › Login Items."
                }
            } else {
                if legacyInstalled {
                    try FileManager.default.removeItem(at: HaloPaths.legacyAgent)
                }
                if modernStatus == .enabled || modernStatus == .requiresApproval {
                    try SMAppService.mainApp.unregister()
                }
            }
            return nil
        } catch {
            return "macOS refused: \(error.localizedDescription)"
        }
    }
}
