import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Dictionary

struct DictionaryPane: View {
    @ObservedObject var ui: SettingsUI
    @ObservedObject var vocab = VocabularyStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Dictionary",
                      subtitle: "Words, names and terms Halo should always get right. Stored in dictionary.json on this Mac.")

            if let e = vocab.loadError { ProblemBanner(message: e).padding(.bottom, 12) }

            if !vocab.suggestions.isEmpty {
                Block(title: "Learned suggestions",
                      note: "Words you corrected after Halo typed them. Nothing is added until you "
                          + "accept it.") {
                    ForEach(vocab.suggestions) { s in
                        HStack(spacing: 10) {
                            Text("“\(s.heard)”").foregroundStyle(.secondary)
                            Image(systemName: "arrow.right").font(.system(size: 10))
                            Text(s.correct).font(.system(size: 12, weight: .semibold))
                            Text(s.kind == "case" ? "capitalisation" : "\(Int(s.confidence * 100))%"
                                 + (s.count > 1 ? " · seen \(s.count)×" : ""))
                                .font(.system(size: 10)).foregroundStyle(.secondary)
                            Spacer()
                            Button("Add") { vocab.accept(s) }.controlSize(.small)
                            Button("Dismiss") { vocab.dismiss(s) }.controlSize(.small)
                        }
                    }
                }
            }

            HStack(spacing: 8) {
                TextField("Search", text: $ui.dictQuery)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 220)
                Spacer()
                Button {
                    vocab.entries.append(VocabularyStore.Entry(term: "", variants: []))
                    ui.editingEntry = vocab.entries.last?.id
                    ui.dictQuery = ""
                } label: { Label("Add", systemImage: "plus") }
                Button("Import…") { importFile() }
                Button("Export…") { exportFile() }
            }
            .padding(.bottom, 8)
            if let m = vocab.message { Note(text: m).padding(.bottom, 6) }

            VStack(spacing: 4) {
                ForEach(vocab.filtered(ui.dictQuery), id: \.self) { i in
                    EntryRow(vocab: vocab, ui: ui, index: i)
                }
            }
            HStack {
                Text("\(vocab.entries.count) entr\(vocab.entries.count == 1 ? "y" : "ies")")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                Spacer()
                Button("Save") { vocab.save() }.keyboardShortcut("s")
            }
            .padding(.vertical, 10)

            Block(title: "Catch near misses",
                  note: "Also corrects words that merely sound close to one of your terms. Three "
                      + "separate vetoes keep it off ordinary English.") {
                Toggle("Fuzzy matching", isOn: Binding(
                    get: { vocab.fuzzyEnabled }, set: { vocab.fuzzyEnabled = $0; vocab.save() }))
                HStack {
                    Text("Only when at least")
                    Slider(value: Binding(get: { vocab.fuzzyThreshold },
                                          set: { vocab.fuzzyThreshold = $0; vocab.save() }),
                           in: 0.80...0.99).frame(width: 180)
                    Text(String(format: "%.0f%% similar", vocab.fuzzyThreshold * 100))
                        .font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                }
                .disabled(!vocab.fuzzyEnabled)
            }
        }
        .onAppear { vocab.load() }
    }

    private func importFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json, .commaSeparatedText]
        panel.message = "Import a dictionary (JSON or CSV). Entries are merged into yours."
        if panel.runModal() == .OK, let url = panel.url { vocab.importFile(url) }
    }

    private func exportFile() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json, .commaSeparatedText]
        panel.nameFieldStringValue = "halo-dictionary.json"
        if panel.runModal() == .OK, let url = panel.url { vocab.exportFile(url) }
    }
}

struct EntryRow: View {
    @ObservedObject var vocab: VocabularyStore
    @ObservedObject var ui: SettingsUI
    let index: Int

    private func bind<T>(_ key: WritableKeyPath<VocabularyStore.Entry, T>) -> Binding<T> {
        Binding(get: { vocab.entries[index][keyPath: key] },
                set: { vocab.entries[index][keyPath: key] = $0 })
    }

