import type { ModelProgress } from "../stores/app";

const ENGINE_LABELS: Record<string, string> = {
  parakeet: "Parakeet",
  gigaam: "GigaAM",
  whisper: "Whisper",
};

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_073_741_824).toFixed(1)} ГБ`;
  return `${Math.round(bytes / 1_048_576)} МБ`;
}

/// First launch pulls the model from HuggingFace — gigabytes on a fresh
/// install. Showing the bytes is the difference between "it's working" and
/// "it's broken", which is exactly how the silent version looked.
export default function ModelProgressBar({ progress }: { progress: ModelProgress }) {
  const { downloaded, total } = progress;
  const engine = ENGINE_LABELS[progress.engine] ?? progress.engine;
  const known = downloaded !== undefined && total !== undefined && total > 0;
  // Never show 100% while we're still waiting: the model also has to load into
  // memory after the last byte lands.
  const pct = known ? Math.min(99, Math.round((downloaded / total) * 100)) : null;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>Скачиваю модель {engine}</span>
        {known && (
          <span className="font-mono text-xs tabular-nums text-subtext">
            {formatSize(downloaded)} из ~{formatSize(total)}
          </span>
        )}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-raised">
        <div
          className={`h-full rounded-full bg-amber transition-[width] duration-500 ${
            pct === null ? "w-1/3 animate-pulse" : ""
          }`}
          style={pct === null ? undefined : { width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-subtext">
        Это один раз. Дальше распознавание работает без интернета.
      </p>
    </div>
  );
}
