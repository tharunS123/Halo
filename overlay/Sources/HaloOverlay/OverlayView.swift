import BorderBeamKit
import SwiftUI
import ThinkingOrbsKit

enum Style {
    /// The panel: wide enough for a two-line message, and for the state labels
    /// that sit beside the bubble; tall enough for the orb bubble.
    static let panelWidth: CGFloat = 264
    /// The original panel width. The orb keeps the on-screen position it had
    /// then (OverlayController anchors on this), so widening the panel for
    /// labels does not move the orb.
    static let anchorWidth: CGFloat = 208
    static let panelHeight: CGFloat = bubbleSize
    /// Message pill (errors, privacy toggles): one line; two lines grow it.
    static let pillHeight: CGFloat = 44
    /// Orb states (speaking, thinking, done): a round, mostly see-through bubble.
    static let bubbleSize: CGFloat = 84
    static let orbSize: CGFloat = 64
    /// The library's 64pt design, drawn at its native size -- the full-detail
    /// ribbon rather than the sparse inline preset.
    static let orbPreset: OrbSize = .px64
    static let accent = Color.white.opacity(0.92)
    /// Command Mode's rim: Imperial at a glance, so an instruction is never
    /// mistaken for dictation. The rim is never the only signal: the wand
    /// badge and the word "Command" say it too.
    static let command = HaloColor.imperial

    /// Orb states are mostly see-through so the animation reads against the
    /// desktop. The glow is what keeps light dots legible over a white window.
    enum Glass {
        static let blur = 0.35   // opacity of the behind-window blur
        static let tint = 0.0    // flat dark wash over the whole bubble
        static let stroke = 0.08
        /// Dark radial glow behind the orb: dense under the dots, clear at the
        /// rim. A lighter glow (0.45) left the dots grey-on-grey over a white
        /// window, so the density is what buys transparency everywhere else.
        static let glowCore = 0.78
        static let glowMid = 0.55

        static var glow: RadialGradient {
            RadialGradient(
                stops: [
                    .init(color: .black.opacity(glowCore), location: 0),
                    .init(color: .black.opacity(glowMid), location: 0.62),
                    .init(color: .clear, location: 1),
                ],
                center: .center, startRadius: 0, endRadius: Style.bubbleSize / 2
            )
        }
    }
}

struct OverlayView: View {
    @ObservedObject var model: OverlayModel
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    private var compact: Bool {
        switch model.state {
        case .info, .error: return false
        case .hidden, .listening, .command, .processing, .inserting, .done: return true
        }
    }

    /// The beam exists only around the orb bubble and only while there is
    /// something to show. Once the state is `.hidden` the view is gone, so its
    /// TimelineViews stop: nothing renders while the panel is off screen.
    private var showsBeam: Bool { compact && model.state != .hidden }

    private var increasedContrast: Bool { contrast == .increased }

    var body: some View {
        ZStack {
            ZStack {
                background
                content
                    .padding(.horizontal, compact ? 0 : 20)
                    .padding(.vertical, compact ? 0 : 10)
                if showsBeam {
                    BeamRing(active: model.visible,
                             command: model.commandMode,
                             increasedContrast: increasedContrast)
                        .transition(.opacity)
                }
            }
            .frame(width: compact ? Style.bubbleSize : pillWidth,
                   height: compact ? Style.bubbleSize : nil)
            .frame(minHeight: compact ? Style.bubbleSize : Style.pillHeight)
            .clipShape(Capsule(style: .continuous))

            // State labels sit beside the bubble, never inside the orb, and
            // are as click-through as the rest of the panel.
            if compact { sideLabels }
        }
        // Entrance/exit: rises slightly as it grows in, settles with a spring.
        .scaleEffect(model.visible ? 1.0 : 0.86, anchor: .bottom)
        .offset(y: model.visible ? 0 : 10)
        .opacity(model.visible ? 1 : 0)
        // The panel keeps its full size; the pill sits on its bottom edge, so
        // the bubble grows upward from the same baseline as a message pill.
        .frame(width: Style.panelWidth, height: Style.panelHeight, alignment: .bottom)
        // Settings > Orb > Size. Applied as a transform rather than by
        // threading a multiplier through every dimension: the orb's own
        // geometry is tuned at its native 64pt preset, and re-deriving the
        // ribbon at an arbitrary size changes how it looks, not just how big
        // it is.
        .scaleEffect(model.scale)
        // ...and then claim the scaled size for layout. `scaleEffect` is a
        // render-time transform: it does NOT change the size the view reports,
        // so without this the hosting view kept its intrinsic size and
        // AppKit snapped the panel straight back to it -- the window moved on
        // a size change but never actually grew.
        .frame(width: Style.panelWidth * model.scale,
               height: Style.panelHeight * model.scale)
    }