    var body: some View {
        // The array can shrink between a delete and the next render pass.
        if index < vocab.entries.count {
            let e = vocab.entries[index]
            let editing = ui.editingEntry == e.id
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Text(e.term.isEmpty ? "New entry" : e.term)
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 150, alignment: .leading)
                    Text(e.variants.isEmpty ? "—" : e.variants.joined(separator: ", "))
                        .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                    Spacer()
                    if !e.type.isEmpty {
                        Text(e.type).font(.system(size: 10))
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(Color.primary.opacity(0.08)))
                    }
                    Text(e.scopeLabel).font(.system(size: 10)).foregroundStyle(.secondary)
                    Button(editing ? "Done" : "Edit") {
                        if editing { vocab.save() }
                        ui.editingEntry = editing ? nil : e.id
                    }
                    .controlSize(.small)
                    Button { vocab.entries.remove(at: index); vocab.save() } label: {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.borderless).foregroundStyle(.secondary)
                }
                if editing {
                    Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 6) {
                        GridRow {
                            Text("Written as").font(.system(size: 11))
                            TextField("Supabase", text: bind(\.term)).textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("Heard as").font(.system(size: 11))
                            TextField("super base, soup a base (comma separated)",
                                      text: bind(\.variantText)).textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("Type").font(.system(size: 11))
                            Picker("", selection: bind(\.type)) {
                                Text("—").tag("")
                                ForEach(VocabularyStore.types, id: \.self) { Text($0.capitalized).tag($0) }
                            }
                            .labelsHidden().frame(width: 160)
                        }
                        GridRow {
                            Text("Sounds like").font(.system(size: 11))
                            TextField("soo-puh-base (optional)", text: bind(\.hint))
                                .textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("Only in apps").font(.system(size: 11))
                            TextField("bundle ids, comma separated (empty: everywhere)",
                                      text: bind(\.appsText)).textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("Only in languages").font(.system(size: 11))
                            TextField("en, es (empty: all)", text: bind(\.languagesText))
                                .textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("")
                            Toggle("Also fix its capitalisation when spelled right",
                                   isOn: bind(\.matchCase))
                        }
                    }
                    .onSubmit { vocab.save() }
                }
            }
            .padding(8)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(editing ? Color.accentColor.opacity(0.06) : Color.primary.opacity(0.035)))
        }
    }
}

// MARK: - Commands & Transforms

struct CommandsPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var transforms = TransformsStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Commands & Transforms",
                      subtitle: "Command Mode turns speech into an edit of the selected text. Edits run on this Mac; nothing is replaced until the result is ready, and “scratch that” undoes it.")

            Block(title: "Command Mode",
                  note: "With nothing selected, a command acts on what Halo just typed. The orb "
                      + "turns violet so an instruction is never mistaken for dictation.") {
                Toggle("Enable Command Mode", isOn: $store.commandModeEnabled)
                Picker("Start it with", selection: Binding(
                    get: { store.commandHotkey.isEmpty ? "shift" : "key" },
                    set: { v in
                        store.commandTrigger = v == "shift" ? "shift" : "key"
                        if v == "shift" { store.commandHotkey = "" }
                        else if store.commandHotkey.isEmpty { store.commandHotkey = "f10" }
                    })) {
                    Text("Shift + \(store.hotkey.uppercased())").tag("shift")
                    Text("Its own key").tag("key")
                }
                .pickerStyle(.radioGroup)
                .disabled(!store.commandModeEnabled)
                if !store.commandHotkey.isEmpty {
                    Picker("Command key", selection: $store.commandHotkey) {
                        ForEach(Hotkeys.all.filter { $0 != store.hotkey }, id: \.self) {
                            Text($0.uppercased()).tag($0)
                        }
                    }
                    .frame(width: 240)
                }
            }

            Block(title: "Things you can say") {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(["Make this shorter.", "Fix the grammar.", "Turn this into bullet points.",
                             "Make this more professional.", "Rewrite this casually.",
                             "Delete the last sentence.", "Replace John with Sarah.",
                             "Summarize this.", "Capitalize this.",
                             "Run <custom transform name>."], id: \.self) {
                        Text("“\($0)”").font(.system(size: 11.5))
                    }
                }
                Text("Deleting, replacing and capitalising are exact rules. Rewrites need the local "
                     + "model (Settings › Models). Commands can only change text — never run programs "
                     + "or touch other apps.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Block(title: "Custom transforms",
                  note: "Also in the menu bar's Transform Selection menu.") {
                ForEach(transforms.custom) { t in
                    TransformRow(transforms: transforms, ui: ui, transform: t)
                }
                HStack {
                    Button("New transform") { ui.editingTransform = transforms.create().id }
                    Menu("Duplicate a built-in") {
                        ForEach(TransformsStore.builtins) { b in
                            Button(b.name) { ui.editingTransform = transforms.create(from: b).id }
                        }
                    }
                    .frame(width: 180)
                }
            }

            Block(title: "Built-in transforms") {
                ForEach(TransformsStore.builtins) { t in
                    HStack(alignment: .top) {
                        Text(t.name).font(.system(size: 12, weight: .medium))
                            .frame(width: 140, alignment: .leading)
                        Text(t.instructions).font(.system(size: 11)).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .onAppear { transforms.load() }
    }
}

struct TransformRow: View {
    @ObservedObject var transforms: TransformsStore
    @ObservedObject var ui: SettingsUI
    let transform: TransformsStore.Transform

    private var editing: Bool { ui.editingTransform == transform.id }

    private func binding(_ key: WritableKeyPath<TransformsStore.Transform, String>) -> Binding<String> {
        Binding(get: { (transforms.custom.first { $0.id == transform.id } ?? transform)[keyPath: key] },
                set: { v in
                    guard var t = transforms.custom.first(where: { $0.id == transform.id }) else { return }
                    t[keyPath: key] = v
                    transforms.update(t)
                })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(transform.name).font(.system(size: 12, weight: .medium))
                Spacer()
                Button(editing ? "Done" : "Edit") { ui.editingTransform = editing ? nil : transform.id }
                    .controlSize(.small)
                Button("Duplicate") { ui.editingTransform = transforms.create(from: transform).id }
                    .controlSize(.small)
                Button("Delete", role: .destructive) { transforms.delete(transform.id) }
                    .controlSize(.small)
            }
            if editing {
                TextField("Name (what you say after “run”)", text: binding(\.name))
                    .textFieldStyle(.roundedBorder).frame(width: 320)
                TextEditor(text: binding(\.instructions))
                    .font(.system(size: 12)).frame(height: 70)
                    .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color.primary.opacity(0.15)))
            } else {
                Text(transform.instructions).font(.system(size: 11)).foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))
    }
}

