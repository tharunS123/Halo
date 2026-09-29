import AppKit
import ApplicationServices
import IOKit.hid
import SwiftUI

// MARK: - History

struct HistoryPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var history = HistoryStore.shared

    static let retentions: [(String, String)] = [
        ("never", "Never keep"), ("1h", "1 hour"), ("24h", "24 hours"), ("7d", "7 days"),
        ("30d", "30 days"), ("forever", "Forever"),
    ]

    static func retentionLabel(_ code: String) -> String {
        retentions.first { $0.0 == code }?.1.lowercased() ?? code
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "History",
                      subtitle: "Off unless you turn it on. Kept only on this Mac, never with the text around your cursor, never for password fields.")

            FailedBlock()

            Block(title: "Keep a history",
                  note: "Turning it off deletes what was kept.") {
                ToggleRow(title: "Keep a history of my dictations", isOn: $store.historyEnabled)
                SettingRow(title: "Keep text for") {
                    Picker("Keep text for", selection: $store.historyRetention) {
                        ForEach(Self.retentions, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .labelsHidden()
                    .frame(width: 170)
                }
                .disabled(!store.historyEnabled)
                .opacity(store.historyEnabled ? 1 : 0.6)
                ToggleRow(title: "Also keep the audio (lets you retry transcription)",
                          isOn: $store.historyKeepAudio, disabled: !store.historyEnabled)
                if store.historyKeepAudio {
                    SettingRow(title: "Keep audio for") {
                        Picker("Keep audio for", selection: $store.historyAudioRetention) {
                            ForEach(Self.retentions, id: \.0) { Text($0.1).tag($0.0) }
                        }
                        .labelsHidden()
                        .frame(width: 170)
                    }
                    .disabled(!store.historyEnabled)
                    .opacity(store.historyEnabled ? 1 : 0.6)
                }
            }

            if store.historyEnabled || !history.items.isEmpty {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        searchBox.frame(maxWidth: 260)
                        Spacer(minLength: 8)
                        trailingTools
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        searchBox
                        trailingTools
                    }
                }
                .padding(.bottom, 10)
            }
            if let m = history.message {
                Note(text: m, failed: m.contains("Not") || m.contains("not")).padding(.bottom, 8)
            }

            if history.items.isEmpty {
                if !store.historyEnabled {
                    EmptyState(symbol: "clock.arrow.circlepath", title: "History is off",
                               message: "Halo is not keeping any transcripts. Turn it on to keep "
                                   + "your dictations on this Mac, so you can copy, retry or "
                                   + "reinsert them later.") {
                        Button("Turn on history") { store.historyEnabled = true }
                            .buttonStyle(.haloPrimary)
                    }
                } else if !history.query.trimmingCharacters(in: .whitespaces).isEmpty {
                    EmptyState(symbol: "magnifyingglass", title: "No matches",
                               message: "No kept dictation matches “\(history.query)”.")
                } else {
                    EmptyState(symbol: "text.quote", title: "Nothing here yet",
                               message: "Dictations you make from now on will appear here, "
                                   + "kept for \(Self.retentionLabel(store.historyRetention)).")
                }
            }
            VStack(spacing: 6) {
                ForEach(history.items) { item in HistoryRow(history: history, item: item) }
            }
        }
        .onAppear { history.load() }
        .onChange(of: store.historyEnabled) { _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { history.load() }
        }
        .alert("Delete all dictation history?", isPresented: $ui.confirmClearHistory) {
            Button("Delete", role: .destructive) { history.clearAll() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Every kept dictation and recording is removed from this Mac.")
        }
    }

    private var searchBox: some View {
        SearchField(placeholder: "Search history", text: $history.query) { history.load() }
    }

    private var trailingTools: some View {
        HStack(spacing: 8) {
            Button("Search") { history.load() }.buttonStyle(.haloSmall)
            if history.busy { ProgressView().controlSize(.small) }
            Button("Clear all…", role: .destructive) { ui.confirmClearHistory = true }
                .buttonStyle(.haloDestructive)
                .disabled(history.items.isEmpty)
        }
    }
}