    /// Errors get the full width (two lines); short notices the original one.
    private var pillWidth: CGFloat {
        model.state == .error ? Style.panelWidth : Style.anchorWidth
    }

    /// Messages keep solid glass, because text must be readable over anything.
    /// Reduce Transparency swaps the blur for an opaque Night fill.
    @ViewBuilder
    private var background: some View {
        if reduceTransparency {
            HaloColor.night.opacity(compact ? 0.9 : 0.97)
        } else {
            Vibrancy(material: .hudWindow)
                .opacity(compact ? Style.Glass.blur : 1)
            Color.black.opacity(compact ? Style.Glass.tint : 0.28)
        }
        if compact {
            Style.Glass.glow
        }
        Capsule(style: .continuous)
            .strokeBorder(rim, lineWidth: compact && model.commandMode ? 2 : 1)
    }

    /// The rim of the bubble. In Command Mode it is Imperial; otherwise it is
    /// a faint neutral line (a firm one with Increase Contrast).
    private var rim: Color {
        if compact && model.commandMode { return Style.command.opacity(0.95) }
        if increasedContrast { return Color.white.opacity(0.6) }
        return Color.white.opacity(compact ? Style.Glass.stroke : 0.13)
    }

    // MARK: Labels beside the bubble

    private var speaking: Bool { model.state == .listening || model.state == .command }

    @ViewBuilder
    private var sideLabels: some View {
        let side = (Style.panelWidth - Style.bubbleSize) / 2
        HStack(spacing: 0) {
            VStack(alignment: .trailing, spacing: 4) {
                // Command Mode is named in words, not only by its rim colour,
                // and stays through processing so it is never mistaken for
                // dictation.
                if model.commandMode {
                    OverlayChip(text: "Command", symbol: "wand.and.stars", tint: Style.command)
                }
                switch model.state {
                case .listening:
                    OverlayChip(text: "Listening")
                case .processing:
                    OverlayChip(text: "Processing")
                case .inserting:
                    // The text is done and going in now -- the moment
                    // switching apps would stop it landing.
                    OverlayChip(text: "Inserting", symbol: "character.cursor.ibeam")
                case .done:
                    OverlayChip(text: "Done")
                case .command, .hidden, .info, .error:
                    EmptyView()
                }
            }
            .frame(width: side, alignment: .trailing)
            .padding(.trailing, 6)

            Color.clear.frame(width: Style.bubbleSize)

            VStack(alignment: .leading, spacing: 4) {
                if speaking && !model.language.isEmpty {
                    OverlayChip(text: model.language)
                }
                // Privacy Mode: visible at the moment you are speaking.
                if speaking && model.privacy {
                    OverlayChip(text: "Privacy", symbol: "lock.fill")
                }
            }
            .frame(width: side, alignment: .leading)
            .padding(.leading, 6)
        }
        .frame(width: Style.panelWidth, height: Style.bubbleSize)
        .allowsHitTesting(false)
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case .hidden:
            EmptyView()

        // One view for all the live states: the voice ribbon dissolves into
        // the breathing ring when you stop, and the ring simply carries on
        // through processing and the finish -- no swap, no hard cut. Done is
        // held briefly (OverlayController.flashDone), then hidden. Nothing is
        // drawn over the orb; its labels are outside the bubble.
        case .listening, .command, .processing, .inserting, .done:
            VoiceOrb(model: model, speaking: speaking)

        case .info:
            HStack(spacing: 8) {
                Image(systemName: infoSymbol)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Style.accent)
                Text(model.message)
                    .font(HaloType.body(12.5, .medium))
                    .foregroundStyle(Style.accent)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

        case .error:
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(HaloColor.imperial)
                Text(model.message.isEmpty ? "Dictation error" : model.message)
                    .font(HaloType.body(12.5, .medium))
                    .foregroundStyle(Style.accent)
                    .lineLimit(2)
                    .truncationMode(.tail)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Error: \(model.message.isEmpty ? "Dictation error" : model.message)")
        }
    }

    /// A lock only for the Privacy Mode notices; everything else is a plain
    /// note (the old test, "contains on", also matched "Restarting dictation").
    private var infoSymbol: String {
        let m = model.message.lowercased()
        guard m.hasPrefix("privacy") else { return "info.circle" }
        return m.hasSuffix("on") ? "lock.fill" : "lock.open.fill"
    }
}

