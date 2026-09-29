import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Dictionary

struct DictionaryPane: View {
    @ObservedObject var ui: SettingsUI
    @ObservedObject var vocab = VocabularyStore.shared

    private func addEntry() {
        vocab.entries.append(VocabularyStore.Entry(term: "", variants: []))
        ui.editingEntry = vocab.entries.last?.id
        ui.dictQuery = ""
    }

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
                        ViewThatFits(in: .horizontal) {
                            HStack(spacing: 10) {
                                suggestionText(s)
                                Spacer(minLength: 8)
                                suggestionActions(s)
                            }
                            VStack(alignment: .leading, spacing: 6) {
                                suggestionText(s)
                                suggestionActions(s)
                            }
                        }
                    }
                }
            }

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    SearchField(placeholder: "Search words", text: $ui.dictQuery)
                        .frame(maxWidth: 240)
                    Spacer(minLength: 8)
                    toolbarButtons
                }
                VStack(alignment: .leading, spacing: 8) {
                    SearchField(placeholder: "Search words", text: $ui.dictQuery)
                    toolbarButtons
                }
            }
            .padding(.bottom, 10)
            if let m = vocab.message { Note(text: m).padding(.bottom, 8) }

            if vocab.entries.isEmpty {
                EmptyState(symbol: "character.book.closed", title: "No words yet",
                           message: "Add names, product terms and jargon, and Halo will spell them "
                               + "the way you do — even when they sound like something else.") {
                    Button { addEntry() } label: { Label("Add a word", systemImage: "plus") }
                        .buttonStyle(.haloPrimary)
                }
            } else {
                let shown = vocab.filtered(ui.dictQuery)
                if shown.isEmpty {
                    EmptyState(symbol: "magnifyingglass", title: "No matches",
                               message: "Nothing in your dictionary matches “\(ui.dictQuery)”.") {
                        Button("Clear search") { ui.dictQuery = "" }.buttonStyle(.haloSmall)
                    }
                }
                VStack(spacing: 6) {
                    ForEach(shown, id: \.self) { i in
                        EntryRow(vocab: vocab, ui: ui, index: i)
                    }
                }
            }
            HStack {
                Text("\(vocab.entries.count) entr\(vocab.entries.count == 1 ? "y" : "ies")")
                    .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                Spacer()
                Button("Save") { vocab.save() }
                    .buttonStyle(.haloSmall)
                    .keyboardShortcut("s")
            }
            .padding(.vertical, 12)

            Block(title: "Catch near misses",
                  note: "Also corrects words that merely sound close to one of your terms. Three "
                      + "separate vetoes keep it off ordinary English.") {
                ToggleRow(title: "Fuzzy matching", isOn: Binding(
                    get: { vocab.fuzzyEnabled }, set: { vocab.fuzzyEnabled = $0; vocab.save() }))
                SliderRow(title: "Only when at least",
                          value: Binding(get: { vocab.fuzzyThreshold },
                                         set: { vocab.fuzzyThreshold = $0; vocab.save() }),
                          range: 0.80...0.99,
                          display: String(format: "%.0f%%", vocab.fuzzyThreshold * 100))
                    .disabled(!vocab.fuzzyEnabled)
                    .opacity(vocab.fuzzyEnabled ? 1 : 0.5)
            }
        }
        .onAppear { vocab.load() }
    }

    private var toolbarButtons: some View {
        HStack(spacing: 8) {
            Button { addEntry() } label: { Label("Add", systemImage: "plus") }
                .buttonStyle(.haloSmallPrimary)
            Button("Import…") { importFile() }.buttonStyle(.haloSmall)
            Button("Export…") { exportFile() }.buttonStyle(.haloSmall)
        }
    }

    private func suggestionText(_ s: VocabularyStore.Suggestion) -> some View {
        HStack(spacing: 8) {
            Text("“\(s.heard)”").foregroundStyle(HaloColor.secondaryText)
            Image(systemName: "arrow.right").font(.system(size: 10))
                .foregroundStyle(HaloColor.secondaryText)
                .accessibilityLabel("becomes")
            Text(s.correct).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
            Text(s.kind == "case" ? "capitalisation" : "\(Int(s.confidence * 100))%"
                 + (s.count > 1 ? " · seen \(s.count)×" : ""))
                .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
        }
        .font(HaloType.control)
    }

    private func suggestionActions(_ s: VocabularyStore.Suggestion) -> some View {
        HStack(spacing: 6) {
            Button("Add") { vocab.accept(s) }.buttonStyle(.haloSmallPrimary)
            Button("Dismiss") { vocab.dismiss(s) }.buttonStyle(.haloSmall)
        }
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
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(e.term.isEmpty ? "New entry" : e.term)
                                .font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                            if !e.type.isEmpty {
                                Text(e.type).font(HaloType.body(11, .medium))
                                    .foregroundStyle(HaloColor.text)
                                    .padding(.horizontal, 7).padding(.vertical, 1)
                                    .background(Capsule().fill(HaloColor.selection))
                                    .overlay(Capsule().strokeBorder(HaloColor.subtleBorder, lineWidth: 1))
                            }
                            Text(e.scopeLabel).font(HaloType.support)
                                .foregroundStyle(HaloColor.secondaryText)
                        }
                        Text(e.variants.isEmpty ? "No “heard as” variants" : "Heard as: " + e.variants.joined(separator: ", "))
                            .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    Button(editing ? "Done" : "Edit") {
                        if editing { vocab.save() }
                        ui.editingEntry = editing ? nil : e.id
                    }
                    .buttonStyle(.haloSmall)
                    IconButton(symbol: "trash",
                               label: "Delete \(e.term.isEmpty ? "this entry" : e.term)",
                               role: .destructive) {
                        vocab.entries.remove(at: index); vocab.save()
                    }
                }
                if editing {
                    Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 10, verticalSpacing: 8) {
                        GridRow {
                            label("Written as")
                            VStack(alignment: .leading, spacing: 4) {
                                TextField("Supabase", text: bind(\.term)).textFieldStyle(.halo)
                                if e.term.trimmingCharacters(in: .whitespaces).isEmpty {
                                    Note(text: "Enter the word as it should be written.", failed: true)
                                }
                            }
                        }
                        GridRow {
                            label("Heard as")
                            TextField("super base, soup a base (comma separated)",
                                      text: bind(\.variantText)).textFieldStyle(.halo)
                        }
                        GridRow {
                            label("Type")
                            Picker("Type", selection: bind(\.type)) {
                                Text("—").tag("")
                                ForEach(VocabularyStore.types, id: \.self) { Text($0.capitalized).tag($0) }
                            }
                            .labelsHidden().frame(width: 160)
                            .gridColumnAlignment(.leading)
                        }
                        GridRow {
                            label("Sounds like")
                            TextField("soo-puh-base (optional)", text: bind(\.hint))
                                .textFieldStyle(.halo)
                        }
                        GridRow {
                            label("Only in apps")
                            TextField("bundle ids, comma separated (empty: everywhere)",
                                      text: bind(\.appsText)).textFieldStyle(.halo)
                        }
                        GridRow {
                            label("Only in languages")
                            TextField("en, es (empty: all)", text: bind(\.languagesText))
                                .textFieldStyle(.halo)
                        }
                        GridRow {
                            Text("")
                            Toggle("Also fix its capitalisation when spelled right",
                                   isOn: bind(\.matchCase))
                                .toggleStyle(.haloCheckbox)
                        }
                    }
                    .onSubmit { vocab.save() }
                }
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .fill(editing ? HaloColor.selection : HaloColor.control))
            .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .strokeBorder(editing ? HaloColor.accentText : HaloColor.subtleBorder,
                              lineWidth: editing ? 1.5 : 1))
        }
    }

    private func label(_ text: String) -> some View {
        Text(text).font(HaloType.body(12, .semibold)).foregroundStyle(HaloColor.text)
            .gridColumnAlignment(.trailing)
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
                      + "shows that it is listening for a command, so an instruction is never "
                      + "mistaken for dictation.") {
                ToggleRow(title: "Enable Command Mode", isOn: $store.commandModeEnabled)
                RowDivider()
                FieldLabel("Start it with")
                RadioList(options: [
                    ("shift", "Shift + \(store.hotkey.uppercased())", nil),
                    ("key", "Its own key", nil),
                ], selection: Binding(
                    get: { store.commandHotkey.isEmpty ? "shift" : "key" },
                    set: { v in
                        store.commandTrigger = v == "shift" ? "shift" : "key"
                        if v == "shift" { store.commandHotkey = "" }
                        else if store.commandHotkey.isEmpty { store.commandHotkey = "f10" }
                    }), accessibilityName: "Start Command Mode with")
                    .disabled(!store.commandModeEnabled)
                    .opacity(store.commandModeEnabled ? 1 : 0.55)
                if !store.commandHotkey.isEmpty {
                    SettingRow(title: "Command key") {
                        HStack(spacing: 10) {
                            KeyCap(text: store.commandHotkey.uppercased())
                            Picker("Command key", selection: $store.commandHotkey) {
                                ForEach(Hotkeys.all.filter { $0 != store.hotkey }, id: \.self) {
                                    Text($0.uppercased()).tag($0)
                                }
                            }
                            .labelsHidden()
                            .frame(width: 90)
                        }
                    }
                }
            }

            Block(title: "Things you can say") {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(["Make this shorter.", "Fix the grammar.", "Turn this into bullet points.",
                             "Make this more professional.", "Rewrite this casually.",
                             "Delete the last sentence.", "Replace John with Sarah.",
                             "Summarize this.", "Capitalize this.",
                             "Run <custom transform name>."], id: \.self) {
                        Text("“\($0)”").font(HaloType.body(12.5)).foregroundStyle(HaloColor.text)
                    }
                }
                Support("Deleting, replacing and capitalising are exact rules. Rewrites need the local "
                        + "model (Settings › Models). Commands can only change text — never run programs "
                        + "or touch other apps.")
            }

            Block(title: "Custom transforms",
                  note: "Also in the menu bar's Transform Selection menu.") {
                if transforms.custom.isEmpty {
                    EmptyState(symbol: "wand.and.stars", title: "No custom transforms yet",
                               message: "A transform is a saved instruction you can run by voice, like "
                                   + "“run make it a haiku”, on any selected text.") {
                        Button("New transform") { ui.editingTransform = transforms.create().id }
                            .buttonStyle(.haloSmallPrimary)
                    }
                }
                ForEach(transforms.custom) { t in
                    TransformRow(transforms: transforms, ui: ui, transform: t)
                }
                HStack(spacing: 8) {
                    if !transforms.custom.isEmpty {
                        Button("New transform") { ui.editingTransform = transforms.create().id }
                            .buttonStyle(.haloSmallPrimary)
                    }
                    Menu("Duplicate a built-in") {
                        ForEach(TransformsStore.builtins) { b in
                            Button(b.name) { ui.editingTransform = transforms.create(from: b).id }
                        }
                    }
                    .fixedSize()
                }
            }

            Block(title: "Built-in transforms") {
                ForEach(Array(TransformsStore.builtins.enumerated()), id: \.element.id) { i, t in
                    if i > 0 { RowDivider() }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(t.name).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                        Support(t.instructions)
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
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    Text(transform.name.isEmpty ? "Untitled transform" : transform.name)
                        .font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                    Spacer(minLength: 8)
                    actions
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text(transform.name.isEmpty ? "Untitled transform" : transform.name)
                        .font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                    actions
                }
            }
            if editing {
                FieldLabel("Name")
                TextField("Name (what you say after “run”)", text: binding(\.name))
                    .textFieldStyle(.halo).frame(maxWidth: 360)
                if binding(\.name).wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    Note(text: "Give the transform a name — it is what you say after “run”.", failed: true)
                }
                FieldLabel("Instructions")
                HaloTextEditor(text: binding(\.instructions), label: "Instructions")
                if binding(\.instructions).wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    Note(text: "Write what the transform should do to the selected text.", failed: true)
                }
            } else {
                Text(transform.instructions).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    .lineLimit(2)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius).fill(HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
            .strokeBorder(editing ? HaloColor.accentText : HaloColor.subtleBorder,
                          lineWidth: editing ? 1.5 : 1))
    }

    private var actions: some View {
        HStack(spacing: 6) {
            Button(editing ? "Done" : "Edit") { ui.editingTransform = editing ? nil : transform.id }
                .buttonStyle(.haloSmall)
            Button("Duplicate") { ui.editingTransform = transforms.create(from: transform).id }
                .buttonStyle(.haloSmall)
            Button(role: .destructive) { transforms.delete(transform.id) } label: {
                Label("Delete", systemImage: "trash")
            }
            .buttonStyle(.haloDestructive)
        }
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

            if let m = models.message {
                Note(text: m, failed: models.failed).padding(.bottom, 12)
            }

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
                DetailRow(title: "\(ModelsStore.human(models.diskUsed)) used by models in Halo's folder",
                           detail: models.ramGB > 0 ? "This Mac has \(Int(models.ramGB)) GB of memory." : nil) {
                    Button("Reveal") {
                        NSWorkspace.shared.activateFileViewerSelecting([HaloPaths.modelsDir])
                    }
                    .buttonStyle(.haloSmall)
                }
            }
        }
        .onAppear { models.refresh() }
    }
}