/// The last dictation that did not make it. Shown whether or not History is
/// on: a failure must never cost you what you said.
struct FailedBlock: View {
    @ObservedObject var failed = FailedStore.shared

    private static let stages = [
        "transcription": "Transcription failed", "cleanup": "Cleanup failed",
        "insertion": "Not typed", "recovered": "Recovered after a restart",
    ]

    var body: some View {
        Group {
            if let item = failed.item {
                Block(title: "Didn’t make it",
                      note: "Halo keeps your last failed dictation for 30 minutes so nothing "
                          + "you said is lost. The words stay in memory; the recording, if "
                          + "kept, is deleted when you discard it.") {
                    HaloBanner(status: .warning,
                               title: (Self.stages[item.stage] ?? item.stage)
                                   + (item.app.isEmpty ? "" : " (\(item.app))"),
                               message: item.reason)
                    (Text(item.at, style: .relative) + Text(" ago"))
                        .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    if !(item.text.isEmpty && item.raw.isEmpty) {
                        Text(item.text.isEmpty ? item.raw : item.text)
                            .font(HaloType.control).foregroundStyle(HaloColor.text)
                            .textSelection(.enabled).lineLimit(6)
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                                .fill(HaloColor.control))
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 6) {
                            Button("Retry transcription") { failed.run("retry_transcription") }
                                .buttonStyle(.haloSmall)
                                .disabled(!item.hasAudio)
                            Button("Retry cleanup") { failed.run("retry_cleanup") }
                                .buttonStyle(.haloSmall)
                                .disabled(item.raw.isEmpty)
                            Button("Retry insertion") { failed.run("retry_insertion") }
                                .buttonStyle(.haloSmallPrimary)
                                .disabled(item.text.isEmpty && item.raw.isEmpty)
                                .help("Hides this window and types it into the app underneath")
                            Button("Copy") { failed.run("copy") }
                                .buttonStyle(.haloSmall)
                                .disabled(item.text.isEmpty && item.raw.isEmpty)
                        }
                        HStack(spacing: 8) {
                            if failed.busy { ProgressView().controlSize(.small) }
                            Spacer()
                            Button(role: .destructive) { failed.run("discard") } label: {
                                Label("Discard", systemImage: "trash")
                            }
                            .buttonStyle(.haloDestructive)
                        }
                    }
                    .disabled(failed.busy)
                    if let m = failed.message { Note(text: m, failed: m.hasPrefix("Could not")) }
                }
            }
        }
        .onAppear { failed.load() }
    }
}

struct HistoryRow: View {
    @ObservedObject var history: HistoryStore
    let item: HistoryStore.Item

    private var open: Bool { history.selected == item.id }
    private var inserted: Bool { item.status == "inserted" }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                history.selected = open ? nil : item.id
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: open ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(HaloColor.secondaryText)
                        .frame(width: 10)
                        .accessibilityHidden(true)
                    Text(item.created, style: .time).font(HaloType.mono(11, .regular))
                        .foregroundStyle(HaloColor.secondaryText).frame(width: 64, alignment: .leading)
                    Text(item.cleaned.isEmpty ? item.raw : item.cleaned)
                        .font(HaloType.control).foregroundStyle(HaloColor.text).lineLimit(1)
                    Spacer(minLength: 8)
                    if !item.app.isEmpty {
                        Text(item.app).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                            .lineLimit(1)
                    }
                    HStack(spacing: 4) {
                        Image(systemName: inserted ? "checkmark.circle" : "exclamationmark.circle")
                            .font(.system(size: 11))
                        Text(inserted ? "Typed" : item.status).font(HaloType.body(11, .medium))
                    }
                    .foregroundStyle(HaloColor.text)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(open ? "Hides the details" : "Shows the details")
            if open {
                VStack(alignment: .leading, spacing: 6) {
                    Text(item.created.formatted(date: .abbreviated, time: .standard)
                         + String(format: " · %.1fs", item.duration)
                         + " · \(item.language) · \(item.mode) · \(item.status)"
                         + (item.reason.isEmpty ? "" : " (\(item.reason))"))
                        .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    FieldLabel("Heard")
                    Text(item.raw).font(HaloType.control).foregroundStyle(HaloColor.text)
                        .textSelection(.enabled)
                    FieldLabel("Typed")
                    Text(item.cleaned).font(HaloType.control).foregroundStyle(HaloColor.text)
                        .textSelection(.enabled)
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 6) {
                            Button("Copy") { history.copy(item) }.buttonStyle(.haloSmall)
                            Button("Reinsert") { history.reinsert(item) }.buttonStyle(.haloSmallPrimary)
                                .help("Hides this window and types it into the app underneath")
                            Button("Retry cleanup") { history.retry(item, transcription: false) }
                                .buttonStyle(.haloSmall)
                            Button("Retry transcription") { history.retry(item, transcription: true) }
                                .buttonStyle(.haloSmall)
                                .disabled(!item.hasAudio)
                        }
                        HStack {
                            Spacer()
                            Button(role: .destructive) { history.delete(item) } label: {
                                Label("Delete", systemImage: "trash")
                            }
                            .buttonStyle(.haloDestructive)
                        }
                    }
                    .disabled(history.busy)
                }
                .padding(.leading, 18)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
            .fill(open ? HaloColor.selection : HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
            .strokeBorder(open ? HaloColor.accentText : HaloColor.subtleBorder,
                          lineWidth: open ? 1.5 : 1))
    }
}

