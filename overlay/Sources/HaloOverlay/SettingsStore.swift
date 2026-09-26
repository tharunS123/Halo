import Foundation
import SwiftUI

/// Read/write access to the same JSON files the Python engine owns.
///
/// There is no IPC for settings and deliberately so. `~/.config/halo/*.json`
/// is already the contract between the engine, the `halo config` CLI and a
/// text editor; adding a socket command would have made the window a fourth
/// writer with its own idea of the truth. Instead the window edits the files,
/// and the engine notices within a second (halo.py `_watch_settings`).
///
/// Two rules the merge below exists to keep:
///
/// 1. **Never drop a key we do not know about.** The file ships with
///    `_comment` strings explaining every section, and `cleanup.models` holds
///    a fallback chain this window does not expose. A naive encode of only
///    the fields with a checkbox would silently delete all of it.
/// 2. **Never write a partial file.** The engine polls on mtime, so it can
///    read at any instant. Writes go to a temp file and are renamed into
///    place, which is atomic on APFS.
@MainActor
final class SettingsStore: ObservableObject {

    static let shared = SettingsStore()

    // MARK: - General
    @Published var hotkey: String = "f9" { didSet { write("hotkey", hotkey) } }
    @Published var activation: String = "hold" { didSet { write("activation", activation) } }
    @Published var maxRecordingSec: Int = 120 { didSet { write("max_recording_sec", maxRecordingSec) } }
    @Published var language: String = "en" { didSet { write("language", language) } }
    @Published var model: String = "small.en" { didSet { write("model", model) } }
    @Published var menuBar: Bool = false {
        didSet {
            write("menu_bar", menuBar)
            if oldValue != menuBar { onMenuBarChanged?(menuBar) }
        }
    }

    // MARK: - Orb
    @Published var overlayEnabled: Bool = true { didSet { write("overlay", overlayEnabled) } }
    @Published var orbScale: Double = 1.0 {
        // Rounded before writing: the slider produces 1.0000000000000002, and
        // a settings file full of float noise is unreadable and invites a
        // pointless engine reload every time the thumb twitches.
        didSet { write("orb.scale", (orbScale * 100).rounded() / 100) }
    }
    @Published var orbPosition: String = "bottom" { didSet { write("orb.position", orbPosition) } }
    @Published var orbInset: Double = 140 {
        didSet { write("orb.inset", Int(orbInset.rounded())) }
    }
    @Published var orbWhileProcessing: Bool = true { didSet { write("orb.show_while_processing", orbWhileProcessing) } }

    // MARK: - Privacy
    @Published var privacyDefault: Bool = false { didSet { write("privacy_default", privacyDefault) } }
    @Published var cleanupEnabled: Bool = true { didSet { write("cleanup.enabled", cleanupEnabled) } }
    @Published var contextEnabled: Bool = true { didSet { write("context.enabled", contextEnabled) } }

    // MARK: - Cleanup
    @Published var cleanupMode: String = "normal" { didSet { write("cleanup.mode", cleanupMode) } }
    @Published var cleanupProvider: String = "auto" { didSet { write("cleanup.provider", cleanupProvider) } }
    @Published var localModel: String = "qwen2.5-1.5b" { didSet { write("cleanup.local.model", localModel) } }
    @Published var selfCorrection: Bool = true { didSet { write("dictation.self_correction", selfCorrection) } }
    @Published var smartFormatting: Bool = true { didSet { write("dictation.smart_formatting", smartFormatting) } }
    @Published var chatPeriod: Bool = false { didSet { write("dictation.chat_period", chatPeriod) } }

    // MARK: - Dictation (all local)
    @Published var spokenPunctuation: Bool = true { didSet { write("dictation.spoken_punctuation", spokenPunctuation) } }
    @Published var stripFillers: Bool = true { didSet { write("dictation.strip_fillers", stripFillers) } }
    @Published var terminalPunctuation: Bool = true { didSet { write("dictation.terminal_punctuation", terminalPunctuation) } }
    @Published var whisperPrompt: Bool = true { didSet { write("whisper.prompt", whisperPrompt) } }
    @Published var suppressNST: Bool = true { didSet { write("whisper.suppress_nst", suppressNST) } }

    // MARK: - Vocabulary
    @Published var terms: [Term] = []
    @Published var fuzzyEnabled: Bool = true { didSet { saveDictionary() } }
    @Published var fuzzyThreshold: Double = 0.90 { didSet { saveDictionary() } }

    /// Set by the app delegate so toggling the checkbox adds/removes the
    /// status item immediately rather than at the next launch.
    var onMenuBarChanged: ((Bool) -> Void)?

    /// One vocabulary entry: the spelling you want, and what whisper says
    /// instead.
    struct Term: Identifiable, Equatable {
        let id = UUID()
        var term: String
        var variants: [String]

        var variantText: String {
            get { variants.joined(separator: ", ") }
            set {
                variants = newValue
                    .split(separator: ",")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
            }
        }
    }

