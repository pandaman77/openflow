/** The signature element: a breathing waveform line.
 *  Repeating SVG path drifts left; speed and color carry engine state.
 *  quiet  — engine loading, dim line barely moving
 *  ready  — amber, calm drift
 *  hot    — coral, fast drift (recording)
 */
export default function Wave({
  state = "ready",
  height = 36,
  className = "",
}: {
  state?: "quiet" | "ready" | "hot";
  height?: number;
  className?: string;
}) {
  const stroke =
    state === "hot" ? "#e4626f" : state === "ready" ? "#f2a35c" : "#3a4d4a";
  const opacity = state === "quiet" ? 0.55 : 0.9;
  const anim = state === "hot" ? "wave-hot" : "wave-live";

  // one 120px tile of a voice-like line, repeated to cover 200% width
  const tile =
    "M0 18 C6 18 8 8 14 8 S22 26 28 26 34 12 40 12 46 22 52 22 58 6 64 6 " +
    "70 28 76 28 82 14 88 14 94 20 100 20 106 10 112 10 118 18 120 18";

  return (
    <div
      className={`pointer-events-none overflow-hidden ${className}`}
      style={{ height }}
      aria-hidden="true"
    >
      <svg
        className={anim}
        width="200%"
        height={height}
        viewBox={`0 0 960 36`}
        preserveAspectRatio="none"
        style={{ display: "block" }}
      >
        {Array.from({ length: 8 }, (_, i) => (
          <path
            key={i}
            d={tile}
            transform={`translate(${i * 120} 0)`}
            fill="none"
            stroke={stroke}
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity={opacity}
          />
        ))}
      </svg>
    </div>
  );
}
