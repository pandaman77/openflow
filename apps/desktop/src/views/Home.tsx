import { useAppStore } from "../stores/app";
import Wave from "../components/Wave";

/** Home: one hero answer — can I dictate right now? — then details. */
export default function Home() {
  const { engineReady, engineError, engineInfo, recording, lastResult, hotkeys, config } =
    useAppStore();

  const status = recording
    ? { title: "Идёт запись", sub: "Отпусти хоткей — текст вставится сам", wave: "hot" as const }
    : engineError
      ? { title: "Движок не запустился", sub: engineError, wave: "quiet" as const }
      : engineReady
        ? { title: "Готов к диктовке", sub: "Зажми хоткей в любом приложении и говори", wave: "ready" as const }
        : { title: "Прогреваю движок…", sub: "Загружаю модель распознавания — при первом запуске это займёт до минуты", wave: "quiet" as const };

  return (
    <div className="mx-auto max-w-2xl">
      {/* hero: the one thing that matters */}
      <section className="rounded-lg border border-line bg-surface">
        <div className="px-6 pb-2 pt-6">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            {status.title}
          </h1>
          <p className={`mt-2 text-sm ${engineError ? "text-coral" : "text-subtext"}`}>
            {status.sub}
          </p>
        </div>
        <Wave state={status.wave} height={44} className="mt-2" />
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-line px-6 py-3">
          <Fact label="распознавание" value={engineInfo?.stt_device === "cuda" ? "GPU · CUDA" : engineInfo?.stt_device === "cpu" ? "CPU" : "—"} />
          <Fact label="очистка" value={config?.cleanup.mode === "smart" ? "умная (ИИ)" : config?.cleanup.mode === "literal" ? "как сказано" : "быстрая"} />
          <Fact
            label="умный режим"
            value={engineInfo?.smart_available ? "доступен" : "нет модели"}
            dim={!engineInfo?.smart_available}
          />
        </div>
      </section>

      {/* how to */}
      <section className="mt-5 rounded-lg border border-line bg-surface px-6 py-5">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtext">
          Как диктовать
        </h2>
        <div className="mt-3 space-y-2 text-sm leading-relaxed">
          <p>
            <Kbd>{prettyHotkey(hotkeys.ptt)}</Kbd> — зажал, говоришь, отпустил. Текст
            появится там, где стоит курсор.
          </p>
          <p className="text-subtext">
            <Kbd>{prettyHotkey(hotkeys.toggle)}</Kbd> — включить и выключить запись двумя
            нажатиями, если долго диктуешь.
          </p>
        </div>
      </section>

      {/* last dictation */}
      <section className="mt-5 rounded-lg border border-line bg-surface px-6 py-5">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtext">
          Последняя диктовка
        </h2>
        {lastResult ? (
          lastResult.type === "text" ? (
            <div className="mt-3">
              <p className="select-text text-sm leading-relaxed">«{lastResult.text}»</p>
              <p className="mt-2 font-mono text-[11px] text-subtext">
                {lastResult.language ?? "?"}
                {lastResult.timings?.stt !== undefined &&
                  ` · распознавание ${lastResult.timings.stt.toFixed(1)}с`}
                {lastResult.timings?.cleanup !== undefined &&
                  lastResult.timings.cleanup >= 0.05 &&
                  ` · очистка ${lastResult.timings.cleanup.toFixed(1)}с`}
              </p>
            </div>
          ) : lastResult.type === "command" ? (
            <p className="mt-3 text-sm">
              Команда: <span className="text-amber">{lastResult.action}</span>
            </p>
          ) : (
            <p className="mt-3 text-sm text-subtext">
              Речь не распозналась — попробуй ещё раз, чуть ближе к микрофону.
            </p>
          )
        ) : (
          <p className="mt-3 text-sm text-subtext">
            Пока пусто. Зажми <Kbd>{prettyHotkey(hotkeys.ptt)}</Kbd> и скажи что-нибудь —
            результат появится здесь.
          </p>
        )}
      </section>
    </div>
  );
}

function Fact({ label, value, dim }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-subtext">
        {label}
      </span>
      <span className={`text-sm ${dim ? "text-subtext" : "text-text"}`}>{value}</span>
    </div>
  );
}

function prettyHotkey(hotkey: string): string {
  return hotkey
    .split("+")
    .map((k) => ({ ctrl: "Ctrl", super: "Win", space: "Space", alt: "Alt", shift: "Shift" }[k] ?? k.toUpperCase()))
    .join(" + ");
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-line bg-raised px-1.5 py-0.5 font-mono text-xs text-amber">
      {children}
    </kbd>
  );
}