/// A small text label beside the orb: legible size, Night fill, never
/// interactive.
private struct OverlayChip: View {
    let text: String
    var symbol: String? = nil
    var tint: Color = Style.accent
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        HStack(spacing: 4) {
            if let symbol {
                Image(systemName: symbol)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(tint)
            }
            Text(text)
                .font(HaloType.body(11.5, .semibold))
                .foregroundStyle(Style.accent)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Capsule().fill(HaloColor.night.opacity(0.85)))
        .overlay(Capsule().strokeBorder(Color.white.opacity(contrast == .increased ? 0.6 : 0.18),
                                        lineWidth: 1))
        .fixedSize()
        .allowsHitTesting(false)
        .accessibilityElement(children: .combine)
        .transition(.opacity)
    }
}

/// The Border Beam (Libraries.dev), a decorative ring at the edge of the orb's
/// 84pt container. It is a separate layer: nothing in it touches the orb, and
/// it is masked away from the orb's 64pt drawing area, so only the rim glows.
///
/// - Official BorderBeamKit, `.mono` variant, circular radius.
/// - `active` false fades it out; the view is removed entirely once the
///   overlay state is `.hidden`, which stops its rendering.
/// - Reduce Motion, or no compiled shader library (see
///   scripts/build-beam-metallib.sh): a static neutral boundary instead.
private struct BeamRing: View {
    let active: Bool
    let command: Bool
    let increasedContrast: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Group {
            if reduceMotion || !BeamRuntime.shadersAvailable {
                Circle()
                    .strokeBorder(Color.white.opacity(increasedContrast ? 0.75 : 0.4),
                                  lineWidth: 1.5)
                    .opacity(active ? 1 : 0)
            } else {
                BorderBeam(size: .md, colorVariant: .mono, theme: .dark,
                           active: active,
                           borderRadius: Double(Style.bubbleSize) / 2) {
                    Color.clear
                }
                .mask(rimMask)
            }
        }
        .frame(width: Style.bubbleSize, height: Style.bubbleSize)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// Opaque from the rim inward to just outside the orb's drawing area,
    /// clear inside it.
    private var rimMask: some View {
        RadialGradient(
            stops: [
                .init(color: .clear, location: 0),
                .init(color: .clear, location: 34 / (Style.bubbleSize / 2)),
                .init(color: .black, location: 39 / (Style.bubbleSize / 2)),
                .init(color: .black, location: 1),
            ],
            center: .center, startRadius: 0, endRadius: Style.bubbleSize / 2)
    }
}
