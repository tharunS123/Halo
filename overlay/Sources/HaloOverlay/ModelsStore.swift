import Foundation

/// Speech and cleanup models, as the Models pane (and onboarding) sees them.
///
/// The catalog -- sizes, checksums, quality and speed, what is installed and
/// verified -- comes from `halo model catalog --json`, so models.py stays the
/// one source of truth. Downloads, verification and removal run the same
/// CLI commands a Terminal user would, with progress read from the .part
/// file's size. The engine checks the checksum before a download is renamed
/// into place, so an interrupted or corrupted file can never be selected.
@MainActor
final class ModelsStore: ObservableObject {
    static let shared = ModelsStore()

    enum Kind { case speech, cleanup }

    struct Model: Identifiable, Equatable {
        let id: String
        let kind: Kind
        let file: String
        let size: Int64
        var installed: Bool
        var disk: Int64
        var partial: Int64
        var verified: Bool?
        var damaged: Bool
        let quality: Int
        let speed: Int
        let hardware: String
        let languages: String
        let note: String
        let recommended: Bool
        var selected: Bool
        let legacy: Bool

        var sizeText: String { ModelsStore.human(size) }
    }

    @Published var speech: [Model] = []
    @Published var cleanup: [Model] = []
    @Published var diskUsed: Int64 = 0
    @Published var ramGB: Double = 0
    @Published var loaded = false
    @Published var downloading: String?
    @Published var progress: Double = 0
    @Published var verifying: String?
    @Published var message: String?
    @Published var failed = false
    /// The cleanup model's live state from local_model.json.
    @Published var cleanupState = ""
    @Published var cleanupDetail = ""

    private var process: Process?
    private var poll: Timer?
    private var selectAfter: (Kind, String)?

    nonisolated static func human(_ bytes: Int64) -> String {
        let mb = Double(bytes) / 1_000_000
        return mb >= 1000 ? String(format: "%.1f GB", mb / 1000) : String(format: "%.0f MB", mb)
    }

    func refresh() {
        readCleanupStatus()
        HaloCLI.run(["model", "catalog", "--json"]) { [weak self] status, out in
            guard let self, status == 0, let data = out.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return }
            self.speech = (obj["speech"] as? [[String: Any]] ?? []).map { Self.model($0, .speech) }
            self.cleanup = (obj["cleanup"] as? [[String: Any]] ?? []).map { Self.model($0, .cleanup) }
            self.diskUsed = (obj["disk_used"] as? NSNumber)?.int64Value ?? 0
            self.ramGB = (obj["ram_gb"] as? NSNumber)?.doubleValue ?? 0
            self.loaded = true
        }
    }

    private static func model(_ d: [String: Any], _ kind: Kind) -> Model {
        func i64(_ k: String) -> Int64 { (d[k] as? NSNumber)?.int64Value ?? 0 }
        func int(_ k: String) -> Int { (d[k] as? NSNumber)?.intValue ?? 0 }
        return Model(id: d["id"] as? String ?? "", kind: kind, file: d["file"] as? String ?? "",
                     size: i64("size"), installed: d["installed"] as? Bool ?? false,
                     disk: i64("disk"), partial: i64("partial"),
                     verified: d["verified"] as? Bool, damaged: d["damaged"] as? Bool ?? false,
                     quality: int("quality"), speed: int("speed"),
                     hardware: d["hardware"] as? String ?? "",
                     languages: d["languages"] as? String ?? "", note: d["note"] as? String ?? "",
                     recommended: d["recommended"] as? Bool ?? false,
                     selected: d["selected"] as? Bool ?? false, legacy: d["legacy"] as? Bool ?? false)
    }

    func readCleanupStatus() {
        let obj = JSONFile.object(HaloPaths.localModelStatus)
        cleanupState = obj["state"] as? String ?? ""
        cleanupDetail = obj["detail"] as? String ?? ""
    }

    private func args(_ m: Model, _ verb: String) -> [String] {
        m.kind == .speech ? ["model", verb == "install" ? "download" : verb, m.id]
                          : ["model", "local", verb, m.id]
    }

    /// Selecting a model that is not downloaded downloads it first: the
    /// setting only changes once a verified file is in place, so the engine
    /// is never pointed at something missing.
    func select(_ m: Model) {
        guard m.installed else {
            selectAfter = (m.kind, m.id)
            download(m)
            return
        }
        apply(m.kind, m.id)
    }

    private func apply(_ kind: Kind, _ id: String) {
        let store = SettingsStore.shared
        if kind == .speech { store.model = id } else { store.localModel = id }
        report("\(id) is now in use.", failed: false)
        refresh()
    }

    func download(_ m: Model) {
        guard downloading == nil, let p = HaloCLI.command(args(m, "install")) else {
            if downloading == nil { report("Could not find Halo's engine.", failed: true) }
            return
        }
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        p.terminationHandler = { [weak self] proc in
            let status = proc.terminationStatus
            Task { @MainActor in self?.finished(m, status: status) }
        }
        do { try p.run() } catch {
            report("Could not start the download.", failed: true)
            return
        }
        process = p
        downloading = m.id
        progress = 0
        message = nil
        poll?.invalidate()
        poll = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick(m) }
        }
    }

    private func tick(_ m: Model) {
        let part = HaloPaths.modelsDir.appendingPathComponent(m.file + ".part")
        let done = (try? FileManager.default.attributesOfItem(atPath: part.path)[.size]
                    as? NSNumber)?.int64Value ?? 0
        progress = m.size > 0 ? min(1, Double(done) / Double(m.size)) : 0
    }

    func cancelDownload() {
        selectAfter = nil
        process?.terminate()
    }

    private func finished(_ m: Model, status: Int32) {
        poll?.invalidate()
        poll = nil
        process = nil
        downloading = nil
        if status == 0 {
            report("\(m.id) downloaded and its checksum verified.", failed: false)
            if let (kind, id) = selectAfter, id == m.id { apply(kind, id) }
        } else if status == 15 {
            report("Download stopped. Start it again to resume where it left off.", failed: true)
        } else {
            report("The download did not finish. Try again; it resumes where it stopped.",
                   failed: true)
        }
        selectAfter = nil
        refresh()
    }

    func verify(_ m: Model) {
        verifying = m.id
        HaloCLI.run(args(m, "verify")) { [weak self] status, _ in
            self?.verifying = nil
            self?.report(status == 0 ? "\(m.id): checksum OK."
                                     : "\(m.id) is damaged. Delete it and download again.",
                         failed: status != 0)
            self?.refresh()
        }
    }

    func delete(_ m: Model) {
        if m.selected {
            report("Choose another model before deleting the one in use.", failed: true)
            return
        }
        HaloCLI.run(args(m, "remove")) { [weak self] _, _ in
            self?.report("\(m.id) deleted.", failed: false)
            self?.refresh()
        }
    }

    private func report(_ text: String, failed: Bool) {
        message = text
        self.failed = failed
    }
}
