import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { relaunch } from "@tauri-apps/plugin-process";
import type { Update } from "@tauri-apps/plugin-updater";
import { useAppStore } from "../stores/app";

const RELEASES_URL = "https://github.com/pandaman77/openflow/releases/latest";

type Stage =
  | { name: "offer" }
  | { name: "downloading"; got: number; total: number | null }
  | { name: "installing" }
  | { name: "failed"; message: string };

function mb(bytes: number): string {
  return `${Math.round(bytes / 1_048_576)} МБ`;
}

/** Checks for a new release on startup and installs it on request.
 *
 * Portable installs are a special case: the bundled installer would put a
 * second copy in %LOCALAPPDATA% instead of updating the folder the user
 * actually runs, so those get a download link instead of a button. */
export default function UpdateBanner() {
  const { update, updateDismissed, dismissUpdate } = useAppStore();
  const [stage, setStage] = useState<Stage>({ name: "offer" });
  const [portable, setPortable] = useState(false);

  useEffect(() => {
    void invoke("is_portable")
      .then((value) => setPortable(Boolean(value)))
      .catch(() => setPortable(false));
  }, []);

  // A newly found update starts from the offer again, even if a previous
  // attempt failed.
  useEffect(() => {
    if (update) setStage({ name: "offer" });
  }, [update]);

  const install = async (update: Update) => {
    let got = 0;
    let total: number | null = null;
    setStage({ name: "downloading", got: 0, total: null });
    try {
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") {
          total = event.data.contentLength ?? null;
          setStage({ name: "downloading", got: 0, total });
        } else if (event.event === "Progress") {
          got += event.data.chunkLength;
          setStage({ name: "downloading", got, total });
        } else if (event.event === "Finished") {
          setStage({ name: "installing" });
        }
      });
      await relaunch();
    } catch (err) {
      setStage({ name: "failed", message: String(err) });
    }
  };

  if (!update || updateDismissed) return null;

  const pct =
    stage.name === "downloading" && stage.total
      ? Math.min(100, Math.round((stage.got / stage.total) * 100))
      : null;

  return (
    <div className="mb-4 rounded-lg border border-amber/40 bg-amber/[0.07] px-4 py-3">
      {stage.name === "offer" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm">Вышла версия {update.version}</div>
            <div className="text-xs text-subtext">
              {portable
                ? "У тебя портативная версия — скачай новую и распакуй поверх."
                : "Обновление скачается и установится само, приложение перезапустится."}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={dismissUpdate}
              className="rounded-lg px-3 py-1.5 text-xs text-subtext hover:text-text"
            >
              Позже
            </button>
            {portable ? (
              <button
                onClick={() => void invoke("open_url", { url: RELEASES_URL })}
                className="rounded-lg bg-amber px-3 py-1.5 text-xs font-medium text-base"
              >
                Скачать
              </button>
            ) : (
              <button
                onClick={() => void install(update)}
                className="rounded-lg bg-amber px-3 py-1.5 text-xs font-medium text-base"
              >
                Обновить
              </button>
            )}
          </div>
        </div>
      )}

      {stage.name === "downloading" && (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span>Скачиваю обновление</span>
            <span className="font-mono text-xs tabular-nums text-subtext">
              {stage.total ? `${mb(stage.got)} из ${mb(stage.total)}` : mb(stage.got)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-raised">
            <div
              className={`h-full rounded-full bg-amber transition-[width] duration-300 ${
                pct === null ? "w-1/3 animate-pulse" : ""
              }`}
              style={pct === null ? undefined : { width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {stage.name === "installing" && (
        <div className="text-sm">Устанавливаю обновление, приложение сейчас перезапустится…</div>
      )}

      {stage.name === "failed" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm text-coral">Обновиться не получилось</div>
            <div className="text-xs text-subtext">{stage.message}</div>
          </div>
          <button
            onClick={() => void invoke("open_url", { url: RELEASES_URL })}
            className="rounded-lg bg-raised px-3 py-1.5 text-xs"
          >
            Скачать вручную
          </button>
        </div>
      )}
    </div>
  );
}
