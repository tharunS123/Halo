import SwiftUI

enum Style {
    static let pillHeight: CGFloat = 44
    static let pillWidth: CGFloat = 208
    static let corner: CGFloat = 22
    static let accent = Color.white.opacity(0.92)
    static let barWidth: CGFloat = 3
    static let barGap: CGFloat = 3
    static let barMaxHeight: CGFloat = 20
    static let barMinHeight: CGFloat = 3
}

struct OverlayView: View {
    @ObservedObject var model: OverlayModel

    var body: some View {
        ZStack {
            Vibrancy(material: .hudWindow)
            Color.black.opacity(0.28)
            RoundedRectangle(cornerRadius: Style.corner, style: .continuous)
                .strokeBorder(Color.white.opacity(0.13), lineWidth: 1)

            content.padding(.horizontal, 16)
        }
        .frame(width: Style.pillWidth, height: Style.pillHeight)
        .clipShape(RoundedRectangle(cornerRadius: Style.corner, style: .continuous))
        // Entrance/exit: rises slightly as it grows in, settles with a spring.
        .scaleEffect(model.visible ? 1.0 : 0.86, anchor: .bottom)
        .offset(y: model.visible ? 0 : 10)
        .opacity(model.visible ? 1 : 0)
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case .hidden:
            EmptyView()

        case .listening:
            HStack(spacing: 10) {
                Image(systemName: model.privacy ? "lock.fill" : "mic.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Style.accent)
                    .transition(.scale.combined(with: .opacity))
                BarRow(
                    heights: model.levels.map {
                        max(Style.barMinHeight, $0 * Style.barMaxHeight)
                    },
                    animated: true
                )
                .frame(height: Style.barMaxHeight)
            }

        case .processing:
            ProcessingBars(
                handoff: model.levelsAtHandoff,
                start: model.stateChangedAt
            )
            .frame(height: Style.barMaxHeight)

        case .done:
            DoneCheck()

        case .info:
            HStack(spacing: 8) {
                Image(systemName: model.message.lowercased().contains("on")
                      ? "lock.fill" : "lock.open.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Style.accent)
                Text(model.message)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(Style.accent)
                    .lineLimit(1)
            }

        case .error:
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 1.0, green: 0.78, blue: 0.35))
                Text(model.message.isEmpty ? "Dictation error" : model.message)
                    .font(.system(size: 11.5, weight: .medium, design: .rounded))
                    .foregroundStyle(Style.accent)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A plain row of bars. Both live states render through this, so moving
/// between them animates heights rather than swapping views.
struct BarRow: View {
    let heights: [CGFloat]
    var opacities: [Double]? = nil
    /// Listening arrives as discrete 60Hz samples, so we spring between them
    /// to fill a 120Hz display. Processing is already continuous via
    /// TimelineView and must NOT be animated, or the two would fight.
    var animated: Bool = false

    var body: some View {
        HStack(alignment: .center, spacing: Style.barGap) {
            ForEach(heights.indices, id: \.self) { i in
                Capsule(style: .continuous)
                    .fill(Style.accent)
                    .opacity(opacities.map { $0[i] } ?? 1)
                    .frame(width: Style.barWidth, height: heights[i])
                    .animation(
                        animated
                            ? .interpolatingSpring(stiffness: 340, damping: 22)
                            : nil,
                        value: heights[i]
                    )
            }
        }
    }
}

/// Processing: a soft pulse of light sweeping left-to-right through the same
/// bars, over a slow breathing baseline. Driven by TimelineView so it redraws
/// at display refresh rate rather than on a fixed timer.
struct ProcessingBars: View {
    let handoff: [CGFloat]
    let start: Date

    // Tuning
    private let sweepPeriod: Double = 1.45   // seconds per pass
    private let sigma: Double = 2.6          // width of the pulse, in bars
    private let peak: CGFloat = 15           // pulse crest height
    private let base: CGFloat = 3.5          // resting height
    private let morphDuration: Double = 0.38 // blend out of the waveform

    var body: some View {
        TimelineView(.animation) { ctx in
            let f = bars(at: ctx.date)
            BarRow(heights: f.heights, opacities: f.opacities)
        }
    }

    /// Pure computation, kept out of the ViewBuilder closure (result builders
    /// cannot contain control flow).
    private func bars(at now: Date) -> (heights: [CGFloat], opacities: [Double]) {
        let t = now.timeIntervalSince(start)
        let blend = easeOut(min(1, max(0, t / morphDuration)))
        let n = kBarCount

        // Sweep with lead-in/lead-out so the pulse enters and exits the pill
        // rather than popping into existence at the first bar.
        let phase = (t / sweepPeriod).truncatingRemainder(dividingBy: 1)
        let center = phase * Double(n + 10) - 5

        var heights: [CGFloat] = []
        var ops: [Double] = []
        heights.reserveCapacity(n)
        ops.reserveCapacity(n)

        for i in 0..<n {
            let d = Double(i) - center
            let bump = exp(-(d * d) / (2 * sigma * sigma))
            // gentle idle motion so the row is never fully static
            let breathe = 0.5 + 0.5 * sin(t * 2.1 + Double(i) * 0.42)
            let target = base
                + CGFloat(bump) * (peak - base)
                + CGFloat(breathe) * 1.6

            let idx = min(i, handoff.count - 1)
            let from = max(Style.barMinHeight, handoff[idx] * Style.barMaxHeight)
            heights.append(from + (target - from) * CGFloat(blend))
            ops.append(0.30 + 0.62 * bump)
        }
        return (heights, ops)
    }

    private func easeOut(_ x: Double) -> Double { 1 - pow(1 - x, 3) }
}

/// Checkmark that springs in, then holds.
struct DoneCheck: View {
    // Not `@State`: on the macOS 27 SDK that spelling is a macro whose plugin
    // ships only with Xcode, so it fails to build with Command Line Tools.
    // The State struct itself needs no plugin, and SwiftUI finds it the same way.
    private let shownState = State(initialValue: false)
    private var shown: Bool {
        get { shownState.wrappedValue }
        nonmutating set { shownState.wrappedValue = newValue }
    }

    var body: some View {
        Image(systemName: "checkmark")
            .font(.system(size: 16, weight: .bold))
            .foregroundStyle(Style.accent)
            .scaleEffect(shown ? 1 : 0.55)
            .opacity(shown ? 1 : 0)
            .onAppear {
                withAnimation(.spring(response: 0.34, dampingFraction: 0.58)) {
                    shown = true
                }
            }
    }
}
