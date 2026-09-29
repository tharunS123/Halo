import SwiftUI

// Pieces of the first-run guide: the four-phase progress header, page titles,
// rows and the model / meter views. State lives in OnboardingModel; nothing
// here uses SwiftUI macros (see CONTRIBUTING.md).

/// The ten steps grouped into four named phases. Purely visual: the stored
/// step index and its persistence are untouched.
enum OnboardingPhase: Int, CaseIterable, Identifiable {
    case welcome, access, voice, tryIt

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Welcome"
        case .access: return "Access"
        case .voice: return "Voice"
        case .tryIt: return "Try it"
        }
    }

    /// 0-based step indices in this phase.
    var steps: ClosedRange<Int> {
        switch self {
        case .welcome: return 0...1
        case .access: return 2...3
        case .voice: return 4...7
        case .tryIt: return 8...9
        }
    }

    static func of(step: Int) -> OnboardingPhase {
        allCases.first { $0.steps.contains(step) } ?? .tryIt
    }
}

/// Small brand at the left, "Step N of 10" at the right, and the four
/// phases underneath. The current phase is bold, has a filled marker and a
/// progress bar; finished phases carry a check -- never color alone.
struct OnboardingProgressHeader: View {
    let step: Int

    var body: some View {
        let current = OnboardingPhase.of(step: step)
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                if step > 0 {
                    HaloMark(size: 24)
                    HaloWordmark(height: 14)
                }
                Spacer(minLength: 8)
                Text("Step \(step + 1) of \(Onboarding.steps)")
                    .font(HaloType.body(12, .semibold))
                    .foregroundStyle(HaloColor.secondaryText)
            }
            .frame(minHeight: 24)
            HStack(alignment: .top, spacing: 10) {
                ForEach(OnboardingPhase.allCases) { phase in
                    segment(phase, current: current)
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func segment(_ phase: OnboardingPhase, current: OnboardingPhase) -> some View {
        let done = phase.rawValue < current.rawValue
        let isCurrent = phase == current
        let fraction: Double = done ? 1
            : isCurrent ? Double(step - phase.steps.lowerBound + 1) / Double(phase.steps.count)
            : 0
        let symbol = done ? "checkmark.circle.fill" : (isCurrent ? "circle.inset.filled" : "circle")
        let state = done ? "done" : (isCurrent ? "current" : "upcoming")
        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(HaloColor.subtleBorder)
                    Capsule().fill(done ? HaloColor.text : HaloColor.imperial)
                        .frame(width: geo.size.width * fraction)
                }
            }
            .frame(height: 4)
            HStack(spacing: 5) {
                Image(systemName: symbol).font(.system(size: 11, weight: .semibold))
                Text(phase.title)
                    .font(HaloType.body(12.5, isCurrent ? .bold : .regular))
                    .lineLimit(1)
            }
            .foregroundStyle(isCurrent ? HaloColor.text : HaloColor.secondaryText)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(phase.title), phase \(phase.rawValue + 1) of \(OnboardingPhase.allCases.count), \(state)")
        .accessibilityAddTraits(isCurrent ? .isSelected : [])
    }
}

/// A step's heading (Oswald) and one line of supporting copy.
struct OnboardingTitle: View {
    let title: String
    var subtitle: String? = nil
    var size: CGFloat = 28

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(HaloType.heading(size))
                .foregroundStyle(HaloColor.text)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let subtitle {
                Text(subtitle)
                    .font(HaloType.control)
                    .foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// An icon and a sentence. The icon is decoration; the sentence says it all.
struct OnboardingBullet: View {
    let icon: String
    let text: Text

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .regular))
                .frame(width: 22)
                .foregroundStyle(HaloColor.accentText)
                .accessibilityHidden(true)
            text
                .font(HaloType.control)
                .foregroundStyle(HaloColor.text)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// The live microphone level: a track and a bar, with the value spoken.
struct OnboardingLevelMeter: View {
    let level: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(HaloColor.control)
                Capsule().strokeBorder(HaloColor.border, lineWidth: 1)
                Capsule().fill(HaloColor.imperial)
                    .frame(width: max(6, geo.size.width * min(max(level, 0), 1)))
                    .animation(.linear(duration: 0.08), value: level)
            }
        }
        .frame(height: 12)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Microphone input level")
        .accessibilityValue("\(Int((min(max(level, 0), 1)) * 100)) percent")
    }
}