// MARK: - Privacy

struct PrivacyPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var keys = KeyStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Privacy",
                      subtitle: "Everything stays on this Mac. What Halo keeps, and where it lives.")

            Block(title: "Processing stays on this Mac",
                  note: "This is about where your words go. What is kept afterwards is separate, below.") {
                statusRow(.ok, "Audio never leaves this Mac — whisper runs locally.")
                statusRow(.ok, "The text around your cursor never leaves this Mac"
                          + (store.contextEnabled ? " (Context Awareness is on, in memory only)."
                                                  : " (Context Awareness is off)."))
                statusRow(.ok, "Transcript text never leaves this Mac — the engine refuses "
                          + "every network connection, so this holds with Wi-Fi off too.")
            }

            Block(title: "What Halo keeps on this Mac") {
                statusRow(.info, store.historyEnabled
                          ? "History is on: dictated text is kept for "
                            + HistoryPane.retentionLabel(store.historyRetention)
                            + (store.historyKeepAudio
                               ? ", and recordings for " + HistoryPane.retentionLabel(store.historyAudioRetention)
                               : "") + "."
                          : "History is off: no transcripts are kept.")
                statusRow(.info, "The last failed dictation is held for up to 30 minutes so you can "
                          + "retry it, even with History off. Discarding it removes it.")
                statusRow(store.debugLogContent ? .warning : .ok, store.debugLogContent
                          ? "Debug content logging is ON: dictated text is written to engine.log."
                          : "Logs record lengths, never what you said.")
            }

            Block(title: "Privacy Mode",
                  note: "For a dictation you want no trace of. Halo keeps no History entry "
                      + "(text or audio), reads no text around your cursor, and does not learn "
                      + "from your corrections. Your words are still cleaned up as usual. The "
                      + "orb shows a lock while it is on; say “privacy on” or “privacy off” any time.") {
                ToggleRow(title: "Start with Privacy Mode on", isOn: $store.privacyDefault)
            }

            if keys.stored || keys.message != nil {
                Block(title: "Old OpenRouter key",
                      note: "An earlier Halo could send transcripts to OpenRouter and stored its key "
                          + "in your Keychain. Nothing uses it any more.") {
                    SettingRow(title: keys.stored ? "A key is still in your Keychain."
                                                  : "No key stored.") {
                        if keys.stored {
                            Button(role: .destructive) { keys.clear() } label: {
                                Label("Remove", systemImage: "trash")
                            }
                            .buttonStyle(.haloDestructive)
                        }
                    }
                    if let message = keys.message { Note(text: message, failed: keys.stored) }
                }
            }

            Block(title: "Where your data lives") {
                location("Settings, dictionary, styles, transforms", HaloPaths.configDir)
                RowDivider()
                location("Models, history, state", HaloPaths.dataDir)
                RowDivider()
                location(store.debugLogContent ? "Logs (currently include dictated text)"
                                               : "Logs (lengths only, no dictated text)",
                         HaloPaths.logDir)
            }

            Block(title: "Clear stored data") {
                HStack(spacing: 8) {
                    Button { HistoryStore.shared.clearAll(); ui.dataMessage = "History cleared." } label: {
                        Label("Clear history", systemImage: "trash")
                    }
                    .buttonStyle(.haloDestructive)
                    Button {
                        try? FileManager.default.removeItem(at: HaloPaths.suggestions)
                        VocabularyStore.shared.loadSuggestions()
                        ui.dataMessage = "Suggestions cleared."
                    } label: { Label("Clear word suggestions", systemImage: "trash") }
                    .buttonStyle(.haloDestructive)
                    Button {
                        for name in ["engine.log", "overlay.log"] {
                            try? Data().write(to: HaloPaths.logDir.appendingPathComponent(name))
                        }
                        ui.dataMessage = "Logs cleared."
                    } label: { Label("Clear logs", systemImage: "trash") }
                    .buttonStyle(.haloDestructive)
                }
                if let m = ui.dataMessage { Note(text: m) }
            }
        }
        .onAppear { keys.refresh() }
    }

    private func statusRow(_ status: HaloStatus, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: status.symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(status.tint)
                .accessibilityLabel(status.spoken)
            Text(text).font(HaloType.control).foregroundStyle(HaloColor.text)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func location(_ label: String, _ url: URL) -> some View {
        DetailRow(title: label,
                   detail: url.path.replacingOccurrences(of: HaloPaths.home.path, with: "~")) {
            Button("Reveal") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
                .buttonStyle(.haloSmall)
        }
    }
}

