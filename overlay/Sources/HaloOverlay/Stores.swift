import AppKit
import Foundation
import SQLite3

// MARK: - Styles

/// styles.json: custom styles, category defaults, per-app assignments.
/// Built-ins are mirrored here only for display; styles.py is the truth.
@MainActor
final class StylesStore: ObservableObject {
    static let shared = StylesStore()

    struct Style: Identifiable, Equatable {
        var id: String
        var name: String
        var instructions: String
        var base: String
        var builtin: Bool
    }

    static let builtins: [Style] = [
        Style(id: "neutral", name: "Neutral", instructions: "Keep the speaker's own tone.", base: "", builtin: true),
        Style(id: "casual", name: "Casual", instructions: "Relaxed and friendly. No closing full stop on short messages.", base: "", builtin: true),
        Style(id: "very_casual", name: "Very Casual", instructions: "Texting style: lowercase is fine, no closing full stop.", base: "", builtin: true),
        Style(id: "professional", name: "Professional", instructions: "Clear, polite and professional. Complete sentences.", base: "", builtin: true),
        Style(id: "formal", name: "Formal", instructions: "Formal and precise. No contractions or slang.", base: "", builtin: true),
        Style(id: "concise", name: "Concise", instructions: "As short as possible while keeping every point.", base: "", builtin: true),
        Style(id: "excited", name: "Excited", instructions: "Upbeat. An exclamation mark where it fits.", base: "", builtin: true),
        Style(id: "coding", name: "Coding / AI Prompt", instructions: "Keep identifiers, file names, flags and commands exact.", base: "", builtin: true),
    ]

    static let categories: [(String, String, String)] = [
        ("personal_messaging", "Personal Messaging", "Messages, WhatsApp, Telegram, Signal, Discord"),
        ("work_messaging", "Work Messaging", "Slack, Teams, Zoom chat"),
        ("email", "Email", "Mail, Outlook, Gmail"),
        ("documents", "Documents", "Notes, Pages, Word, Google Docs, Notion"),
        ("coding", "Coding / AI Prompts", "Xcode, Cursor, VS Code, terminals, ChatGPT, Claude"),
        ("other", "Other", "Everything else"),
    ]

    static let defaults: [String: String] = [
        "personal_messaging": "casual", "work_messaging": "concise", "email": "professional",
        "documents": "neutral", "coding": "coding", "other": "neutral",
    ]

    @Published var custom: [Style] = []
    @Published var categories: [String: String] = StylesStore.defaults
    @Published var apps: [String: String] = [:]
    @Published private(set) var loadError: String?

    private var root: [String: Any] = [:]

    var all: [Style] { Self.builtins + custom }

    func name(of id: String) -> String { all.first { $0.id == id }?.name ?? id }

    func load() {
        loadError = nil
        switch JSONFile.read(HaloPaths.styles) {
        case .missing: root = [:]
        case .ok(let o): root = o
        case .malformed(let why):
            root = [:]
            loadError = "styles.json could not be read: \(why)"
        }
        custom = (root["custom"] as? [[String: Any]] ?? []).compactMap { d in
            guard let id = d["id"] as? String, let name = d["name"] as? String else { return nil }
            return Style(id: id, name: name, instructions: d["instructions"] as? String ?? "",
                         base: d["base"] as? String ?? "neutral", builtin: false)
        }
        var cats = Self.defaults
        for (k, v) in root["categories"] as? [String: String] ?? [:] { cats[k] = v }
        categories = cats
        apps = root["apps"] as? [String: String] ?? [:]
    }

    func save() {
        guard loadError == nil else { return }
        var r = root
        if case .ok(let current) = JSONFile.read(HaloPaths.styles) { r = current }
        r["custom"] = custom.map { ["id": $0.id, "name": $0.name, "base": $0.base,
                                    "instructions": $0.instructions] }
        r["categories"] = categories
        r["apps"] = apps
        root = r
        JSONFile.write(r, to: HaloPaths.styles)
    }

