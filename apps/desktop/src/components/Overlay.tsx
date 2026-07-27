import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";

const BAR_COUNT = 24;

type OverlayState = "idle" | "recording" | "processing";
type Engine = "parakeet" | "gigaam" | "faster-whisper";

const ENGINES: { id: Engine; label: string; note: string }[] = [
  { id: "parakeet", label: "Parakeet", note: "RU+EN · 5x" },
  { id: "gigaam", label: "GigaAM", note: "RU · 9x" },
  { id: "faster-whisper", label: "Whisper", note: "точный" },
];

// The window itself resizes so it only ever occupies its visible pixels —
// tiny in idle (clicks land on the app behind it), larger when it matters.
const SIZES = {
  collapsed: { w: 72, h: 16 },
  // pill and menu share a width so the pill doesn't jump sideways when the
  // menu opens; the window is wide enough that the centred menu never clips.
  pill: { w: 300, h: 44 },
  menu: { w: 300, h: 214 },
  active: { w: 340, h: 52 },
};

async function fitWindow(size: { w: number; h: number }) {
  try {
    // one native SetWindowPos on the Rust side: move + resize atomically,
    // so the window never paints at an intermediate rect (no stretch flash)
    await invoke("fit_overlay", { w: size.w, h: size.h });
  } catch {
    /* window API unavailable in dev preview */
  }
}

// Two rAFs guarantee the frame we just rendered actually reached the screen.
// The timeout is the escape hatch: when Windows decides the overlay isn't
// visible (occlusion tracking, sleep, lock screen) the webview stops painting
// and rAF never fires again. Without it the resize chain below would hang
// forever, leaving the overlay blank and frozen at its last size.
const nextPaint = () =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, 120);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        clearTimeout(timer);
        resolve();
      }),
    );
  });