// MARK: - Permissions

struct PermissionsPane: View {
    var body: some View {
        // Re-read every second while visible: grants happen in another app.
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            VStack(alignment: .leading, spacing: 0) {
                PaneTitle(title: "Permissions",
                          subtitle: "What macOS must allow for Halo to work. Granted to Halo.app, which runs the engine.")
                PermissionRow(title: "Microphone", why: "Recording while you hold the key.",
                              status: Permissions.microphoneChip.0,
                              statusText: Permissions.microphoneChip.1) {
                    if Permissions.microphone == .notDetermined {
                        Button("Allow") { Permissions.requestMicrophone { _ in } }
                            .buttonStyle(.haloSmallPrimary)
                    } else if Permissions.microphone != .authorized {
                        Button("Open System Settings") { SystemSettings.open(.microphone) }
                            .buttonStyle(.haloSmallPrimary)
                    }
                }
                PermissionRow(title: "Accessibility", why: "Typing the text, reading context, undo.",
                              status: Permissions.accessibility ? .ok : .error,
                              statusText: Permissions.accessibility ? "Allowed" : "Not granted") {
                    if !Permissions.accessibility {
                        Button("Open System Settings") {
                            let opts = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
                            _ = AXIsProcessTrustedWithOptions(opts)
                            SystemSettings.open(.accessibility)
                        }
                        .buttonStyle(.haloSmallPrimary)
                    }
                }
                PermissionRow(title: "Input Monitoring", why: "Noticing the dictation key, anywhere.",
                              status: Permissions.inputMonitoring == 0 ? .ok : .error,
                              statusText: Permissions.inputMonitoring == 0 ? "Allowed"
                                  : (Permissions.inputMonitoring == 1 ? "Denied" : "Not granted")) {
                    if Permissions.inputMonitoring != 0 {
                        Button("Open System Settings") {
                            _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
                            SystemSettings.open(.inputMonitoring)
                        }
                        .buttonStyle(.haloSmallPrimary)
                    }
                }
                Support("After granting Accessibility, Halo restarts its engine by itself within a "
                        + "couple of seconds. If macOS asks you to quit Halo, do — it comes back at login "
                        + "or with `halo start`. This list re-checks every second.")
                    .padding(.top, 4)
            }
        }
    }
}

// MARK: - Advanced