    func create(from base: Style? = nil) -> Style {
        let id = "custom-\(UUID().uuidString.prefix(8).lowercased())"
        let s = Style(id: id, name: base.map { "\($0.name) copy" } ?? "My style",
                      instructions: base?.instructions ?? "",
                      base: base.map { $0.builtin ? $0.id : $0.base } ?? "neutral", builtin: false)
        custom.append(s)
        save()
        return s
    }

    func update(_ s: Style) {
        if let i = custom.firstIndex(where: { $0.id == s.id }) { custom[i] = s; save() }
    }

    func delete(_ id: String) {
        custom.removeAll { $0.id == id }
        // Anything pointing at it falls back to its category's default.
        for (k, v) in categories where v == id { categories[k] = Self.defaults[k] ?? "neutral" }
        apps = apps.filter { $0.value != id }
        save()
    }
}

// MARK: - Transforms

@MainActor
final class TransformsStore: ObservableObject {
    static let shared = TransformsStore()

    struct Transform: Identifiable, Equatable {
        var id: String
        var name: String
        var instructions: String
        var builtin: Bool
    }

    static let builtins: [Transform] = [
        ("polish", "Polish", "Improve clarity and flow. Keep the meaning, the facts and the tone."),
        ("shorten", "Shorten", "Make it noticeably shorter while keeping every key point."),
        ("expand", "Expand", "Expand it into fuller sentences, explaining what is already there."),
        ("fix_grammar", "Fix Grammar", "Fix grammar, spelling and punctuation only."),
        ("professional", "Make Professional", "Rewrite it to sound professional and polite."),
        ("casual", "Make Casual", "Rewrite it to sound casual and friendly."),
        ("bulletize", "Bulletize", "Turn it into a concise bullet list."),
        ("summarize", "Summarize", "Summarize it in one to three sentences."),
        ("improve_prompt", "Improve Prompt", "Rewrite it as a clear prompt for an AI assistant."),
    ].map { Transform(id: $0.0, name: $0.1, instructions: $0.2, builtin: true) }

    @Published var custom: [Transform] = []
    private var root: [String: Any] = [:]

    var all: [Transform] { Self.builtins + custom }

    func load() {
        root = JSONFile.object(HaloPaths.transforms)
        custom = (root["custom"] as? [[String: Any]] ?? []).compactMap { d in
            guard let id = d["id"] as? String, let name = d["name"] as? String else { return nil }
            return Transform(id: id, name: name, instructions: d["instructions"] as? String ?? "",
                             builtin: false)
        }
    }

    func save() {
        var r = root
        if case .ok(let current) = JSONFile.read(HaloPaths.transforms) { r = current }
        r["custom"] = custom.map { ["id": $0.id, "name": $0.name, "instructions": $0.instructions] }
        root = r
        JSONFile.write(r, to: HaloPaths.transforms)
    }

    func create(from base: Transform? = nil) -> Transform {
        let t = Transform(id: "custom-\(UUID().uuidString.prefix(8).lowercased())",
                          name: base.map { "\($0.name) copy" } ?? "My transform",
                          instructions: base?.instructions ?? "", builtin: false)
        custom.append(t)
        save()
        return t
    }

    func update(_ t: Transform) {
        if let i = custom.firstIndex(where: { $0.id == t.id }) { custom[i] = t; save() }
    }

    func delete(_ id: String) {
        custom.removeAll { $0.id == id }
        save()
    }
}

// MARK: - Vocabulary

/// dictionary.json and the learned suggestions. Keeps every field an entry
/// has, including ones this window does not show, so a save never strips
/// what `halo dictionary import` or a text editor put there.
@MainActor
final class VocabularyStore: ObservableObject {
    static let shared = VocabularyStore()

    static let types = ["word", "name", "company", "acronym", "technical", "phrase"]

