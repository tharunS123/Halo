import Foundation
import SwiftUI

/// Read/write access to settings.json, the file the Python engine owns.
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
///
/// The vocabulary, styles and transforms have stores of their own
/// (Stores.swift); they follow the same two rules.
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
    @Published var sounds: Bool = false { didSet { write("sounds", sounds) } }

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

    // MARK: - Languages
    @Published var enabledLanguages: [String] = ["en"] { didSet { write("languages.enabled", enabledLanguages) } }
    @Published var regions: [String: String] = [:] { didSet { write("languages.region", regions) } }

    // MARK: - Microphone
    @Published var micDevice: String = "" { didSet { write("microphone.device", micDevice) } }

    // MARK: - Intelligence
    @Published var developerMode: String = "auto" { didSet { write("developer_mode", developerMode) } }
    @Published var learningEnabled: Bool = true { didSet { write("learning.enabled", learningEnabled) } }
    @Published var stylesEnabled: Bool = true { didSet { write("styles.enabled", stylesEnabled) } }

    // MARK: - Command Mode
    @Published var commandModeEnabled: Bool = true { didSet { write("command_mode.enabled", commandModeEnabled) } }
    @Published var commandTrigger: String = "shift" { didSet { write("command_mode.trigger", commandTrigger) } }
    @Published var commandHotkey: String = "" { didSet { write("command_mode.hotkey", commandHotkey) } }

    // MARK: - History
    @Published var historyEnabled: Bool = false { didSet { write("history.enabled", historyEnabled) } }
    @Published var historyRetention: String = "7d" { didSet { write("history.retention", historyRetention) } }
    @Published var historyKeepAudio: Bool = false { didSet { write("history.keep_audio", historyKeepAudio) } }
    @Published var historyAudioRetention: String = "24h" { didSet { write("history.audio_retention", historyAudioRetention) } }

    // MARK: - Advanced
    @Published var insertionMethod: String = "auto" { didSet { write("insertion.method", insertionMethod) } }
    @Published var debugLogContent: Bool = false { didSet { write("debug.log_content", debugLogContent) } }

    /// Set by the app delegate so toggling the checkbox adds/removes the
    /// status item immediately rather than at the next launch.
    var onMenuBarChanged: ((Bool) -> Void)?

    /// Suppresses the `didSet` writes while load() assigns every property --
    /// otherwise opening the window would rewrite the file ~40 times.
    private var loading = false
    private var settingsRoot: [String: Any] = [:]

    /// Set when settings.json exists but will not parse. Writing is then
    /// refused, because a full-tree save would replace a file we could not
    /// read. This mirrors `settings.py`, which raises `SettingsFileError` for
    /// exactly the same reason: one trailing comma left behind by a text
    /// editor must not cost someone every other setting.
    @Published private(set) var loadError: String?

    // MARK: - Locations

    static var configDir: URL { HaloPaths.configDir }
    static var settingsURL: URL { HaloPaths.settings }

    private init() { load() }

    // MARK: - Loading

    func load() {
        loading = true
        defer { loading = false }

        loadError = nil
        switch JSONFile.read(Self.settingsURL) {
        case .missing:   settingsRoot = [:]
        case .ok(let o): settingsRoot = o
        case .malformed(let why):
            settingsRoot = [:]
            loadError = "settings.json could not be read: \(why)"
        }

        hotkey = string("hotkey") ?? "f9"
        activation = string("activation") ?? "hold"
        maxRecordingSec = int("max_recording_sec") ?? 120
        language = string("language") ?? "en"
        model = string("model") ?? "small.en"
        menuBar = bool("menu_bar") ?? false
        sounds = bool("sounds") ?? false

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

        let langs = value("languages.enabled") as? [String] ?? []
        enabledLanguages = langs.isEmpty ? ["en"] : langs
        regions = value("languages.region") as? [String: String] ?? [:]
        micDevice = string("microphone.device") ?? ""
        developerMode = string("developer_mode") ?? "auto"
        learningEnabled = bool("learning.enabled") ?? true
        stylesEnabled = bool("styles.enabled") ?? true
        commandModeEnabled = bool("command_mode.enabled") ?? true
        commandTrigger = string("command_mode.trigger") ?? "shift"
        commandHotkey = string("command_mode.hotkey") ?? ""
        historyEnabled = bool("history.enabled") ?? false
        historyRetention = string("history.retention") ?? "7d"
        historyKeepAudio = bool("history.keep_audio") ?? false
        historyAudioRetention = string("history.audio_retention") ?? "24h"
        insertionMethod = string("insertion.method") ?? "auto"
        debugLogContent = bool("debug.log_content") ?? false
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
        switch JSONFile.read(Self.settingsURL) {
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
        JSONFile.write(settingsRoot, to: Self.settingsURL)
    }

    /// Back to defaults: every setting key goes, so the engine's built-in
    /// defaults apply. The `_comment` strings, whisper-cli's location and the
    /// OpenRouter model chain stay.
    func resetToDefaults() {
        guard loadError == nil else { return }
        let old = JSONFile.object(Self.settingsURL)
        var root = old.filter { $0.key.hasPrefix("_") || $0.key == "whisper_bin" }
        var cleanup = (old["cleanup"] as? [String: Any] ?? [:]).filter { $0.key.hasPrefix("_") }
        if let models = (old["cleanup"] as? [String: Any])?["models"] { cleanup["models"] = models }
        root["cleanup"] = cleanup
        JSONFile.write(root, to: Self.settingsURL)
        load()
    }

    // MARK: - Languages

    func setLanguage(_ code: String) {
        language = code
        guard code != "auto" else { return }
        if !enabledLanguages.contains(code) { enabledLanguages.append(code) }
        var state = JSONFile.object(HaloPaths.state)
        var recent = (state["languages_recent"] as? [String] ?? []).filter { $0 != code }
        recent.insert(code, at: 0)
        state["languages_recent"] = Array(recent.prefix(5))
        JSONFile.write(state, to: HaloPaths.state)
    }

    func recentLanguages() -> [String] {
        JSONFile.object(HaloPaths.state)["languages_recent"] as? [String] ?? []
    }

    // MARK: - For the overlay, read fresh each time

    static func soundsEnabled() -> Bool {
        JSONFile.object(HaloPaths.settings)["sounds"] as? Bool ?? false
    }

    /// Re-read just the orb section. Cheap enough to call on every dictation,
    /// which is how the overlay picks up a slider change with no restart.
    struct OrbConfig {
        var scale: CGFloat = 1.0
        var position: String = "bottom"
        var inset: CGFloat = 140
        var showWhileProcessing: Bool = true
    }

    static func currentOrbConfig() -> OrbConfig {
        let root = JSONFile.object(settingsURL)
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

/// Mirrors languages.py for display. The engine is the truth; this is the
/// list of names the pickers show.
enum LanguageInfo {
    static let all: [(String, String, [String])] = [
        ("en", "English", ["en-US", "en-GB", "en-AU", "en-CA", "en-IN"]),
        ("es", "Spanish", ["es-ES", "es-MX", "es-US"]), ("fr", "French", ["fr-FR", "fr-CA"]),
        ("de", "German", ["de-DE", "de-AT", "de-CH"]), ("it", "Italian", []),
        ("pt", "Portuguese", ["pt-BR", "pt-PT"]), ("nl", "Dutch", []), ("ru", "Russian", []),
        ("ja", "Japanese", []), ("ko", "Korean", []), ("zh", "Chinese", ["zh-CN", "zh-TW"]),
        ("hi", "Hindi", []), ("ta", "Tamil", []), ("te", "Telugu", []), ("ar", "Arabic", []),
        ("tr", "Turkish", []), ("pl", "Polish", []), ("sv", "Swedish", []),
        ("uk", "Ukrainian", []), ("vi", "Vietnamese", []),
    ]

    static func name(_ code: String) -> String {
        code == "auto" ? "Detect automatically" : (all.first { $0.0 == code }?.1 ?? code)
    }

    static func regions(_ code: String) -> [String] { all.first { $0.0 == code }?.2 ?? [] }
}
