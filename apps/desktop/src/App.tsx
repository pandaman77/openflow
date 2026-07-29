import { useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { useAppStore } from "./stores/app";
import Settings from "./views/Settings";
import Onboarding from "./views/Onboarding";
import Home from "./views/Home";
import UpdateBanner from "./components/UpdateBanner";
import Wave from "./components/Wave";

type View = "home" | "settings" | "onboarding";

export default function App() {
  const init = useAppStore((s) => s.init);
  const { engineReady, engineError, recording } = useAppStore();
  const [view, setView] = useState<View>(
    localStorage.getItem("openflow.onboarded") ? "home" : "onboarding",
  );

  useEffect(() => {
    void init();
  }, [init]);

  if (view === "onboarding") {
    return (
      <Onboarding
        onDone={() => {
          localStorage.setItem("openflow.onboarded", "1");
          setView("home");
        }}
      />
    );
  }

  const waveState = recording ? "hot" : engineReady && !engineError ? "ready" : "quiet";

  return (
    <div className="studio-bg flex h-screen">
      <nav className="flex w-52 flex-col border-r border-line bg-surface">
        <div className="px-5 pb-4 pt-6">
          <div className="font-display text-lg font-semibold tracking-tight">
            OpenFlow
          </div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-subtext">
            голос → текст
          </div>
        </div>
        <Wave state={waveState} height={28} className="mb-4" />
        <div className="flex flex-col gap-1 px-3">
          <NavButton active={view === "home"} onClick={() => setView("home")}>
            Главная
          </NavButton>
          <NavButton active={view === "settings"} onClick={() => setView("settings")}>
            Настройки
          </NavButton>
        </div>
        <div className="mt-auto px-5 pb-5">
          <div className="font-mono text-[10px] leading-relaxed text-subtext">
            всё локально
            <br />
            ничего не уходит в сеть
          </div>
          <VersionFooter />
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto max-w-2xl">
          <UpdateBanner />
        </div>
        {view === "home" ? <Home /> : <Settings />}
      </main>
    </div>
  );
}

function NavButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-3 py-2 text-left text-sm transition-colors ${
        active
          ? "bg-amber-soft text-amber"
          : "text-subtext hover:bg-raised hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

type CheckState = "idle" | "checking" | "current" | "error";

/** Version plus a manual re-check. The automatic one runs at startup; this is
 *  for when someone knows a release just landed. A found update shows up in
 *  the banner, so there is only ever one place offering to install. */
function VersionFooter() {
  const [version, setVersion] = useState("");
  const [state, setState] = useState<CheckState>("idle");
  const { update, checkUpdate } = useAppStore();

  useEffect(() => {
    void getVersion().then(setVersion).catch(() => setVersion(""));
  }, []);

  const runCheck = async () => {
    setState("checking");
    const outcome = await checkUpdate();
    setState(outcome === "available" ? "idle" : outcome === "current" ? "current" : "error");
  };

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="font-mono text-[10px] text-subtext">
        OpenFlow v{version || "…"}
      </div>
      {update ? (
        <div className="mt-1 text-[10px] text-amber">Доступна v{update.version}</div>
      ) : (
        <button
          onClick={() => void runCheck()}
          disabled={state === "checking"}
          className="mt-1 text-[10px] text-subtext hover:text-text disabled:opacity-50"
        >
          {state === "checking"
            ? "Проверяю…"
            : state === "current"
              ? "Актуальная версия ✓"
              : state === "error"
                ? "Не удалось проверить"
                : "Проверить обновления"}
        </button>
      )}
    </div>
  );
}