// MARK: - Models

struct ModelsPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var models = ModelsStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Models",
                      subtitle: "Downloaded to this Mac, checked against a published checksum before they can be used.")

            if let m = models.message { Note(text: m, failed: models.failed).padding(.bottom, 10) }

            Block(title: "Speech models (whisper)",
                  note: "English uses the .en model; other languages need a multilingual one.") {
                if !models.loaded { ProgressView().controlSize(.small) }
                ForEach(models.speech) { m in ModelRow(models: models, model: m) }
            }

            Block(title: "Cleanup models (optional)",
                  note: "Runs with llama.cpp on your GPU, only in Normal and Polished modes, and "
                      + "only if it answers in time. Unloaded after 30 idle minutes.") {
                ForEach(models.cleanup) { m in ModelRow(models: models, model: m) }
            }

            Block(title: "Storage") {
                HStack {
                    Text("\(ModelsStore.human(models.diskUsed)) used by models in Halo's folder"
                         + (models.ramGB > 0 ? " · this Mac has \(Int(models.ramGB)) GB of memory" : ""))
                        .font(.system(size: 12))
                    Spacer()
                    Button("Reveal") {
                        NSWorkspace.shared.activateFileViewerSelecting([HaloPaths.modelsDir])
                    }
                    .controlSize(.small)
                }
            }
        }
        .onAppear { models.refresh() }
    }
}

struct ModelRow: View {
    @ObservedObject var models: ModelsStore
    let model: ModelsStore.Model

    private func stars(_ n: Int) -> String { String(repeating: "●", count: n) + String(repeating: "○", count: max(0, 5 - n)) }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(model.id).font(.system(size: 12.5, weight: .semibold))
                    if model.selected {
                        Text("In use").font(.system(size: 9, weight: .bold)).foregroundStyle(.white)
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(Color.accentColor))
                    }
                    if model.recommended {
                        Text("Recommended for this Mac").font(.system(size: 9)).foregroundStyle(.secondary)
                    }
                }
                Text(model.note).font(.system(size: 11)).foregroundStyle(.secondary)
                Text("\(model.sizeText) · quality \(stars(model.quality)) · speed \(stars(model.speed))"
                     + (model.languages.isEmpty ? "" : " · \(model.languages)")
                     + " · \(model.hardware)")
                    .font(.system(size: 10.5)).foregroundStyle(.secondary)
                Text(status).font(.system(size: 10.5))
                    .foregroundStyle(model.damaged || model.verified == false ? .orange : .secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                if models.downloading == model.id {
                    ProgressView(value: models.progress).frame(width: 110)
                    Button("Cancel") { models.cancelDownload() }.controlSize(.small)
                } else if model.installed {
                    if !model.selected {
                        Button("Use") { models.select(model) }.controlSize(.small)
                    }
                    HStack(spacing: 4) {
                        Button(models.verifying == model.id ? "Verifying…" : "Verify") { models.verify(model) }
                            .controlSize(.small).disabled(models.verifying != nil)
                        if !model.legacy {
                            Button("Delete", role: .destructive) { models.delete(model) }
                                .controlSize(.small).disabled(model.selected)
                        }
                    }
                } else {
                    Button(model.partial > 0 ? "Resume download" : "Download") { models.download(model) }
                        .controlSize(.small).disabled(models.downloading != nil)
                    if model.selected {
                        Text("Selected but missing").font(.system(size: 10)).foregroundStyle(.orange)
                    }
                }
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))
    }

    private var status: String {
        if models.downloading == model.id {
            return String(format: "Downloading… %.0f%%", models.progress * 100)
        }
        if model.damaged { return "Incomplete or damaged — download it again." }
        guard model.installed else {
            return model.partial > 0 ? "Partly downloaded (\(ModelsStore.human(model.partial)))."
                                     : "Not downloaded."
        }
        var s = model.legacy ? "Installed (in ~/whisper.cpp)" : "Installed"
        switch model.verified {
        case .some(true): s += " · checksum verified"
        case .some(false): s += " · checksum FAILED — delete and download again"
        case .none: s += " · not verified yet"
        }
        if model.kind == .cleanup && model.selected && !models.cleanupState.isEmpty {
            s += " · \(models.cleanupState)"
        }
        return s
    }
}