    /// Suppresses the `didSet` writes while load() assigns every property --
    /// otherwise opening the window would rewrite both files ~20 times.
    private var loading = false
    private var settingsRoot: [String: Any] = [:]
    private var dictionaryRoot: [String: Any] = [:]

    /// Set when a file exists but will not parse. Writing is then refused,
    /// because a full-tree save would replace a file we could not read -- and
    /// that file is the user's settings, comments, vocabulary and all. This
    /// mirrors `settings.py`, which raises `SettingsFileError` for exactly the
    /// same reason: one trailing comma left behind by a text editor must not
    /// cost someone every other setting.
    @Published private(set) var loadError: String?

    // MARK: - Locations

    static var configDir: URL {
        if let override = ProcessInfo.processInfo.environment["HALO_CONFIG_DIR"] {
            return URL(fileURLWithPath: (override as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/halo")
    }

    static var settingsURL: URL { configDir.appendingPathComponent("settings.json") }
    static var dictionaryURL: URL { configDir.appendingPathComponent("dictionary.json") }

    private init() { load() }

    // MARK: - Loading

    func load() {
        loading = true
        defer { loading = false }

        loadError = nil
        switch Self.read(Self.settingsURL) {
        case .missing:   settingsRoot = [:]
        case .ok(let o): settingsRoot = o
        case .malformed(let why):
            settingsRoot = [:]
            loadError = "settings.json could not be read: \(why)"
        }
        switch Self.read(Self.dictionaryURL) {
        case .missing:   dictionaryRoot = [:]
        case .ok(let o): dictionaryRoot = o
        case .malformed(let why):
            dictionaryRoot = [:]
            loadError = (loadError.map { $0 + "\n" } ?? "")
                + "dictionary.json could not be read: \(why)"
        }

        hotkey = string("hotkey") ?? "f9"
        activation = string("activation") ?? "hold"
        maxRecordingSec = int("max_recording_sec") ?? 120
        language = string("language") ?? "en"
        model = string("model") ?? "small.en"
        menuBar = bool("menu_bar") ?? false

        overlayEnabled = bool("overlay") ?? true
        orbScale = double("orb.scale") ?? 1.0
        orbPosition = string("orb.position") ?? "bottom"
        orbInset = double("orb.inset") ?? 140
        orbWhileProcessing = bool("orb.show_while_processing") ?? true

        privacyDefault = bool("privacy_default") ?? false
        cleanupEnabled = bool("cleanup.enabled") ?? true
        contextEnabled = bool("context.enabled") ?? true

        cleanupMode = string("cleanup.mode") ?? "normal"
        cleanupProvider = string("cleanup.provider") ?? "auto"
        localModel = string("cleanup.local.model") ?? "qwen2.5-1.5b"
        selfCorrection = bool("dictation.self_correction") ?? true
        smartFormatting = bool("dictation.smart_formatting") ?? true
        chatPeriod = bool("dictation.chat_period") ?? false

        spokenPunctuation = bool("dictation.spoken_punctuation") ?? true
        stripFillers = bool("dictation.strip_fillers") ?? true
        terminalPunctuation = bool("dictation.terminal_punctuation") ?? true
        whisperPrompt = bool("whisper.prompt") ?? true
        suppressNST = bool("whisper.suppress_nst") ?? true

        let raw = dictionaryRoot["terms"] as? [[String: Any]] ?? []
        terms = raw.compactMap { entry in
            guard let name = entry["term"] as? String, !name.isEmpty else { return nil }
            return Term(term: name, variants: entry["variants"] as? [String] ?? [])
        }
        let fuzzy = dictionaryRoot["fuzzy"] as? [String: Any] ?? [:]
        fuzzyEnabled = fuzzy["enabled"] as? Bool ?? true
        fuzzyThreshold = (fuzzy["threshold"] as? NSNumber)?.doubleValue ?? 0.90
    }

    enum ReadResult {
        case missing
        case ok([String: Any])
        case malformed(String)
    }

    /// Missing and malformed are deliberately NOT the same answer. A missing
    /// file is a fresh install and writing one is correct; a malformed file is
    /// a typo in something the user owns, and overwriting it destroys data.
    static func read(_ url: URL) -> ReadResult {
        guard FileManager.default.fileExists(atPath: url.path) else { return .missing }
        guard let data = try? Data(contentsOf: url) else {
            return .malformed("unreadable")
        }
        if data.isEmpty { return .missing }
        do {
            guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return .malformed("not a JSON object") }
            return .ok(obj)
        } catch {
            return .malformed(error.localizedDescription)
        }
    }

    private static func readObject(_ url: URL) -> [String: Any] {
        if case .ok(let o) = read(url) { return o }
        return [:]
    }

    // MARK: - Typed reads over a dotted path

    private func value(_ path: String) -> Any? {
        var node: Any? = settingsRoot
        for part in path.split(separator: ".") {
            guard let dict = node as? [String: Any] else { return nil }
            node = dict[String(part)]
        }
        return node
    }

    private func string(_ p: String) -> String? { value(p) as? String }
    private func bool(_ p: String) -> Bool? { value(p) as? Bool }
    private func int(_ p: String) -> Int? { (value(p) as? NSNumber)?.intValue }
    private func double(_ p: String) -> Double? { (value(p) as? NSNumber)?.doubleValue }

    /// Set one dotted path inside `root`, creating intermediate objects and
    /// leaving every sibling key untouched.
    private static func set(_ root: inout [String: Any], _ path: String, _ value: Any) {
        var parts = path.split(separator: ".").map(String.init)
        guard let key = parts.first else { return }
        if parts.count == 1 {
            root[key] = value
            return
        }
        parts.removeFirst()
        var child = root[key] as? [String: Any] ?? [:]
        set(&child, parts.joined(separator: "."), value)
        root[key] = child
    }

    // MARK: - Saving

    /// Write ONE key, merging into whatever is on disk right now.
    ///
    /// Not a whole-tree save of every published property. The window is one of
    /// three writers -- `halo config set` and a text editor are the others --
    /// and a full snapshot would carry this window's stale idea of every
    /// *other* field back over their changes. Writing only what actually
    /// changed means two writers can only collide on the same key, which is
    /// the same guarantee `settings.py::Settings.set` gives.
    private func write(_ path: String, _ value: Any) {
        guard !loading, loadError == nil else { return }
        switch Self.read(Self.settingsURL) {
        case .malformed:
            // Re-check at write time, not just at load: the file may have been
            // broken by an editor while this window sat open.
            loadError = "settings.json changed and no longer parses"
            return
        case .missing:
            settingsRoot = [:]
        case .ok(let current):
            settingsRoot = current
        }
        Self.set(&settingsRoot, path, value)
        Self.write(settingsRoot, to: Self.settingsURL)
    }

    func saveDictionary() {
        guard !loading, loadError == nil else { return }
        var root = dictionaryRoot
        if case .ok(let current) = Self.read(Self.dictionaryURL) { root = current }
        root["terms"] = terms
            .filter { !$0.term.trimmingCharacters(in: .whitespaces).isEmpty }
            .map { ["term": $0.term.trimmingCharacters(in: .whitespaces),
                    "variants": $0.variants] as [String: Any] }
        var fuzzy = root["fuzzy"] as? [String: Any] ?? [:]
        fuzzy["enabled"] = fuzzyEnabled
        fuzzy["threshold"] = (fuzzyThreshold * 100).rounded() / 100
        root["fuzzy"] = fuzzy
        dictionaryRoot = root
        Self.write(root, to: Self.dictionaryURL)
    }

    /// Atomic, pretty-printed, key-sorted.
    ///
    /// Sorted because JSONSerialization has no insertion order to preserve, so
    /// without it the file would reshuffle on every save and every diff would
    /// be noise. The `_comment` keys survive either way -- they are ordinary
    /// keys in the object, and the merge above never deletes what it does not
    /// recognise.
    private static func write(_ object: [String: Any], to url: URL) {
        guard let data = try? JSONSerialization.data(
            withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        else {
            NSLog("HaloSettings: could not encode \(url.lastPathComponent)")
            return
        }
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            // Write-then-rename: the engine polls this file on mtime and must
            // never catch it half-written.
            let tmp = url.deletingLastPathComponent()
                .appendingPathComponent(".\(url.lastPathComponent).tmp")
            try (data + Data("\n".utf8)).write(to: tmp, options: .atomic)
            _ = try FileManager.default.replaceItemAt(url, withItemAt: tmp)
        } catch {
            NSLog("HaloSettings: could not write \(url.path): \(error)")
        }
    }

    // MARK: - Vocabulary editing

    func addTerm() {
        terms.append(Term(term: "", variants: []))
        // Not saved yet: an empty term would be filtered straight back out,
        // so the new blank row would vanish as you reached for it.
    }

    func removeTerms(at offsets: IndexSet) {
        terms.remove(atOffsets: offsets)
        saveDictionary()
    }

    // MARK: - Orb geometry, for OverlayController

    /// Re-read just the orb section. Cheap enough to call on every dictation,
    /// which is how the overlay picks up a slider change with no restart.
    struct OrbConfig {
        var scale: CGFloat = 1.0
        var position: String = "bottom"
        var inset: CGFloat = 140
        var showWhileProcessing: Bool = true
    }

    static func currentOrbConfig() -> OrbConfig {
        let root = readObject(settingsURL)
        let orb = root["orb"] as? [String: Any] ?? [:]
        var c = OrbConfig()
        if let v = (orb["scale"] as? NSNumber)?.doubleValue {
            // Clamped: a hand-edited 0 would make the panel zero-sized and the
            // orb simply never appear, which reads as "Halo is broken".
            c.scale = CGFloat(min(max(v, 0.6), 1.6))
        }
        if let v = orb["position"] as? String { c.position = v }
        if let v = (orb["inset"] as? NSNumber)?.doubleValue {
            c.inset = CGFloat(min(max(v, 0), 2000))
        }
        if let v = orb["show_while_processing"] as? Bool { c.showWhileProcessing = v }
        return c
    }
}
