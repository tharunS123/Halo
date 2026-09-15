import SwiftUI
import ThinkingOrbsKit

/// The dictation orb, one continuous view from first word to finish.
///
/// While you speak it is the Orb's `composing` ribbon, played by your voice:
/// the mic level drives how deep the ribbon undulates (`wobMul`) and how fast
/// its waves travel. Silence settles it into a calm band -- itself the visible
/// sign the mic hears nothing, since a missing mic grant records silence rather
/// than failing. When you stop, the ribbon dissolves into the `breathing` ring,
/// which carries on through processing and the finish with no second cut.
struct VoiceOrb: View {
    /// Read every frame, not observed: `level` arrives at ~60Hz and the
    /// timeline redraws at display rate anyway.
    let model: OverlayModel
    let speaking: Bool
    var preset: OrbSize = Style.orbPreset
    var displaySize: CGFloat = Style.orbSize

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        // Capped at 60fps: the 64pt ribbon is ~570 dots, and a 120Hz display
        // would double the work for motion this soft.
        TimelineView(.animation(minimumInterval: 1.0 / 60)) { timeline in
            let s = model.orb.step(at: timeline.date, level: model.level,
                                   speaking: speaking, frozen: reduceMotion)
            ZStack {
                // Both layers exist only during the dissolve.
                if s.breathing < 1 {
                    OrbDots(state: .composing, t: s.clock * speed(.composing),
                            overrides: ["wobMul": s.wob],
                            preset: preset, displaySize: displaySize)
                        .opacity(1 - s.breathing)
                }
                if s.breathing > 0 {
                    OrbDots(state: .breathing, t: s.clock * speed(.breathing),
                            overrides: [:],
                            preset: preset, displaySize: displaySize)
                        .opacity(s.breathing)
                }
            }
        }
        .frame(width: displaySize, height: displaySize)
        .accessibilityElement()
        .accessibilityLabel(speaking ? "Listening" : OrbState.breathing.label)
        .accessibilityAddTraits(.isImage)
    }

    private func speed(_ state: OrbState) -> Double {
        resolvePreset(state, preset).speed
    }
}

/// Voice-driven clock, wave depth and ribbon-to-ring dissolve for the orb.
///
/// The engine is a pure function of `t`, so speeding it up by scaling `t`
/// would jump the animation. Instead we integrate our own clock and ease every
/// change. Lives on the model so it survives SwiftUI re-creating the view.
final class OrbDriver {
    private enum Tuning {
        static let attack = 0.045   // s: the wave rises with a word almost instantly
        static let release = 0.22   // s: and falls back more gently between words
        static let morph = 0.30     // s: wave depth/speed settling after you stop
        static let dissolve = 0.55  // s: ribbon -> breathing ring, end to end
        static let quietWob = 0.35  // undulation in silence (1 = library default)
        static let loudWob = 2.0    // added at full voice
        static let quietRate = 0.5  // wave travel speed in silence (x preset speed)
        static let loudRate = 1.4   // added at full voice
    }

    private var last: Date?
    private var clock = 0.0
    private var amp = 0.0
    private var rate = Tuning.quietRate
    private var wob = Tuning.quietWob
    /// 0 = composing ribbon, 1 = breathing ring. Moves linearly so it lands
    /// exactly on either end; the returned weight is eased.
    private var progress = 0.0

    /// Start each dictation from a calm ribbon, not the previous one's state.
    func reset() {
        last = nil
        amp = 0
        rate = Tuning.quietRate
        wob = Tuning.quietWob
        progress = 0
    }

    /// Advance to `now`. Safe to call more than once per frame: a repeated
    /// timestamp is simply a zero-length step.
    func step(at now: Date, level: Double, speaking: Bool, frozen: Bool)
        -> (clock: Double, wob: Double, breathing: Double)
    {
        // Clamped so a stall (sleep, a hidden panel) cannot fling the clock.
        let dt = last.map { min(0.1, max(0, now.timeIntervalSince($0))) } ?? 0
        last = now

        let target = speaking ? min(1, max(0, level)) : 0
        amp += (target - amp) * ease(dt, target > amp ? Tuning.attack : Tuning.release)

        // After you stop, the ribbon calms rather than swelling, so it fades
        // out as a quiet band while the ring fades in.
        let wantRate = speaking ? Tuning.quietRate + Tuning.loudRate * amp : 1
        let wantWob = Tuning.quietWob + (speaking ? Tuning.loudWob * amp : 0)
        // While speaking, `amp` is already enveloped -- follow it closely, or
        // the wave lags the voice.
        let tau = speaking ? 0.02 : Tuning.morph
        rate += (wantRate - rate) * ease(dt, tau)
        wob += (wantWob - wob) * ease(dt, tau)

        let step = dt / Tuning.dissolve
        progress = speaking ? max(0, progress - step) : min(1, progress + step)

        // Reduce Motion: no drifting, but the shape still answers your voice.
        if !frozen { clock += dt * rate }
        return (clock, wob, smoothstep(progress))
    }

    private func ease(_ dt: Double, _ tau: Double) -> Double {
        1 - exp(-dt / tau)
    }

    private func smoothstep(_ x: Double) -> Double {
        x * x * (3 - 2 * x)
    }
}

/// Draws one orb frame. Mirrors ThinkingOrb's own painter (dots arrive
/// z-sorted; ink quantised to 8-bit), with light dots for the dark bubble.
struct OrbDots: View {
    let state: OrbState
    let t: Double
    let overrides: [String: Double]
    let preset: OrbSize
    let displaySize: CGFloat

    var body: some View {
        Canvas(rendersAsynchronously: false) { context, _ in
            let zoom = Double(displaySize) / Double(preset.rawValue)
            if zoom != 1 { context.scaleBy(x: zoom, y: zoom) }
            let frame = orbFrame(state: state, size: preset, t: t, overrides: overrides)
            for d in frame.dots {
                let rect = CGRect(x: d.x - d.r, y: d.y - d.r,
                                  width: d.r * 2, height: d.r * 2)
                context.fill(Path(ellipseIn: rect), with: .color(ink(d.white, d.a)))
            }
        }
        .frame(width: displaySize, height: displaySize)
    }

    private func ink(_ white: Double, _ alpha: Double) -> Color {
        let w = min(1, max(0, white))
        let g = ((1 - w) * 255).rounded(.toNearestOrAwayFromZero) / 255
        return Color(.sRGB, red: g, green: g, blue: g, opacity: alpha)
    }
}
