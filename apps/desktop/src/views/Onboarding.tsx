import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useAppStore, DictationResult } from "../stores/app";

const STEPS = ["Микрофон", "Модель", "Хоткей", "Проверка"] as const;

/** First-launch wizard: mic -> model -> hotkey -> live test. */
export default function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const { devices, config, setConfig, engineReady, engineError, hotkeys } = useAppStore();
  const [testResult, setTestResult] = useState<DictationResult | null>(null);
  const [testing, setTesting] = useState(false);

  const runTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await invoke("start_dictation");
      await new Promise((r) => setTimeout(r, 4000));
      const result = (await invoke("stop_dictation")) as DictationResult;
      setTestResult(result);
    } catch (e) {
      setTestResult({ type: "empty", text: String(e) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="flex h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex justify-center gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                  i <= step ? "bg-amber text-base" : "bg-raised text-subtext"
                }`}
              >
                {i + 1}
              </div>
              <span className={`text-xs ${i === step ? "text-text" : "text-subtext"}`}>{s}</span>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-line bg-surface p-8">
          {step === 0 && (
            <div>
              <h2 className="mb-3 text-xl font-semibold">Привет! 👋</h2>
              <p className="mb-4 text-sm text-subtext">
                OpenFlow превращает речь в чистый текст в любом приложении. Всё работает
                локально. Выбери микрофон:
              </p>
              <select
                value={String(config?.audio.device ?? "default")}
                onChange={(e) =>
                  setConfig("audio.device", e.target.value === "default" ? null : Number(e.target.value))
                }
                className="w-full rounded-lg bg-raised px-3 py-2 text-sm outline-none"
              >
                <option value="default">Системный по умолчанию</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {step === 1 && (
            <div>
              <h2 className="mb-3 text-xl font-semibold">Модель распознавания</h2>
              <p className="mb-4 text-sm text-subtext">
                {engineReady
                  ? "Движок уже готов с моделью по умолчанию (small). Поменять можно в настройках."
                  : engineError
                    ? "Движок не смог запуститься:"
                    : "Движок загружает модель — при первом запуске она скачивается (~500 МБ), это происходит один раз."}
              </p>
              <div className={`rounded-lg p-3 text-sm ${engineError ? "bg-coral/10 text-coral" : "bg-raised"}`}>
                {engineReady ? "✓ Готов" : engineError ? engineError : "⏳ Загрузка…"}
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h2 className="mb-3 text-xl font-semibold">Хоткей</h2>
              <p className="text-sm leading-relaxed text-subtext">
                Зажми{" "}
                <kbd className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-amber">
                  {hotkeys.ptt
                    .split("+")
                    .map((k) => ({ ctrl: "Ctrl", super: "Win", space: "Space", alt: "Alt" }[k] ?? k))
                    .join(" + ")}
                </kbd>{" "}
                в любом приложении, говори, отпусти. Текст вставится сам. Изменить сочетание
                можно в настройках.
              </p>
            </div>
          )}

          {step === 3 && (
            <div>
              <h2 className="mb-3 text-xl font-semibold">Проверка</h2>
              <p className="mb-4 text-sm text-subtext">
                Нажми кнопку и скажи что-нибудь — запись идёт 4 секунды.
              </p>
              <button
                onClick={() => void runTest()}
                disabled={testing || !engineReady}
                className="mb-4 rounded-lg bg-amber px-4 py-2 text-sm font-medium text-base disabled:opacity-50"
              >
                {testing ? "🔴 Говорите…" : "Начать проверку"}
              </button>
              {testResult && (
                <div className="rounded-lg bg-raised p-3 text-sm">
                  {testResult.type === "text" ? (
                    <span className="text-moss">«{testResult.text}»</span>
                  ) : (
                    <span className="text-subtext">Речь не распознана — попробуй ещё раз</span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-6 flex justify-between">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="rounded-lg px-4 py-2 text-sm text-subtext hover:bg-raised disabled:opacity-0"
          >
            Назад
          </button>
          {step < STEPS.length - 1 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              className="rounded-lg bg-amber px-4 py-2 text-sm font-medium text-base"
            >
              Дальше
            </button>
          ) : (
            <button
              onClick={onDone}
              className="rounded-lg bg-moss px-4 py-2 text-sm font-medium text-base"
            >
              Готово 🚀
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
