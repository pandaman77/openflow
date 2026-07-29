import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { check, type Update } from "@tauri-apps/plugin-updater";

export interface EngineConfig {
  audio: { device: number | null; sample_rate: number; channels: number };
  vad: { enabled: boolean; threshold: number; min_silence_ms: number };
  stt: {
    engine: string;
    model: string;
    device: string;
    compute_type: string;
    beam_size: number;
    language: string | null;
    translate: boolean;
  };
  cleanup: { mode: "fast" | "smart" | "literal"; remove_fillers: boolean; profile: string };
  llm: { model_path: string | null; context_size: number; max_tokens: number; temperature: number };
  snippets: { enabled: boolean };
  commands: { enabled: boolean };
  dictionary: { enabled: boolean };
}

export interface AudioDevice {
  id: number;
  name: string;
  default: boolean;
}

export interface DictationResult {
  type: "text" | "command" | "empty";
  text?: string;
  action?: string;
  language?: string;
  timings?: Record<string, number>;
}

/// Progress of the one-time model download, pushed by the engine while it
/// loads. `downloaded`/`total` are absent for models whose size we can't tell;
/// the ticks still arrive, so the UI can say "working" instead of going quiet.
export interface ModelProgress {
  engine: string;
  downloaded?: number;
  total?: number;
  done: boolean;
}

interface AppState {
  engineReady: boolean;
  engineError: string | null;
  engineInfo: { stt_device?: string; stt_engine?: string; smart_available?: boolean } | null;
  modelProgress: ModelProgress | null;
  /// Pending release, found at startup or by the button in the sidebar. Kept
  /// here so both places agree on what is available and what was dismissed.
  update: Update | null;
  updateDismissed: boolean;
  recording: boolean;
  config: EngineConfig | null;
  devices: AudioDevice[];
  lastResult: DictationResult | null;
  hotkeys: { ptt: string; toggle: string };

  init: () => Promise<void>;
  checkUpdate: () => Promise<"available" | "current" | "error">;
  dismissUpdate: () => void;
  loadConfig: () => Promise<void>;
  setConfig: (key: string, value: unknown) => Promise<void>;
  setHotkeys: (ptt: string, toggle: string) => Promise<void>;
  reloadUserData: () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  engineReady: false,
  engineError: null,
  engineInfo: null,
  modelProgress: null,
  update: null,
  updateDismissed: false,
  recording: false,
  config: null,
  devices: [],
  lastResult: null,
  hotkeys: { ptt: "ctrl+super", toggle: "ctrl+alt+d" },

  init: async () => {
    const markReady = (info: (AppState["engineInfo"] & { devices?: AudioDevice[] }) | null) => {
      if (get().engineReady) return;
      set({
        engineReady: true,
        engineError: null,
        engineInfo: info,
        modelProgress: null,
        devices: info?.devices ?? get().devices,
      });
      void get().loadConfig();
    };

    // Reliable path FIRST, before any awaited listen() so a slow subscription
    // can't delay it. Poll the stored status until the engine is ready.
    const poll = async () => {
      if (get().engineReady) return;
      try {
        const status = (await invoke("get_engine_status")) as
          | (AppState["engineInfo"] & { devices?: AudioDevice[] })
          | null;
        if (status) {
          markReady(status);
          return;
        }
      } catch {
        /* shell not ready yet */
      }
      setTimeout(poll, 500);
    };
    void poll();

    // Fast path: live event if the window is open when the engine finishes.
    void listen("engine:ready", (event) =>
      markReady(event.payload as AppState["engineInfo"] & { devices?: AudioDevice[] }),
    );
    void listen("engine:error", (event) => set({ engineError: String(event.payload) }));
    void listen("engine:progress", (event) =>
      set({ modelProgress: event.payload as ModelProgress }),
    );
    void listen("dictation:started", () => set({ recording: true }));
    void listen("dictation:finished", (event) =>
      set({ recording: false, lastResult: event.payload as DictationResult }),
    );
    void listen("dictation:cancelled", () => set({ recording: false }));

    // Look for a new release on every launch. Silent when there's nothing to
    // install, offline, or when no manifest is published yet.
    void get().checkUpdate();
  },

  checkUpdate: async () => {
    try {
      const found = await check();
      set({ update: found, updateDismissed: false });
      return found ? "available" : "current";
    } catch {
      return "error";
    }
  },

  dismissUpdate: () => set({ updateDismissed: true }),

  loadConfig: async () => {
    const config = (await invoke("engine_call", {
      method: "get_config",
      params: {},
    })) as EngineConfig;
    set({ config });
  },

  setConfig: async (key, value) => {
    await invoke("engine_call", { method: "set_config", params: { [key]: value } });
    await get().loadConfig();
  },

  setHotkeys: async (ptt, toggle) => {
    await invoke("set_hotkeys", { ptt, toggle });
    set({ hotkeys: { ptt, toggle } });
  },

  reloadUserData: async () => {
    await invoke("engine_call", { method: "reload_user_data", params: {} });
  },
}));
