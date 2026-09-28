import Foundation

/// The OpenRouter key an older Halo (0.3–0.4) may have left in the Keychain.
///
/// Halo sends nothing off this Mac since 0.5, so nothing reads the key any
/// more. The Privacy pane uses this only to say one is still there and to
/// offer to remove it -- the same thing `halo key delete` does.
///
/// Through `/usr/bin/security`, never the Security framework, and presence
/// only (no `-w`): nothing here needs the secret, so it is never read.
@MainActor
final class KeyStore: ObservableObject {

    static let shared = KeyStore()

    /// Must match `config.KEYCHAIN_SERVICE` in the engine.
    static let service = "halo"

    @Published private(set) var stored = false
    @Published private(set) var message: String?

    func refresh() {
        stored = Self.security(["find-generic-password", "-s", Self.service]) == 0
    }

    /// A fresh window starts clean, and the Keychain may have changed under
    /// `halo key` meanwhile.
    func reset() {
        message = nil
        refresh()
    }

    func clear() {
        _ = Self.security(["delete-generic-password", "-s", Self.service])
        refresh()
        message = stored ? "Could not remove the key." : "Key removed."
    }

    @discardableResult
    private static func security(_ args: [String]) -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        p.arguments = args
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return -1 }
        p.waitUntilExit()
        return p.terminationStatus
    }
}