struct AdvancedPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Advanced", subtitle: "Engine health, diagnostics and the settings you rarely need.")

            Block(title: "Engine health") {
                if let sup = EngineSupervisor.current {
                    SupervisorStatus(supervisor: sup)
                } else {
                    InfoNote("Running in terminal mode: `python halo.py` owns the engine.")
                }
                if let e = ui.healthError {
                    Note(text: e, failed: true)
                } else if !ui.health.isEmpty {
                    Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 14, verticalSpacing: 4) {
                        ForEach(ui.health.keys.sorted(), id: \.self) { k in
                            GridRow {
                                Text(k.replacingOccurrences(of: "_", with: " "))
                                    .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                                    .gridColumnAlignment(.leading)
                                Text(ui.health[k] ?? "").font(HaloType.mono(11.5, .regular))
                                    .foregroundStyle(HaloColor.text)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
                HStack(spacing: 8) {
                    Button("Refresh") { refresh() }.buttonStyle(.haloSmall)
                    Button("Restart engine") {
                        EngineSupervisor.current?.restart()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { refresh() }
                    }
                    .buttonStyle(.haloSmall).disabled(EngineSupervisor.current == nil)
                    Button("Open engine log") { NSWorkspace.shared.open(HaloPaths.engineLog) }
                        .buttonStyle(.haloSmall)
                }
            }

            Block(title: "Insertion",
                  note: "Automatic picks per app: Accessibility where the app honours it and the "
                      + "result can be verified, paste (with your clipboard restored) elsewhere, "
                      + "typed keystrokes for remote desktops.") {
                SettingRow(title: "Method") {
                    Picker("Method", selection: $store.insertionMethod) {
                        Text("Automatic (recommended)").tag("auto")
                        Text("Accessibility").tag("ax")
                        Text("Paste").tag("paste")
                        Text("Type").tag("type")
                    }
                    .labelsHidden()
                    .frame(width: 220)
                }
            }

            Block(title: "Debug content logging",
                  note: "For chasing a bug only. Off by default; turn it off again when done.") {
                ToggleRow(title: "Write dictated text to the engine log", isOn: $store.debugLogContent)
                if store.debugLogContent {
                    HaloBanner(status: .warning,
                               title: "Your dictated text is being written to engine.log",
                               message: "While this is on, what you dictate, selected text and commands "
                                   + "are saved in plain text in "
                                   + HaloPaths.engineLog.path.replacingOccurrences(of: HaloPaths.home.path, with: "~")
                                   + ". Clear the logs from Privacy afterwards.")
                } else {
                    Support("While on, what you dictate, selected text and commands are written to "
                            + "engine.log in plain text.")
                }
            }

            Block(title: "Reset",
                  note: "Every setting back to its default. Your dictionary, styles, transforms, "
                      + "history and models are not touched.") {
                Button(role: .destructive) { ui.confirmReset = true } label: {
                    Label("Reset all settings…", systemImage: "arrow.counterclockwise")
                }
                .buttonStyle(.haloDestructive)
            }
        }
        .onAppear { refresh() }
        .alert("Reset all settings?", isPresented: $ui.confirmReset) {
            Button("Reset", role: .destructive) { store.resetToDefaults() }
            Button("Cancel", role: .cancel) {}
        }
    }

    private func refresh() {
        EngineClient.request(["op": "health"], timeout: 3) { reply in
            guard let reply, reply["ok"] as? Bool == true else {
                ui.health = [:]
                ui.healthError = "The engine is not answering."
                return
            }
            ui.healthError = nil
            var h: [String: String] = [:]
            for (k, v) in reply where k != "ok" { h[k] = "\(v)" }
            ui.health = h
        }
    }
}

struct SupervisorStatus: View {
    @ObservedObject var supervisor: EngineSupervisor

    private var status: HaloStatus {
        supervisor.state == "running" ? .ok : (supervisor.state.hasPrefix("waiting") ? .warning : .error)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            StateLabel(status: status,
                       text: "Engine: \(supervisor.state)" + (supervisor.pid > 0 ? " (pid \(supervisor.pid))" : ""))
            if let started = supervisor.startedAt {
                Support("Up since \(started.formatted(date: .omitted, time: .shortened))"
                        + " · \(supervisor.crashes.count) crash\(supervisor.crashes.count == 1 ? "" : "es") recorded"
                        + (supervisor.lastExit.map { " · last exit \($0)" } ?? ""))
            }
        }
    }
}
