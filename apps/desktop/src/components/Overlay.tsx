import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  getCurrentWindow,
  currentMonitor,
  LogicalSize,
  LogicalPosition,
} from "@tauri-apps/api/window";

const BAR_COUNT = 24;

type OverlayState = "idle" | "recording" | "processing";

// The window itself resizes so it only ever occupies its visible pixels —
// tiny in idle (clicks land on the app behind it), larger when it matters.
const SIZES = {
  collapsed: { w: 72, h: 16 },
  expanded: { w: 300, h: 40 },
  active: { w: 340, h: 52 },
};

async function fitWindow(size: { w: number; h: number }) {
  try {
    const win = getCurrentWindow();
    const monitor = await currentMonitor();
    await win.setSize(new LogicalSize(size.w, size.h));
    if (monitor) {
      const scale = monitor.scaleFactor;
      const screenW = monitor.size.width / scale;
      const screenH = monitor.size.height / scale;
      const x = Math.round((screenW - size.w) / 2);
      // sit above the taskbar (same level as before), not on top of it
      const y = Math.round(screenH - size.h - 56);
      await win.setPosition(new LogicalPosition(x, y));
    }
  } catch {
    /* window API unavailable in dev preview */
  }
}

export default function Overlay() {
  const [state, setState] = useState<OverlayState>("idle");
  const [hovered, setHovered] = useState(false);
  const [levels, setLevels] = useState<number[]>(Array(BAR_COUNT).fill(0.05));
  const [seconds, setSeconds] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const collapseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Collapse on a short delay so a stray mouse-out doesn't flicker the pill.
  const onEnter = () => {
    if (collapseRef.current) clearTimeout(collapseRef.current);
    setHovered(true);
  };
  const onLeave = () => {
    if (collapseRef.current) clearTimeout(collapseRef.current);
    collapseRef.current = setTimeout(() => setHovered(false), 260);
  };

  useEffect(() => {
    const unlisten = [
      listen("dictation:started", () => {
        setState("recording");
        setSeconds(0);
        setLevels(Array(BAR_COUNT).fill(0.05));
      }),
      listen("dictation:processing", () => setState("processing")),
      listen("dictation:finished", () => setState("idle")),
      listen("dictation:cancelled", () => setState("idle")),
    ];
    void fitWindow(SIZES.collapsed);
    return () => unlisten.forEach((p) => p.then((un) => un()));
  }, []);

  // Resize the OS window to match the current visual state.
  useEffect(() => {
    if (state === "recording" || state === "processing") {
      void fitWindow(SIZES.active);
    } else {
      void fitWindow(hovered ? SIZES.expanded : SIZES.collapsed);
    }
  }, [state, hovered]);

  useEffect(() => {
    if (state === "recording") {
      pollRef.current = setInterval(async () => {
        try {
          const res = (await invoke("get_audio_level")) as { level: number };
          setLevels((prev) => [...prev.slice(1), Math.min(1, res.level * 6 + 0.05)]);
        } catch {
          /* engine busy */
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
  const idleExpanded = state === "idle" && hovered;

  return (
    <div
      id="overlay-root"
      className="flex h-screen w-screen items-end justify-center pb-1"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {state === "idle" && !hovered && (
        // resting sliver — a thin amber bar
        <div className="mb-1 h-1 w-14 rounded-full bg-amber/70 shadow-lg" />
      )}

      {idleExpanded && (
        // click opens the main window, like Wispr Flow
        <button
          onClick={() => void invoke("open_main")}
          className="overlay-rise flex cursor-pointer items-center gap-2 rounded-full bg-surface/95 px-4 py-1.5 shadow-xl ring-1 ring-line transition-colors hover:ring-amber/50"
          title="Открыть OpenFlow"
        >
          <MicIcon className="h-3.5 w-3.5 text-amber" />
          <span className="text-xs text-subtext">
            Диктовка{" "}
            <kbd className="rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] text-amber">
              Ctrl + Win
            </kbd>
          </span>
        </button>
      )}

      {state === "recording" && (
        <div className="overlay-rise flex items-center gap-3 rounded-full bg-surface/95 px-4 py-1.5 shadow-2xl ring-1 ring-amber/40">
          <div className="h-2 w-2 animate-pulse rounded-full bg-coral" />
          <div className="flex h-6 items-end gap-[2px]">
            {levels.map((level, i) => (
              <div
                key={i}
                className="w-[3px] rounded-sm bg-amber transition-[height] duration-75"
                style={{ height: `${Math.max(10, level * 100)}%` }}
              />
            ))}
          </div>
          <div className="font-mono text-xs tabular-nums text-subtext">
            {mm}:{ss}
          </div>
        </div>
      )}

      {state === "processing" && (
        <div className="overlay-rise flex items-center gap-2 rounded-full bg-surface/95 px-4 py-1.5 shadow-xl ring-1 ring-amber/40">
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