    struct Entry: Identifiable, Equatable {
        let id = UUID()
        var term: String
        var variants: [String]
        var type: String = ""
        var hint: String = ""
        var apps: [String] = []
        var languages: [String] = []
        var matchCase: Bool = true
        var extra: [String: String] = [:]   // unknown string fields, kept as-is

        var variantText: String {
            get { variants.joined(separator: ", ") }
            set { variants = Self.split(newValue) }
        }
        var appsText: String {
            get { apps.joined(separator: ", ") }
            set { apps = Self.split(newValue) }
        }
        var languagesText: String {
            get { languages.joined(separator: ", ") }
            set { languages = Self.split(newValue) }
        }
        static func split(_ s: String) -> [String] {
            s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        }
        var scopeLabel: String {
            var bits: [String] = []
            if !apps.isEmpty { bits.append(apps.count == 1 ? "1 app" : "\(apps.count) apps") }
            if !languages.isEmpty { bits.append(languages.joined(separator: "/")) }
            return bits.isEmpty ? "Global" : bits.joined(separator: ", ")
        }
    }

    struct Suggestion: Identifiable {
        var id: String { heard.lowercased() + "\u{2192}" + correct }
        var heard: String
        var correct: String
        var confidence: Double
        var count: Int
        var kind: String
    }

    @Published var entries: [Entry] = []
    @Published var fuzzyEnabled = true
    @Published var fuzzyThreshold = 0.90
    @Published var suggestions: [Suggestion] = []
    @Published private(set) var loadError: String?
    @Published var message: String?

    private var root: [String: Any] = [:]

    func load() {
        loadError = nil
        switch JSONFile.read(HaloPaths.dictionary) {
        case .missing: root = [:]
        case .ok(let o): root = o
        case .malformed(let why):
            root = [:]
            loadError = "dictionary.json could not be read: \(why)"
        }
        entries = (root["terms"] as? [[String: Any]] ?? []).compactMap(Self.entry)
        let fuzzy = root["fuzzy"] as? [String: Any] ?? [:]
        fuzzyEnabled = fuzzy["enabled"] as? Bool ?? true
        fuzzyThreshold = (fuzzy["threshold"] as? NSNumber)?.doubleValue ?? 0.90
        loadSuggestions()
    }

    static func entry(_ d: [String: Any]) -> Entry? {
        guard let term = d["term"] as? String, !term.isEmpty else { return nil }
        var e = Entry(term: term, variants: d["variants"] as? [String] ?? [])
        e.type = d["type"] as? String ?? ""
        e.hint = d["hint"] as? String ?? ""
        e.apps = d["apps"] as? [String] ?? []
        e.languages = d["languages"] as? [String] ?? []
        e.matchCase = d["match_case"] as? Bool ?? true
        let known: Set = ["term", "variants", "type", "hint", "apps", "languages", "match_case"]
        for (k, v) in d where !known.contains(k) { if let s = v as? String { e.extra[k] = s } }
        return e
    }

    static func dict(_ e: Entry) -> [String: Any] {
        var d: [String: Any] = ["term": e.term.trimmingCharacters(in: .whitespaces),
                                "variants": e.variants]
        if !e.type.isEmpty { d["type"] = e.type }
        if !e.hint.isEmpty { d["hint"] = e.hint }
        if !e.apps.isEmpty { d["apps"] = e.apps }
        if !e.languages.isEmpty { d["languages"] = e.languages }
        if !e.matchCase { d["match_case"] = false }
        for (k, v) in e.extra { d[k] = v }
        return d
    }

    func save() {
        guard loadError == nil else { return }
        var r = root
        if case .ok(let current) = JSONFile.read(HaloPaths.dictionary) { r = current }
        r["terms"] = entries.filter { !$0.term.trimmingCharacters(in: .whitespaces).isEmpty }
            .map(Self.dict)
        var fuzzy = r["fuzzy"] as? [String: Any] ?? [:]
        fuzzy["enabled"] = fuzzyEnabled
        fuzzy["threshold"] = (fuzzyThreshold * 100).rounded() / 100
        r["fuzzy"] = fuzzy
        root = r
        JSONFile.write(r, to: HaloPaths.dictionary)
    }