/// name, purpose, size, real state, primary action. Every value here comes
/// from ModelsStore; nothing is invented.
struct ModelRow: View {
    @ObservedObject var models: ModelsStore
    let model: ModelsStore.Model

    private func dots(_ n: Int) -> String {
        String(repeating: "●", count: n) + String(repeating: "○", count: max(0, 5 - n))
    }

    private var chip: (HaloStatus, String) {
        if models.downloading == model.id {
            return (.working, String(format: "Downloading %.0f%%", models.progress * 100))
        }
        if models.verifying == model.id { return (.working, "Verifying") }
        if model.damaged { return (.error, "Damaged") }
        if model.installed {
            if model.verified == false { return (.error, "Checksum failed") }
            return model.selected ? (.ok, "In use") : (.info, "Installed")
        }
        if model.selected { return (.warning, "Selected but missing") }
        return model.partial > 0 ? (.info, "Partly downloaded") : (.info, "Not downloaded")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 8) {
                    title
                    Spacer(minLength: 8)
                    StateLabel(status: chip.0, text: chip.1)
                }
                VStack(alignment: .leading, spacing: 6) {
                    title
                    StateLabel(status: chip.0, text: chip.1)
                }
            }
            Support(model.note)
            Text("\(model.sizeText)"
                 + (model.languages.isEmpty ? "" : " · \(model.languages)")
                 + " · \(model.hardware)")
                .font(HaloType.mono(11, .regular)).foregroundStyle(HaloColor.secondaryText)
            Text("Quality \(dots(model.quality))  ·  Speed \(dots(model.speed))")
                .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                .accessibilityLabel("Quality \(model.quality) of 5, speed \(model.speed) of 5")
            if models.downloading == model.id {
                ProgressView(value: models.progress).tint(HaloColor.imperial)
            }
            if let d = detail {
                Text(d).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            actions
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius + 2).fill(HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius + 2)
            .strokeBorder(model.selected ? HaloColor.accentText : HaloColor.subtleBorder,
                          lineWidth: model.selected ? 1.5 : 1))
        .accessibilityElement(children: .contain)
    }

    private var title: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(model.id).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
            if model.recommended {
                Text("Recommended for this Mac").font(HaloType.support)
                    .foregroundStyle(HaloColor.secondaryText)
            }
        }
    }

    @ViewBuilder
    private var actions: some View {
        HStack(spacing: 6) {
            if models.downloading == model.id {
                Button("Cancel") { models.cancelDownload() }.buttonStyle(.haloSmall)
            } else if model.installed {
                if !model.selected {
                    Button("Use") { models.select(model) }.buttonStyle(.haloSmallPrimary)
                }
                Button(models.verifying == model.id ? "Verifying…" : "Verify") { models.verify(model) }
                    .buttonStyle(.haloSmall).disabled(models.verifying != nil)
                if !model.legacy {
                    Button(role: .destructive) { models.delete(model) } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .buttonStyle(.haloDestructive).disabled(model.selected)
                }
            } else {
                Button(model.partial > 0 ? "Resume download" : "Download") { models.download(model) }
                    .buttonStyle(.haloSmallPrimary).disabled(models.downloading != nil)
            }
        }
    }

    /// Facts the chip does not carry: where it lives, checksum, load state.
    private var detail: String? {
        if models.downloading == model.id { return nil }
        if model.damaged { return "Incomplete or damaged — download it again." }
        guard model.installed else {
            return model.partial > 0 ? "Partly downloaded (\(ModelsStore.human(model.partial)))."
                                     : nil
        }
        var s = model.legacy ? "Installed in ~/whisper.cpp" : "Installed"
        switch model.verified {
        case .some(true): s += " · checksum verified"
        case .some(false): s += " · checksum failed — delete and download again"
        case .none: s += " · not verified yet"
        }
        if model.kind == .cleanup && model.selected && !models.cleanupState.isEmpty {
            s += " · \(models.cleanupState)"
        }
        return s
    }
}
