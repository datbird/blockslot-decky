/**
 * Blockslot in the Quick Access menu, and the full page behind it.
 *
 * The panel keeps only what you want mid-session: is sync working, and turn it
 * on for the game you are about to play. Everything the desktop window has
 * lives on the full page, which the panel opens.
 *
 * Every write of a launch option goes through Steam, never through the file.
 * Steam holds localconfig.vdf in memory and writes it out on exit, so an edit
 * to the file from inside Steam is thrown away. See `api.ts`.
 */

import { definePlugin, routerHook } from "@decky/api";
import {
  ButtonItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { useEffect, useState, FC } from "react";

import { call, Game, Step } from "./api";
import { BlockslotPage, GameRows, loadWithHub, useSyncToggle } from "./pages";

const ROUTE = "/blockslot";

const Panel: FC = () => {
  const [games, setGames] = useState<Game[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [device, setDevice] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const flip = useSyncToggle(setGames, setNote);

  const loadGames = async () => {
    const answer = await call<any>("games");
    if (answer?.games) setGames(answer.games);
  };

  const loadStatus = async () => {
    const answer = await call<any>("status");
    if (answer) {
      setSteps(answer.steps || []);
      setDevice(answer.device || "");
    }
  };

  useEffect(() => {
    (async () => {
      setBusy("Reading your library ...");
      await loadStatus();
      await loadWithHub(loadGames, setBusy);
    })();
  }, []);

  const broken = steps.filter((step) => !step.ok);

  return (
    <>
      <PanelSection title={device ? "This device: " + device : "Blockslot"}>
        {busy ? (
          <PanelSectionRow>
            <Field label={busy} />
          </PanelSectionRow>
        ) : null}
        {!busy && broken.length === 0 ? (
          <PanelSectionRow>
            <Field label="Sync is working" bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
        {broken.map((step) => (
          <PanelSectionRow key={step.label}>
            <Field label={step.label} description={step.detail} />
          </PanelSectionRow>
        ))}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              Navigation.CloseSideMenus();
              Navigation.Navigate(ROUTE);
            }}
          >
            Open Blockslot
          </ButtonItem>
        </PanelSectionRow>
        {note ? (
          <PanelSectionRow>
            <Field label={note} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title="Games Steam Cloud does not cover">
        <GameRows games={games} busy={busy} flip={flip} />
      </PanelSection>
    </>
  );
};

export default definePlugin(() => {
  routerHook.addRoute(ROUTE, BlockslotPage, { exact: false });
  return {
    name: "Blockslot",
    titleView: <div className={staticClasses.Title}>Blockslot</div>,
    content: <Panel />,
    icon: <BlockslotIcon />,
    onDismount() {
      routerHook.removeRoute(ROUTE);
    },
  };
});

/** The same mark the desktop window uses: a block above a slot. */
function BlockslotIcon() {
  return (
    <svg viewBox="0 0 32 32" width="1em" height="1em" fill="currentColor">
      <rect x="11" y="5" width="10" height="7" rx="2" />
      <path d="M4 16h24v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V16zm8 4h8a2 2 0 0 1 0 4h-8a2 2 0 0 1 0-4z" />
    </svg>
  );
}
