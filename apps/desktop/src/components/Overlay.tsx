import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const BAR_COUNT = 24;

type OverlayState = "idle" | "recording" | "processing";

/** Always-on pill near the taskbar (like Wispr Flow):
 *  idle       — mic icon + «Диктовка Ctrl + Win» hint
 *  recording  — waveform bars + timer
 *  processing — spinner while STT runs
 *  Lives in its own transparent always-on-top window. */
export default function Overlay() {
  const [state, setState] = useState<OverlayState>("idle");
  const [levels, setLevels] = useState<number[]>(Array(BAR_COUNT).fill(0.05));
  const [seconds, setSeconds] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const unlistenPromises = [
      listen("dictation:started", () => {
        setState("recording");
        setSeconds(0);
        setLevels(Array(BAR_COUNT).fill(0.05));
      }),
      listen("dictation:processing", () => setState("processing")),
      listen("dictation:finished", () => setState("idle")),
      listen("dictation:cancelled", () => setState("idle")),
    ];
    return () => {
      unlistenPromises.forEach((p) => p.then((un) => un()));
    };
  }, []);

  useEffect(() => {
    if (state === "recording") {
      pollRef.current = setInterval(async () => {
        try {
          const res = (await invoke("get_audio_level")) as { level: number };
          setLevels((prev) => {
            const next = prev.slice(1);
            next.push(Math.min(1, res.level * 6 + 0.05));
            return next;
          });
        } catch {
          /* engine busy — keep last frame */
        }
      }, 66);
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [state]);

  const mm = String(Math.floor(seconds / 60));
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div id="overlay-root" className="flex h-screen w-screen items-end justify-center pb-1">
      {state === "idle" && (
        <div className="flex items-center gap-2 rounded-full bg-surface/95 px-4 py-2 shadow-xl ring-1 ring-line">
          <MicIcon className="h-4 w-4 text-subtext" />
          <span className="text-xs text-subtext">
            Диктовка{" "}
            <kbd className="rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] text-amber">
              Ctrl + Win
            </kbd>
          </span>
        </div>
      )}

      {state === "recording" && (
        <div className="flex items-center gap-3 rounded-full bg-surface/95 px-5 py-2.5 shadow-2xl ring-1 ring-amber/40">
          <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-coral" />
          <div className="flex h-7 items-end gap-[2px]">
            {levels.map((level, i) => (
              <div
                key={i}
                className="w-[4px] rounded-sm bg-amber transition-[height] duration-75"
                style={{ height: `${Math.max(10, level * 100)}%` }}
              />
            ))}
          </div>
          <div className="font-mono text-sm tabular-nums text-subtext">
            {mm}:{ss}
          </div>
          <span className="text-xs text-subtext">Говорите…</span>
        </div>
      )}

      {state === "processing" && (
        <div className="flex items-center gap-2 rounded-full bg-surface/95 px-4 py-2 shadow-xl ring-1 ring-amber/40">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-amber border-t-transparent" />
          <span className="text-xs text-subtext">Обработка…</span>
        </div>
      )}
    </div>
  );
}

function MicIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3z" />
      <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V20H8a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2h-3v-2.08A7 7 0 0 0 19 11z" />
    </svg>
  );
}
