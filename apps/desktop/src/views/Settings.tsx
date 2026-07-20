import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useAppStore } from "../stores/app";

const TABS = [
  "Общие",
  "Аудио",
  "Модели",
  "Хоткеи",
  "Сниппеты",
  "Команды",
  "Языки",
  "Приватность",
  "Производительность",
  "Продвинутые",
] as const;

type Tab = (typeof TABS)[number];

export default function Settings() {
  const [tab, setTab] = useState<Tab>("Общие");

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-4 text-2xl font-semibold">Настройки</h1>
      <div className="mb-6 flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
              tab === t ? "bg-amber-soft text-amber" : "text-subtext hover:bg-raised"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Общие" && <GeneralTab />}
      {tab === "Аудио" && <AudioTab />}
      {tab === "Модели" && <ModelsTab />}
      {tab === "Хоткеи" && <HotkeysTab />}
      {tab === "Сниппеты" && <SnippetsTab />}
      {tab === "Команды" && <CommandsTab />}
      {tab === "Языки" && <LanguagesTab />}
      {tab === "Приватность" && <PrivacyTab />}
      {tab === "Производительность" && <PerformanceTab />}
      {tab === "Продвинутые" && <AdvancedTab />}
    </div>
  );
}

/* ---------- shared field components ---------- */

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 rounded-lg border border-line bg-surface px-4 py-3">
      <div>
        <div className="text-sm">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-subtext">{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg bg-raised px-3 py-1.5 text-sm outline-none"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`h-6 w-11 rounded-full p-0.5 transition-colors ${value ? "bg-amber" : "bg-raised"}`}
    >
      <div
        className={`h-5 w-5 rounded-full bg-white transition-transform ${value ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

/* ---------- tabs ---------- */

function GeneralTab() {
  const { config, setConfig } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="Режим очистки" hint="Fast — правила, мгновенно. Smart — локальный LLM.">
        <Select
          value={config.cleanup.mode}
          options={[
            { value: "fast", label: "Fast" },
            { value: "smart", label: "Smart" },
            { value: "literal", label: "Literal (как сказано)" },
          ]}
          onChange={(v) => setConfig("cleanup.mode", v)}
        />
      </Row>
      <Row label="Убирать слова-паразиты" hint="эм, ну вот, um, uh…">
        <Toggle
          value={config.cleanup.remove_fillers}
          onChange={(v) => setConfig("cleanup.remove_fillers", v)}
        />
      </Row>
      <Row label="Сниппеты">
        <Toggle value={config.snippets.enabled} onChange={(v) => setConfig("snippets.enabled", v)} />
      </Row>
      <Row label="Голосовые команды">
        <Toggle value={config.commands.enabled} onChange={(v) => setConfig("commands.enabled", v)} />
      </Row>
      <Row label="Личный словарь">
        <Toggle
          value={config.dictionary.enabled}
          onChange={(v) => setConfig("dictionary.enabled", v)}
        />
      </Row>
    </div>
  );
}

function AudioTab() {
  const { config, devices, setConfig } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="Микрофон">
        <Select
          value={String(config.audio.device ?? "default")}
          options={[
            { value: "default", label: "Системный по умолчанию" },
            ...devices.map((d) => ({ value: String(d.id), label: d.name })),
          ]}
          onChange={(v) => setConfig("audio.device", v === "default" ? null : Number(v))}
        />
      </Row>
      <Row label="VAD" hint="Отсекать тишину перед распознаванием">
        <Toggle value={config.vad.enabled} onChange={(v) => setConfig("vad.enabled", v)} />
      </Row>
    </div>
  );
}

function ModelsTab() {
  const { config, setConfig, engineInfo } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="Модель распознавания" hint="Меньше — быстрее, больше — точнее">
        <Select
          value={config.stt.model}
          options={[
            { value: "tiny", label: "Tiny (75 МБ)" },
            { value: "base", label: "Base (145 МБ)" },
            { value: "small", label: "Small (484 МБ)" },
            { value: "medium", label: "Medium (1.5 ГБ)" },
            { value: "large-v3-turbo", label: "Large-v3 Turbo (1.6 ГБ, GPU)" },
            { value: "large-v3", label: "Large-v3 (3 ГБ, GPU)" },
          ]}
          onChange={(v) => setConfig("stt.model", v)}
        />
      </Row>
      <Row label="Устройство" hint={`Сейчас: ${engineInfo?.stt_device ?? "?"}`}>
        <Select
          value={config.stt.device}
          options={[
            { value: "auto", label: "Авто (CUDA → CPU)" },
            { value: "cuda", label: "CUDA (GPU)" },
            { value: "cpu", label: "CPU" },
          ]}
          onChange={(v) => setConfig("stt.device", v)}
        />
      </Row>
      <LlmRow />
    </div>
  );
}

/** "LLM для Smart-режима": either the configured path, or a one-click
 * download of the recommended Qwen model with polled progress. */
function LlmRow() {
  const { config, loadConfig } = useAppStore();
  const [dl, setDl] = useState<{ state: string; pct: number; error?: string }>({
    state: "idle",
    pct: 0,
  });
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  const poll = () => {
    timer.current = window.setInterval(async () => {
      try {
        const s = (await invoke("engine_call", {
          method: "download_llm_status",
          params: {},
        })) as { state: string; pct: number; error?: string };
        setDl(s);
        if (s.state === "done" || s.state === "error") {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          if (s.state === "done") await loadConfig();
        }
      } catch {
        /* engine busy (e.g. dictating) — keep polling */
      }
    }, 800);
  };

  const start = async () => {
    setDl({ state: "downloading", pct: 0 });
    await invoke("engine_call", { method: "download_llm", params: {} });
    poll();
  };

  if (!config) return null;

  if (config.llm.model_path) {
    return (
      <Row label="LLM для Smart-режима" hint={config.llm.model_path}>
        <span className="text-moss">✓</span>
      </Row>
    );
  }

  return (
    <Row
      label="LLM для Smart-режима"
      hint={
        dl.state === "error"
          ? `Не скачалось: ${dl.error ?? "ошибка сети"}. Можно повторить или указать GGUF-файл вручную в config.json`
          : "Нужна для умной очистки текста. Qwen2.5-1.5B, скачается один раз"
      }
    >
      {dl.state === "downloading" ? (
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-28 overflow-hidden rounded-full bg-raised">
            <div
              className="h-full rounded-full bg-amber transition-all"
              style={{ width: `${dl.pct}%` }}
            />
          </div>
          <span className="text-xs tabular-nums text-subtext">{Math.floor(dl.pct)}%</span>
        </div>
      ) : (
        <button
          onClick={() => void start()}
          className="rounded-lg bg-amber px-3 py-1.5 text-sm font-medium text-base transition-opacity hover:opacity-90"
        >
          {dl.state === "error" ? "Повторить" : "Скачать (1.1 ГБ)"}
        </button>
      )}
    </Row>
  );
}

function HotkeysTab() {
  const { hotkeys, setHotkeys } = useAppStore();
  const [ptt, setPtt] = useState(hotkeys.ptt);
  const [toggle, setToggle] = useState(hotkeys.toggle);
  const dirty = ptt !== hotkeys.ptt || toggle !== hotkeys.toggle;
  return (
    <div className="space-y-2">
      <Row label="Push-to-talk" hint="Зажал — говоришь — отпустил. Можно только модификаторы (Ctrl + Win)">
        <HotkeyCapture value={ptt} onChange={setPtt} allowModifiersOnly />
      </Row>
      <Row label="Toggle" hint="Нажал — говоришь — нажал ещё раз. Нужна обычная клавиша">
        <HotkeyCapture value={toggle} onChange={setToggle} />
      </Row>
      <button
        onClick={() => void setHotkeys(ptt, toggle)}
        disabled={!dirty}
        className="rounded-lg bg-amber px-4 py-2 text-sm font-medium text-base transition-opacity disabled:opacity-40"
      >
        Применить
      </button>
    </div>
  );
}

function SnippetsTab() {
  return (
    <EditableJsonList
      title="Сниппеты"
      hint='Скажи «мой календарь» — вставится ссылка. Файл: %APPDATA%\OpenFlow\snippets.json'
      method="reload_user_data"
    />
  );
}

function CommandsTab() {
  return (
    <div className="rounded-lg border border-line bg-surface p-5 text-sm leading-relaxed">
      <p className="mb-3 font-medium">Встроенные голосовые команды:</p>
      <ul className="grid grid-cols-2 gap-1 text-subtext">
        <li>«новый абзац» / new paragraph</li>
        <li>«новая строка» / new line</li>
        <li>«отмена» / undo</li>
        <li>«вернуть» / redo</li>
        <li>«удали последнее предложение»</li>
        <li>«маркированный список» / bullet list</li>
        <li>«сделай короче» / make shorter *</li>
        <li>«перепиши официально» *</li>
      </ul>
      <p className="mt-3 text-xs text-subtext">* — требуют Smart-режим (LLM)</p>
    </div>
  );
}

function LanguagesTab() {
  const { config, setConfig } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="Язык распознавания" hint="Авто определяет язык каждой фразы, включая смешанную речь">
        <Select
          value={config.stt.language ?? "auto"}
          options={[
            { value: "auto", label: "Авто (RU/EN/mixed)" },
            { value: "ru", label: "Русский" },
            { value: "en", label: "English" },
          ]}
          onChange={(v) => setConfig("stt.language", v === "auto" ? null : v)}
        />
      </Row>
      <Row
        label="Переводить на английский"
        hint="Говорите на любом языке — вставляется английский текст. Работает без Smart-режима; для лучшего перевода — модель Large-v3 Turbo."
      >
        <Toggle value={config.stt.translate} onChange={(v) => setConfig("stt.translate", v)} />
      </Row>
    </div>
  );
}

function PrivacyTab() {
  return (
    <div className="rounded-lg border border-line bg-surface p-5 text-sm leading-relaxed">
      <p className="mb-2 font-medium text-moss">Всё локально. Точка.</p>
      <ul className="list-inside list-disc space-y-1 text-subtext">
        <li>Аудио не покидает компьютер и не сохраняется на диск</li>
        <li>Распознавание и полировка — локальные модели</li>
        <li>Телеметрии нет вообще</li>
        <li>Сеть используется один раз — для скачивания моделей</li>
      </ul>
    </div>
  );
}

function PerformanceTab() {
  const { config, setConfig } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="Beam size" hint="1 — быстрее, 5 — точнее (медленнее)">
        <Select
          value={String(config.stt.beam_size)}
          options={[
            { value: "1", label: "1 (greedy)" },
            { value: "3", label: "3" },
            { value: "5", label: "5" },
          ]}
          onChange={(v) => setConfig("stt.beam_size", Number(v))}
        />
      </Row>
      <Row label="Compute type" hint="int8 для CPU, float16 для GPU">
        <Select
          value={config.stt.compute_type}
          options={[
            { value: "auto", label: "Авто" },
            { value: "int8", label: "int8" },
            { value: "float16", label: "float16" },
          ]}
          onChange={(v) => setConfig("stt.compute_type", v)}
        />
      </Row>
    </div>
  );
}

function AdvancedTab() {
  const { config, setConfig, reloadUserData } = useAppStore();
  if (!config) return <Loading />;
  return (
    <div className="space-y-2">
      <Row label="LLM: путь к GGUF" hint="Модель для Smart-режима">
        <input
          value={config.llm.model_path ?? ""}
          onChange={(e) => setConfig("llm.model_path", e.target.value || null)}
          placeholder="C:\models\qwen2.5-1.5b.gguf"
          className="w-72 rounded-lg bg-raised px-3 py-1.5 font-mono text-xs outline-none"
        />
      </Row>
      <Row label="LLM: температура">
        <input
          type="number"
          step="0.1"
          min="0"
          max="1"
          value={config.llm.temperature}
          onChange={(e) => setConfig("llm.temperature", Number(e.target.value))}
          className="w-20 rounded-lg bg-raised px-3 py-1.5 text-sm outline-none"
        />
      </Row>
      <button
        onClick={() => void reloadUserData()}
        className="rounded-lg bg-raised px-4 py-2 text-sm hover:bg-amber/20"
      >
        Перечитать сниппеты и словарь с диска
      </button>
    </div>
  );
}

function EditableJsonList({ title, hint, method }: { title: string; hint: string; method: string }) {
  const { reloadUserData } = useAppStore();
  void method;
  return (
    <div className="rounded-lg border border-line bg-surface p-5 text-sm">
      <p className="mb-2 font-medium">{title}</p>
      <p className="mb-4 text-subtext">{hint}</p>
      <button
        onClick={() => void reloadUserData()}
        className="rounded-lg bg-raised px-4 py-2 text-sm hover:bg-amber/20"
      >
        Перечитать с диска
      </button>
    </div>
  );
}

function Loading() {
  return <p className="text-sm text-subtext">Движок загружается…</p>;
}

const MODIFIER_KEYS = new Set(["Control", "Alt", "Shift", "Meta"]);

/** Records a key combo by listening to real key presses instead of typing.
 *  While focused: press the combo you want, it captures modifiers + one key
 *  (or just modifiers, for push-to-talk). */
function HotkeyCapture({
  value,
  onChange,
  allowModifiersOnly = false,
}: {
  value: string;
  onChange: (v: string) => void;
  allowModifiersOnly?: boolean;
}) {
  const [capturing, setCapturing] = useState(false);

  const keyName = (e: React.KeyboardEvent): string | null => {
    const map: Record<string, string> = {
      Control: "ctrl",
      Alt: "alt",
      Shift: "shift",
      Meta: "super",
      " ": "space",
    };
    if (map[e.key]) return map[e.key];
    if (MODIFIER_KEYS.has(e.key)) return null;
    if (e.key.length === 1) return e.key.toLowerCase();
    if (/^F\d{1,2}$/.test(e.key)) return e.key.toLowerCase();
    if (e.key === "Tab") return "tab";
    return null;
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    e.preventDefault();
    if (e.key === "Escape") {
      setCapturing(false);
      return;
    }
    const mods: string[] = [];
    if (e.ctrlKey) mods.push("ctrl");
    if (e.altKey) mods.push("alt");
    if (e.shiftKey) mods.push("shift");
    if (e.metaKey) mods.push("super");

    const main = keyName(e);
    if (main && !mods.includes(main)) {
      onChange([...mods, main].join("+"));
      setCapturing(false);
    } else if (allowModifiersOnly && mods.length > 0) {
      // modifier-only combo is only finalized on keyup; show it live meanwhile
      onChange(mods.join("+"));
    }
  };

  const onKeyUp = (e: React.KeyboardEvent) => {
    if (allowModifiersOnly && capturing && value.split("+").every((k) => ["ctrl", "alt", "shift", "super"].includes(k))) {
      e.preventDefault();
      setCapturing(false);
    }
  };

  return (
    <button
      onKeyDown={onKeyDown}
      onKeyUp={onKeyUp}
      onClick={() => setCapturing(true)}
      onBlur={() => setCapturing(false)}
      className={`w-52 rounded-lg border px-3 py-1.5 text-left font-mono text-sm outline-none transition-colors ${
        capturing
          ? "border-amber bg-raised text-amber"
          : "border-line bg-raised text-text hover:border-subtext"
      }`}
    >
      {capturing ? "Нажми сочетание…" : prettyCombo(value)}
    </button>
  );
}

function prettyCombo(spec: string): string {
  const map: Record<string, string> = {
    ctrl: "Ctrl",
    super: "Win",
    alt: "Alt",
    shift: "Shift",
    space: "Space",
  };
  return spec
    .split("+")
    .map((k) => map[k] ?? k.toUpperCase())
    .join(" + ");
}
