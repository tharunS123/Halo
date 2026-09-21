import Foundation

/// The optional OpenRouter key, as the Settings window sees it.
///
/// Everything goes through `/usr/bin/security` rather than the Security
/// framework, and that is load-bearing. The engine reads the key with
/// `security find-generic-password`, from a launchd agent with no UI to answer
/// a Keychain prompt. An item written by `SecItemAdd` from this app would trust
/// Halo.app and nothing else, so the engine's read would raise an "allow
/// access?" dialog nobody is there to click, and cleanup would silently stop.
/// Writing with `security -T /usr/bin/security` gives the item exactly the ACL
/// `halo key set` gives it, so either writer produces the same item.
///
/// The window writes the key but never reads it back: nothing here needs the
/// secret, so it is not kept in this process any longer than the save takes.
@MainActor
final class KeyStore: ObservableObject {

    static let shared = KeyStore()

    /// Must match `config.KEYCHAIN_SERVICE` in the engine.
    static let service = "halo"

    @Published private(set) var stored = false
    /// What is typed in the field. Lives here, not in the view, because
    /// `@State` is unavailable under the Command Line Tools (see SettingsView).
    @Published var draft = ""
    /// The result of the last save or removal, shown under the field.
    @Published private(set) var message: String?
    @Published private(set) var failed = false

    /// Presence only -- no `-w`, so the secret is never printed to us.
    func refresh() {
        stored = Self.security(["find-generic-password", "-s", Self.service]) == 0
    }

    /// A fresh window starts clean: a half-typed key or last week's "Saved"
    /// should not survive a close, and the Keychain may have changed under
    /// `halo key` meanwhile.
    func reset() {
        draft = ""
        message = nil
        refresh()
    }

    func save() {
        let key = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return }
        // The key goes to `security -i` inside double quotes. OpenRouter keys
        // are `sk-or-v1-` plus hex, so anything with a quote, a backslash or
        // whitespace is a paste accident, not a key -- and refusing it is
        // simpler than escaping it correctly.
        guard key.unicodeScalars.allSatisfy({ $0.isASCII && $0.value > 0x20
                                              && $0 != "\"" && $0 != "\\" })
        else {
            report("That doesn't look like a key — it has spaces or quotes in it.",
                   failed: true)
            return
        }

        // Through stdin, not argv: `-w <key>` on the command line would be
        // readable by any process listing arguments while it runs.
        let account = NSUserName()
        let command = "add-generic-password -s \(Self.service) -a \"\(account)\" "
            + "-T /usr/bin/security -U -w \"\(key)\"\n"
        // `security -i` exits non-zero when a command inside it fails. The
        // status is what counts: with a key already stored, a failed replace
        // would still leave `stored` true.
        let status = Self.security(["-i"], stdin: command)
        draft = ""
        refresh()
        if status == 0 && stored {
            report(key.hasPrefix("sk-or-")
                   ? "Saved to your Keychain. Halo uses it from the next dictation."
                   : "Saved, but OpenRouter keys usually start with “sk-or-” — "
                     + "check you copied the whole thing.",
                   failed: !key.hasPrefix("sk-or-"))
        } else {
            report("Could not save to the Keychain. `halo key set` in Terminal "
                   + "will say why.", failed: true)
        }
    }

    func clear() {
        _ = Self.security(["delete-generic-password", "-s", Self.service])
        refresh()
        report(stored ? "Could not remove the key." : "Key removed.", failed: stored)
    }

    private func report(_ text: String, failed: Bool) {
        message = text
        self.failed = failed
    }

    @discardableResult
    private static func security(_ args: [String], stdin: String? = nil) -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        p.arguments = args
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        let pipe = Pipe()
        if stdin != nil { p.standardInput = pipe }
        do { try p.run() } catch { return -1 }
        if let stdin {
            pipe.fileHandleForWriting.write(Data(stdin.utf8))
            try? pipe.fileHandleForWriting.close()
        }
        p.waitUntilExit()
        return p.terminationStatus
    }
}