    func filtered(_ query: String) -> [Int] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        return entries.indices.filter { i in
            q.isEmpty || entries[i].term.lowercased().contains(q)
                || entries[i].variants.contains { $0.lowercased().contains(q) }
                || entries[i].type.lowercased().contains(q)
        }
    }

    // MARK: suggestions (suggestions.json, written by learning.py)

    func loadSuggestions() {
        let items = JSONFile.object(HaloPaths.suggestions)["suggestions"] as? [[String: Any]] ?? []
        suggestions = items.compactMap { d in
            guard d["status"] as? String == "pending",
                  let heard = d["heard"] as? String, let correct = d["correct"] as? String,
                  let conf = (d["confidence"] as? NSNumber)?.doubleValue, conf >= 0.7
            else { return nil }
            return Suggestion(heard: heard, correct: correct, confidence: conf,
                              count: (d["count"] as? NSNumber)?.intValue ?? 1,
                              kind: d["kind"] as? String ?? "spelling")
        }.sorted { $0.confidence > $1.confidence }
    }

    private func setStatus(_ s: Suggestion, _ status: String) {
        var root = JSONFile.object(HaloPaths.suggestions)
        var items = root["suggestions"] as? [[String: Any]] ?? []
        for i in items.indices {
            if (items[i]["heard"] as? String)?.lowercased() == s.heard.lowercased(),
               items[i]["correct"] as? String == s.correct {
                items[i]["status"] = status
            }
        }
        root["suggestions"] = items
        JSONFile.write(root, to: HaloPaths.suggestions)
        loadSuggestions()
    }

    /// Accept: `correct` becomes a term (or gains `heard` as a variant).
    func accept(_ s: Suggestion) {
        if let i = entries.firstIndex(where: { $0.term == s.correct }) {
            if s.heard.lowercased() != s.correct.lowercased(),
               !entries[i].variants.contains(where: { $0.lowercased() == s.heard.lowercased() }) {
                entries[i].variants.append(s.heard)
            }
        } else {
            var e = Entry(term: s.correct,
                          variants: s.heard.lowercased() == s.correct.lowercased() ? [] : [s.heard])
            e.type = s.correct.contains(" ") ? "phrase" : ""
            entries.append(e)
        }
        save()
        setStatus(s, "accepted")
    }

    func dismiss(_ s: Suggestion) { setStatus(s, "dismissed") }

    // MARK: import / export through the CLI (one parser, in dictionary.py)

    func importFile(_ url: URL) {
        save()
        HaloCLI.run(["dictionary", "import", url.path]) { [weak self] status, out in
            self?.load()
            self?.message = status == 0
                ? out.trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "OK", with: "").trimmingCharacters(in: .whitespaces)
                : "Could not import that file."
        }
    }

    func exportFile(_ url: URL) {
        save()
        let fmt = url.pathExtension.lowercased() == "csv" ? "csv" : "json"
        HaloCLI.run(["dictionary", "export", url.path, "--format", fmt]) { [weak self] status, _ in
            self?.message = status == 0 ? "Exported \(self?.entries.count ?? 0) entries."
                                        : "Could not export."
        }
    }
}

// MARK: - History

/// The opt-in history database, read directly (it is a plain SQLite file the
/// engine writes). Reinsert and the retries go through the engine, which
/// owns typing, whisper and the model.
@MainActor
final class HistoryStore: ObservableObject {
    static let shared = HistoryStore()

    struct Item: Identifiable, Equatable {
        let id: String
        let created: Date
        let duration: Double
        let app: String
        let language: String
        let raw: String
        let cleaned: String
        let mode: String
        let status: String
        let reason: String
        let hasAudio: Bool
    }

    @Published var items: [Item] = []
    @Published var query = ""
    @Published var selected: String?
    @Published var busy = false
    @Published var message: String?