export default function Overlay() {
  const [state, setState] = useState<OverlayState>("idle");
  const [hovered, setHovered] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // While the OS window is being resized we render nothing: during a resize
  // Windows shows the previous buffer anchored top-left in the new rect, so
  // old content would flash at the wrong spot. A transparent frame can't.
  const [resizing, setResizing] = useState(false);
  const [levels, setLevels] = useState<number[]>(Array(BAR_COUNT).fill(0.05));
  const [seconds, setSeconds] = useState(0);
  const [engine, setEngine] = useState<Engine>("parakeet");
  const [translate, setTranslate] = useState(false);
  const prevEngine = useRef<Engine>("parakeet");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const collapseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Collapse on a short delay so a stray mouse-out doesn't flicker the pill.
  const onEnter = () => {
    if (collapseRef.current) clearTimeout(collapseRef.current);
    setHovered(true);
    void refreshConfig(); // main window may have changed engine/translate
  };
  const onLeave = () => {
    if (collapseRef.current) clearTimeout(collapseRef.current);
    collapseRef.current = setTimeout(() => {
      setHovered(false);
      setMenuOpen(false);
    }, 300);
  };

  const refreshConfig = async () => {
    try {
      const c = (await invoke("engine_call", { method: "get_config", params: {} })) as {
        stt: { engine: Engine; translate: boolean };
      };
      setEngine(c.stt.engine);
      setTranslate(c.stt.translate);
      if (c.stt.engine !== "faster-whisper") prevEngine.current = c.stt.engine;
    } catch {
      /* engine busy */
    }
  };

  // Push a config change to the engine (set_config also reloads the STT model).
  const apply = (params: Record<string, unknown>) =>
    invoke("engine_call", { method: "set_config", params }).catch(() => {});

  const chooseEngine = (id: Engine) => {
    // Picking a non-Whisper engine while translating turns translation off,
    // since only Whisper can translate.
    const dropTranslate = translate && id !== "faster-whisper";
    setEngine(id);
    if (id !== "faster-whisper") prevEngine.current = id;
    if (dropTranslate) setTranslate(false);
    void apply(dropTranslate ? { "stt.engine": id, "stt.translate": false } : { "stt.engine": id });
  };

  const toggleTranslate = () => {
    const next = !translate;
    let nextEngine = engine;
    if (next) {
      // Turning translation on forces Whisper (the only engine that translates),
      // remembering the current engine to restore later.
      if (engine !== "faster-whisper") {
        prevEngine.current = engine;
        nextEngine = "faster-whisper";
      }
    } else {
      nextEngine = prevEngine.current;
    }
    setTranslate(next);
    setEngine(nextEngine);
    void apply({ "stt.translate": next, "stt.engine": nextEngine });
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
    // Size and position the window BEFORE revealing it, so it never flashes
    // at the OS default spot on launch (Rust keeps it hidden until now).
    void (async () => {
      await fitWindow(SIZES.collapsed);
      try {
        await getCurrentWindow().show();
      } catch {
        /* not running under Tauri (dev preview) */
      }
    })();
    void refreshConfig();
    return () => unlisten.forEach((p) => p.then((un) => un()));
  }, []);

  // Resize the OS window to match the current visual state:
  // blank frame first → resize → reveal (content fades in via .overlay-rise).
  useEffect(() => {
    const target =
      state === "recording" || state === "processing"
        ? SIZES.active
        : hovered
          ? menuOpen
            ? SIZES.menu
            : SIZES.pill
          : SIZES.collapsed;
    let stale = false;
    void (async () => {
      setResizing(true);
      await nextPaint();
      if (stale) return;
      await fitWindow(target);
      if (!stale) setResizing(false);
    })();
    return () => {
      stale = true;
    };
  }, [state, hovered, menuOpen]);

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
      {!resizing && state === "idle" && !hovered && (
        // resting sliver — a thin amber bar
        <div className="overlay-rise mb-1 h-1 w-14 rounded-full bg-amber/70 shadow-lg" />
      )}

      {!resizing && idleExpanded && (
        <div className="relative">
          {/* step 2: menu grows upward, centred over the pill (never clips) */}
          <div
            className={`overlay-menu absolute bottom-full left-1/2 mb-2 -ml-[135px] w-[270px] overflow-hidden rounded-[18px] bg-surface/95 shadow-2xl ring-1 ring-line backdrop-blur ${
              menuOpen ? "open" : ""
            }`}
          >
            <div className="flex flex-col gap-2 px-3.5 py-2.5">
              <div className="text-[10px] uppercase tracking-wider text-subtext">
                Движок распознавания
              </div>
              <div className="flex gap-1.5">
                {ENGINES.map((e) => {
                  const active = engine === e.id;
                  const dim = translate && e.id !== "faster-whisper";
                  return (
                    <button
                      key={e.id}
                      onClick={() => chooseEngine(e.id)}
                      className={`flex-1 rounded-xl border px-1 py-1.5 text-center text-xs transition-all ${
                        active
                          ? "border-amber bg-amber/[0.16] text-amber"
                          : "border-line bg-raised text-text hover:border-amber/50"
                      } ${dim ? "opacity-40" : ""}`}
                    >
                      {e.label}
                      <span className="mt-0.5 block text-[9px] text-subtext">{e.note}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="h-px bg-line" />

            <button
              onClick={toggleTranslate}
              className="flex w-full items-center justify-between px-3.5 py-2.5 transition-colors hover:bg-amber/[0.05]"
            >
              <span className="flex items-center gap-2.5">
                <SwapIcon className="h-4 w-4 text-amber" />
                <span className="text-left">
                  <span className="block text-xs">Перевод на английский</span>
                  <span className="block text-[10px] text-subtext">
                    {translate ? "движок переключён на Whisper" : "говорю по-русски → английский"}
                  </span>
                </span>
              </span>
              <span
                className={`relative h-5 w-9 flex-none rounded-full transition-colors ${
                  translate ? "bg-amber" : "bg-raised"
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                    translate ? "translate-x-4" : ""
                  }`}
                />
              </span>
            </button>
          </div>

          {/* step 1: compact pill with a kebab that opens the menu */}
          <div className="overlay-rise flex items-center gap-1.5 rounded-full bg-surface/95 py-1.5 pl-3.5 pr-1.5 shadow-xl ring-1 ring-line backdrop-blur">
            <button
              onClick={() => void invoke("open_main")}
              className="flex items-center gap-2"
              title="Открыть OpenFlow"
            >
              <MicIcon className="h-3.5 w-3.5 text-amber" />
              <span className="whitespace-nowrap text-xs text-subtext">
                Диктовка{" "}
                <kbd className="rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] text-amber">
                  Ctrl + Win
                </kbd>
              </span>
            </button>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              title="Меню"
              className={`ml-0.5 flex h-6 w-8 items-center justify-center gap-[3px] rounded-full transition-colors ${
                menuOpen ? "bg-amber text-base" : "bg-raised text-subtext hover:bg-amber/20 hover:text-amber"
              }`}
            >
              <span className="h-[3px] w-[3px] rounded-full bg-current" />
              <span className="h-[3px] w-[3px] rounded-full bg-current" />
              <span className="h-[3px] w-[3px] rounded-full bg-current" />
            </button>
          </div>
        </div>
      )}

      {!resizing && state === "recording" && (
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

      {!resizing && state === "processing" && (
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

function SwapIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 8.5h13l-3.2-3.2" />
      <path d="M20 15.5H7l3.2 3.2" />
    </svg>
  );
}
