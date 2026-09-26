import SwiftUI
import ThinkingOrbsKit

enum Style {
    /// The panel: wide enough for a message, tall enough for the orb bubble.
    static let panelWidth: CGFloat = 208
    static let panelHeight: CGFloat = bubbleSize
    /// Message pill (errors, privacy toggles).
    static let pillHeight: CGFloat = 44
    /// Orb states (speaking, thinking, done): a round, mostly see-through bubble.
    static let bubbleSize: CGFloat = 84
    static let orbSize: CGFloat = 64
    /// The library's 64pt design, drawn at its native size -- the full-detail
    /// ribbon rather than the sparse inline preset.
    static let orbPreset: OrbSize = .px64
    static let accent = Color.white.opacity(0.92)
    /// Command Mode's ring: a different colour at a glance, so an instruction
    /// is never mistaken for dictation (or the other way round).
    static let command = Color(red: 0.62, green: 0.55, blue: 1.0)

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

    private var compact: Bool {
        switch model.state {
        case .info, .error: return false
        case .hidden, .listening, .command, .processing, .done: return true
        }
    }

    var body: some View {
        ZStack {
            background
            content.padding(.horizontal, compact ? 0 : 16)
        }
        .frame(width: compact ? Style.bubbleSize : Style.panelWidth,
               height: compact ? Style.bubbleSize : Style.pillHeight)
        .clipShape(Capsule(style: .continuous))
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
        // so without this the hosting view kept its intrinsic 208x84 and
        // AppKit snapped the panel straight back to it -- the window moved on
        // a size change but never actually grew.
        .frame(width: Style.panelWidth * model.scale,
               height: Style.panelHeight * model.scale)
    }

    /// Messages keep solid glass, because text must be readable over anything.
    @ViewBuilder
    private var background: some View {
        Vibrancy(material: .hudWindow)
            .opacity(compact ? Style.Glass.blur : 1)
        Color.black.opacity(compact ? Style.Glass.tint : 0.28)
        if compact {
            Style.Glass.glow
        }
        Capsule(style: .continuous)
            .strokeBorder(Color.white.opacity(compact ? Style.Glass.stroke : 0.13),
                          lineWidth: 1)
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case .hidden:
            EmptyView()

        // One view for all three live states: the voice ribbon dissolves into
        // the breathing ring when you stop, and the ring simply carries on
        // through processing and the finish -- no swap, no hard cut. Done is
        // held briefly (OverlayController.flashDone), then hidden.
        case .listening, .command, .processing, .done:
            let speaking = model.state == .listening || model.state == .command
            VoiceOrb(model: model, speaking: speaking)
                .overlay {
                    if model.commandMode {
                        Circle()
                            .strokeBorder(Style.command.opacity(0.9), lineWidth: 2.5)
                            .padding(3)
                            .transition(.opacity)
                    }
                }
                .overlay(alignment: .bottomLeading) {
                    if model.commandMode && speaking {
                        Image(systemName: "wand.and.stars")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Style.command)
                            .padding(4)
                            .background(Circle().fill(Color.black.opacity(0.6)))
                            .offset(x: -2, y: 2)
                    }
                }
                .overlay(alignment: .top) {
                    if speaking && !model.language.isEmpty {
                        Text(model.language)
                            .font(.system(size: 8, weight: .bold, design: .rounded))
                            .foregroundStyle(Style.accent)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Capsule().fill(Color.black.opacity(0.55)))
                            .offset(y: -1)
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    // Privacy Mode: visible at the moment you are speaking.
                    if speaking && model.privacy {
                        Image(systemName: "lock.fill")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Style.accent)
                            .padding(4)
                            .background(Circle().fill(Color.black.opacity(0.6)))
                            .offset(x: 2, y: 2)
                            .transition(.scale.combined(with: .opacity))
                    }
                }

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