    func load() {
        items = Self.fetch(query)
        if let s = selected, !items.contains(where: { $0.id == s }) { selected = nil }
    }

    private static func fetch(_ query: String) -> [Item] {
        let path = HaloPaths.history.path
        guard FileManager.default.fileExists(atPath: path) else { return [] }
        var db: OpaquePointer?
        guard sqlite3_open_v2(path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            sqlite3_close(db)
            return []
        }
        defer { sqlite3_close(db) }
        let q = query.trimmingCharacters(in: .whitespaces)
        let sql = q.isEmpty
            ? "SELECT id, created, duration, app_name, language, raw, cleaned, mode, status, reason, audio FROM dictations ORDER BY created DESC LIMIT 500"
            : "SELECT id, created, duration, app_name, language, raw, cleaned, mode, status, reason, audio FROM dictations WHERE raw LIKE ?1 OR cleaned LIKE ?1 OR app_name LIKE ?1 ORDER BY created DESC LIMIT 500"
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }
        let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        if !q.isEmpty { sqlite3_bind_text(stmt, 1, "%\(q)%", -1, transient) }
        func text(_ i: Int32) -> String {
            sqlite3_column_text(stmt, i).map { String(cString: $0) } ?? ""
        }
        var out: [Item] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            out.append(Item(id: text(0),
                            created: Date(timeIntervalSince1970: sqlite3_column_double(stmt, 1)),
                            duration: sqlite3_column_double(stmt, 2), app: text(3), language: text(4),
                            raw: text(5), cleaned: text(6), mode: text(7), status: text(8),
                            reason: text(9), hasAudio: sqlite3_column_type(stmt, 10) != SQLITE_NULL))
        }
        return out
    }

    private func exec(_ sql: String, _ arg: String? = nil) {
        var db: OpaquePointer?
        guard sqlite3_open(HaloPaths.history.path, &db) == SQLITE_OK else { sqlite3_close(db); return }
        defer { sqlite3_close(db) }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        if let arg { sqlite3_bind_text(stmt, 1, arg, -1, transient) }
        sqlite3_step(stmt)
    }

    func delete(_ item: Item) {
        exec("DELETE FROM dictations WHERE id = ?1", item.id)
        try? FileManager.default.removeItem(
            at: HaloPaths.historyAudio.appendingPathComponent("\(item.id).wav"))
        load()
    }

    func clearAll() {
        for suffix in ["", "-wal", "-shm", "-journal"] {
            try? FileManager.default.removeItem(atPath: HaloPaths.history.path + suffix)
        }
        try? FileManager.default.removeItem(at: HaloPaths.historyAudio)
        selected = nil
        load()
        message = "History cleared."
    }

    func copy(_ item: Item) {
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(item.cleaned, forType: .string)
        message = "Copied."
    }

    /// Hide the window so the app underneath has focus again, then have the
    /// engine type it there -- through the same verified insertion as any
    /// dictation.
    func reinsert(_ item: Item) {
        SettingsWindowController.shared.hideForAction()
        busy = true
        EngineClient.request(["op": "history.reinsert", "id": item.id]) { [weak self] reply in
            self?.busy = false
            if reply?["ok"] as? Bool != true {
                self?.message = "Not inserted: \(reply?["reason"] as? String ?? "Halo is not running")."
                SettingsWindowController.shared.show()
            }
        }
    }

    func retry(_ item: Item, transcription: Bool) {
        busy = true
        message = transcription ? "Transcribing again…" : "Cleaning up again…"
        let op = transcription ? "history.retry_transcription" : "history.retry_cleanup"
        EngineClient.request(["op": op, "id": item.id], timeout: 180) { [weak self] reply in
            self?.busy = false
            if reply?["ok"] as? Bool == true {
                self?.message = "Updated."
            } else {
                self?.message = "Could not retry: \(reply?["reason"] as? String ?? reply?["error"] as? String ?? "Halo is not running")."
            }
            self?.load()
        }
    }
}