/// One speech model in the guide: what it is, its real state (symbol +
/// words), and the actions that apply. Progress and verification come from
/// ModelsStore; nothing here is invented.
struct OnboardingModelRow: View {
    @ObservedObject var models: ModelsStore
    let model: ModelsStore.Model

    private func dots(_ n: Int) -> String {
        String(repeating: "●", count: n) + String(repeating: "○", count: max(0, 5 - n))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Text(model.id).font(HaloType.body(14, .semibold))
                        .foregroundStyle(HaloColor.text)
                    if model.selected {
                        StateLabel(status: .ok, text: "In use")
                    }
                    if model.recommended {
                        Text("Recommended for this Mac")
                            .font(HaloType.body(11.5, .semibold))
                            .foregroundStyle(HaloColor.secondaryText)
                    }
                }
                Text(model.note).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                Text("\(model.sizeText) · quality \(dots(model.quality)) · speed \(dots(model.speed))"
                     + (model.languages.isEmpty ? "" : " · \(model.languages)")
                     + " · \(model.hardware)")
                    .font(HaloType.body(11.5)).foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel("\(model.sizeText), quality \(model.quality) of 5, "
                                        + "speed \(model.speed) of 5"
                                        + (model.languages.isEmpty ? "" : ", \(model.languages)")
                                        + ", \(model.hardware)")
                statusLine
            }
            if models.downloading == model.id {
                HStack(spacing: 12) {
                    ProgressView(value: models.progress)
                        .frame(maxWidth: 260)
                        .accessibilityLabel("Download progress")
                        .accessibilityValue("\(Int(models.progress * 100)) percent")
                    Button("Cancel") { models.cancelDownload() }.buttonStyle(.haloSecondary)
                }
            } else {
                HStack(spacing: 8) { actions }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius).fill(HaloColor.surface))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius)
            .strokeBorder(model.selected ? HaloColor.text : HaloColor.subtleBorder,
                          lineWidth: model.selected ? 1.5 : 1))
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private var actions: some View {
        if model.installed {
            if !model.selected {
                Button("Use") { models.select(model) }.buttonStyle(.haloSecondary)
            }
            Button(models.verifying == model.id ? "Verifying…" : "Verify") { models.verify(model) }
                .buttonStyle(.haloSecondary).disabled(models.verifying != nil)
            if !model.legacy {
                Button("Delete") { models.delete(model) }
                    .buttonStyle(.haloSecondary).disabled(model.selected)
            }
        } else {
            Button(model.partial > 0 ? "Resume download" : "Download") { models.download(model) }
                .buttonStyle(.haloSecondary).disabled(models.downloading != nil)
            if model.selected {
                StateLabel(status: .warning, text: "Selected but missing")
            }
        }
    }

    private var statusLine: some View {
        let (status, text) = state
        return HStack(spacing: 6) {
            if status == .working {
                ProgressView().controlSize(.mini)
            } else {
                Image(systemName: status.symbol).foregroundStyle(status.tint)
                    .accessibilityHidden(true)
            }
            Text(text).font(HaloType.body(12, .semibold)).foregroundStyle(HaloColor.text)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(status.spoken): \(text)")
    }

    private var state: (HaloStatus, String) {
        if models.downloading == model.id {
            return (.working, String(format: "Downloading… %.0f%%", models.progress * 100))
        }
        if model.damaged { return (.warning, "Incomplete or damaged — download it again.") }
        guard model.installed else {
            return (.info, model.partial > 0
                    ? "Partly downloaded (\(ModelsStore.human(model.partial)))." : "Not downloaded.")
        }
        let base = model.legacy ? "Installed (in ~/whisper.cpp)" : "Installed"
        switch model.verified {
        case .some(true): return (.ok, base + " · checksum verified")
        case .some(false): return (.error, base + " · checksum failed — delete and download again")
        case .none: return (.info, base + " · not verified yet")
        }
    }
}
