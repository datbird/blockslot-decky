/**
 * The full Blockslot page, reached from the Quick Access panel.
 *
 * Same five sections as the desktop window, in the shape Steam gives a page:
 * a rail on the left, one section at a time on the right. The Quick Access
 * panel keeps only the thing you want mid-session, which is flipping sync on
 * for the game you are about to play.
 */

import {
  ConfirmModal,
  DialogButton,
  Dropdown,
  Field,
  Focusable,
  PanelSection,
  PanelSectionRow,
  showModal,
  SidebarNavigation,
  ToggleField,
} from "@decky/ui";
import { FC, useEffect, useState } from "react";

import {
  call,
  EngineState,
  Game,
  LogLine,
  SaveSet,
  setSync,
  Step,
  SyncSettings,
} from "./api";
import { SafeButton, Text } from "./controls";

const GOOD = "#57d364";
const WARN = "#e3b341";
const BAD = "#f2685c";

/** A line of state: a coloured dot, what it is, and what it says. */
const State: FC<{ ok: boolean; label: string; detail?: string }> = ({
  ok,
  label,
  detail,
}) => (
  <Field
    label={
      <span>
        <span style={{ color: ok ? GOOD : WARN, marginRight: "8px" }}>
          {ok ? "●" : "○"}
        </span>
        {label}
      </span>
    }
    description={detail}
    bottomSeparator="standard"
  />
);

// ------------------------------------------------------------------ games

/** Show the library at once, then again with what the hub holds. */
export async function loadWithHub(
  load: () => Promise<void>,
  setBusy: (text: string) => void
) {
  setBusy("Reading your library ...");
  await load();
  setBusy("Asking the hub what it has ...");
  await call("read_hub");
  await load();
  setBusy("");
}

/** Turning sync on or off for one row, the same from the panel and the page. */
export function useSyncToggle(
  setGames: (update: (rows: Game[]) => Game[]) => void,
  setNote: (text: string) => void
) {
  const flip = async (game: Game, on: boolean, saveSet?: string) => {
    setNote("");
    const answer = await setSync(game, on, saveSet);
    if (answer.chooseSet) {
      showModal(
        <ChooseSet
          game={game}
          sets={answer.chooseSet}
          onPick={(name) => flip(game, on, name)}
        />
      );
      return;
    }
    if (answer.error) {
      setNote(answer.error);
      return;
    }
    setGames((rows) =>
      rows.map((row) => (row.appid === game.appid ? { ...row, on } : row))
    );
    setNote(
      on
        ? game.name + " will sync from its next launch."
        : game.name + " is no longer synced."
    );
  };
  return flip;
}

/** One toggle per game. Turning one off asks first, turning one on does not. */
export const GameRows: FC<{
  games: Game[];
  busy: string;
  flip: (game: Game, on: boolean) => void;
}> = ({ games, busy, flip }) => (
  <>
    {games.map((game) => (
      <PanelSectionRow key={game.appid}>
        <ToggleField
          label={game.name}
          description={describe(game)}
          checked={game.on}
          onChange={(value: boolean) => {
            if (!value && game.on) {
              showModal(
                <ConfirmModal
                  strTitle={"Stop syncing " + game.name + "?"}
                  strDescription={
                    "Its saves stay where they are, here and on the hub. " +
                    "They just stop being carried between your machines."
                  }
                  strOKButtonText="Stop syncing"
                  onOK={() => flip(game, false)}
                />
              );
              return;
            }
            flip(game, value);
          }}
        />
      </PanelSectionRow>
    ))}
    {games.length === 0 && !busy ? (
      <PanelSectionRow>
        <Field
          label="Nothing to show"
          description="Every installed game is covered by Steam Cloud."
        />
      </PanelSectionRow>
    ) : null}
  </>
);

const GamesPage: FC = () => {
  const [games, setGames] = useState<Game[]>([]);
  const [hideCloud, setHideCloud] = useState(true);
  const [busy, setBusy] = useState("Reading your library ...");
  const [note, setNote] = useState("");
  const flip = useSyncToggle(setGames, setNote);

  const load = async (includeCloud: boolean) => {
    const answer = await call<any>("games", includeCloud);
    if (answer?.games) setGames(answer.games);
  };

  useEffect(() => {
    loadWithHub(() => load(!hideCloud), setBusy);
  }, []);

  return (
    <>
      <PanelSection title="Games">
        <PanelSectionRow>
          <ToggleField
            label="Hide games Steam Cloud covers"
            description="Steam already carries those. This tool is for the rest."
            checked={hideCloud}
            onChange={async (value: boolean) => {
              setHideCloud(value);
              setBusy("Reading ...");
              await load(!value);
              setBusy("");
            }}
          />
        </PanelSectionRow>
        {busy ? (
          <PanelSectionRow>
            <Field label={busy} />
          </PanelSectionRow>
        ) : null}
        {note ? (
          <PanelSectionRow>
            <Field label={note} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
      <PanelSection>
        <GameRows games={games} busy={busy} flip={flip} />
      </PanelSection>
    </>
  );
};

/** The line under a game: where its save last landed, or why it cannot sync. */
function describe(game: Game): string {
  const parts: string[] = [];
  if (game.hub) {
    parts.push(
      "hub has " + game.hub + (game.hub_device ? " from " + game.hub_device : "")
    );
  } else {
    parts.push("nothing on the hub yet");
  }
  if (game.set) parts.push("set: " + game.set);
  if (game.cloud) parts.push("Steam Cloud covers this");
  if (game.shortcut && !game.set) parts.push("it will ask which save set it uses");
  return parts.join("   ");
}

/** Ask which save set a non-Steam game owns. Its app id tells savepick nothing. */
const ChooseSet: FC<{
  game: Game;
  sets: string[];
  onPick: (name: string) => void;
  closeModal?: () => void;
}> = ({ game, sets, onPick, closeModal }) => (
  <ConfirmModal
    strTitle={"Which saves does " + game.name + " use?"}
    strDescription={
      game.name + " is not a Steam game, so its app id says nothing about saves."
    }
    bAlertDialog={true}
    strOKButtonText="Cancel"
    onOK={() => closeModal?.()}
  >
    <Focusable style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {sets.map((name) => (
        <DialogButton
          key={name}
          onClick={() => {
            closeModal?.();
            onPick(name);
          }}
        >
          {name}
        </DialogButton>
      ))}
    </Focusable>
  </ConfirmModal>
);

// ------------------------------------------------------------------- sync

const SyncPage: FC = () => {
  const [values, setValues] = useState<SyncSettings | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [note, setNote] = useState("");

  const field = (key: keyof SyncSettings) => (text: string) =>
    setValues((old) => (old ? { ...old, [key]: text } : old));

  useEffect(() => {
    (async () => {
      setValues(await call<SyncSettings>("sync_settings"));
      const answer = await call<any>("status");
      if (answer?.steps) setSteps(answer.steps);
    })();
  }, []);

  const save = async () => {
    if (!values) return;
    setNote("Saving ...");
    const answer = await call<any>("save_sync", values);
    if (!answer?.ok) {
      setNote(answer?.error || "Could not save.");
      return;
    }
    setSteps(answer.steps || []);
    setNote("Saved.");
  };

  if (!values) return <PanelSection title="Sync" />;

  return (
    <>
      <PanelSection title="What is working">
        {steps.map((step) => (
          <PanelSectionRow key={step.label}>
            <State ok={step.ok} label={step.label} detail={step.detail} />
          </PanelSectionRow>
        ))}
      </PanelSection>
      <PanelSection title="The server to use">
        <PanelSectionRow>
          <Text
            label="Syncthing address"
            value={values.url}
            onChange={field("url")}
            onEnter={save}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Text
            label="API key"
            value={values.apikey}
            onChange={field("apikey")}
            password
            description="Syncthing shows this under Actions, Settings."
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Text label="Folder id" value={values.folder} onChange={field("folder")} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Text label="Hub name" value={values.hub_name} onChange={field("hub_name")} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Text label="Hub device id" value={values.hub_id} onChange={field("hub_id")} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Text
            label="This device's folder inside the share"
            value={values.device_dir}
            onChange={field("device_dir")}
            description="Each device owns one folder in the shared folder."
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Focusable style={{ display: "flex", gap: "8px" }}>
            <SafeButton primary onClick={save}>
              Save and test
            </SafeButton>
          </Focusable>
        </PanelSectionRow>
        {note ? (
          <PanelSectionRow>
            <Field label={note} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    </>
  );
};

// -------------------------------------------------------------- save sets

const SetsPage: FC = () => {
  const [sets, setSets] = useState<SaveSet[]>([]);
  const [picked, setPicked] = useState<string>("");
  const [folder, setFolder] = useState("");
  const [name, setName] = useState("");
  const [everyFile, setEveryFile] = useState(false);
  const [note, setNote] = useState("");

  const load = async () => {
    const answer = await call<any>("sets");
    const rows: SaveSet[] = answer?.sets || [];
    setSets(rows);
    if (rows.length && !rows.some((row) => row.name === picked)) {
      setPicked(rows[0].name);
      setFolder(rows[0].root);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const current = sets.find((row) => row.name === picked);

  return (
    <>
      <PanelSection title="Save sets">
        <PanelSectionRow>
          <Field
            label="What these are for"
            description={
              "One per launcher or non-Steam game: a name, and the folder its " +
              "saves live in on THIS device. Steam games need none of this."
            }
          />
        </PanelSectionRow>
        {sets.length ? (
          <PanelSectionRow>
            <Dropdown
              rgOptions={sets.map((row) => ({
                data: row.name,
                label: row.name + (row.root ? "" : "   no folder here"),
              }))}
              selectedOption={picked}
              onChange={(option: any) => {
                setPicked(option.data);
                setFolder(
                  sets.find((row) => row.name === option.data)?.root || ""
                );
                setNote("");
              }}
            />
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <Field label="None yet" />
          </PanelSectionRow>
        )}
        {current ? (
          <>
            <PanelSectionRow>
              <State
                ok={!!current.root}
                label={
                  current.root
                    ? "Ready on this device"
                    : "This device has no folder for it"
                }
                detail={current.devices + " device(s) know this set"}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <Text
                label="Its folder on this device"
                value={folder}
                onChange={setFolder}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <Focusable style={{ display: "flex", gap: "8px" }}>
                <SafeButton
                  primary
                  onClick={async () => {
                    const answer = await call<any>("set_root", picked, folder);
                    setNote(
                      answer?.ok
                        ? answer.exists
                          ? "Saved."
                          : "Saved, but that folder is not there yet."
                        : answer?.error || "Could not save."
                    );
                    load();
                  }}
                >
                  Save the folder
                </SafeButton>
                <SafeButton
                  onClick={() =>
                    showModal(
                      <ConfirmModal
                        strTitle={"Remove " + picked + "?"}
                        strDescription={
                          "No save file is touched and no other device changes. " +
                          "Any game using it stops syncing until it is given another."
                        }
                        strOKButtonText="Remove it"
                        onOK={async () => {
                          await call("remove_set", picked);
                          setPicked("");
                          load();
                        }}
                      />
                    )
                  }
                >
                  Remove
                </SafeButton>
              </Focusable>
            </PanelSectionRow>
          </>
        ) : null}
        {note ? (
          <PanelSectionRow>
            <Field label={note} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title="New save set">
        <PanelSectionRow>
          <Text label="Name" value={name} onChange={setName} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="One game's own save folder"
            description={
              "On: every file in the folder is save data, which is what a " +
              "console game needs. Off: a launcher, where only files that look " +
              "like saves are carried."
            }
            checked={everyFile}
            onChange={setEveryFile}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Focusable>
            <SafeButton
              disabled={!name.trim()}
              onClick={async () => {
                const answer = await call<any>("add_set", name, everyFile);
                setNote(answer?.ok ? "Added " + name + "." : answer?.error || "");
                if (answer?.ok) {
                  setPicked(name.trim());
                  setName("");
                  load();
                }
              }}
            >
              Add it
            </SafeButton>
          </Focusable>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};

// --------------------------------------------------------------- settings

const SettingsPage: FC = () => {
  const [state, setState] = useState<EngineState | null>(null);
  const [device, setDevice] = useState("");
  const [note, setNote] = useState("");

  const load = async () => {
    const answer = await call<EngineState>("engine_state");
    setState(answer);
    return answer;
  };

  useEffect(() => {
    load().then((answer) => setDevice(answer?.device_name || ""));
  }, []);

  if (!state) return <PanelSection title="Settings" />;

  return (
    <>
      <PanelSection title="This device">
        <PanelSectionRow>
          <Text
            label="What to call this device"
            value={device}
            onChange={setDevice}
            description="What the other devices call it when they report a save."
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Focusable>
            <SafeButton
              primary
              onClick={async () => {
                const answer = await call<any>("set_device_name", device);
                setNote(answer?.ok ? "Saved." : answer?.error || "Could not save.");
              }}
            >
              Save
            </SafeButton>
          </Focusable>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="The engine">
        <PanelSectionRow>
          <State
            ok={state.installed && state.current}
            label={
              !state.installed
                ? "Not installed. Nothing syncs until it is."
                : state.current
                ? "Installed and up to date"
                : "Installed, but older than this plugin's copy"
            }
            detail={state.engine}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label="What it does"
            description={
              "savepick is the part that works. Steam starts it instead of the " +
              "game, it brings the newest save down first, and it backs the save " +
              "up when you quit."
            }
          />
        </PanelSectionRow>
        {state.have_source ? (
          <PanelSectionRow>
            <Focusable>
              <SafeButton
                onClick={async () => {
                  const answer = await call<any>("install_engine");
                  setNote(answer?.ok ? "Engine installed." : answer?.error || "");
                  load();
                }}
              >
                {!state.installed
                  ? "Install it"
                  : state.current
                  ? "Reinstall it"
                  : "Update it"}
              </SafeButton>
            </Focusable>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title="Everything else">
        <PanelSectionRow>
          <State
            ok={state.ludusavi_found}
            label={state.ludusavi_found ? "ludusavi found" : "ludusavi missing"}
            detail={state.ludusavi}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label="What it does"
            description={
              "ludusavi knows where games keep their saves and does every copy. " +
              "Blockslot installs its official 0.31.0 release. That release " +
              "cannot yet match a Windows save path to a Proton one, so a save " +
              "moves between SteamOS devices today, and between SteamOS and " +
              "Windows once ludusavi releases that."
            }
          />
        </PanelSectionRow>
        {!state.ludusavi_found && state.ludusavi_archive ? (
          <PanelSectionRow>
            <Focusable>
              <SafeButton
                primary
                onClick={async () => {
                  setNote("Installing ludusavi ...");
                  const answer = await call<any>("install_ludusavi");
                  setNote(
                    answer?.ok ? "ludusavi installed." : answer?.error || "Could not install it."
                  );
                  load();
                }}
              >
                Install ludusavi
              </SafeButton>
            </Focusable>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <Field label="Settings file" description={state.settings_file} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Log" description={state.log} />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Steam" description={state.steam || "not found"} />
        </PanelSectionRow>
        {note ? (
          <PanelSectionRow>
            <Field label={note} bottomSeparator="none" />
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    </>
  );
};

// --------------------------------------------------------------- activity

const ActivityPage: FC = () => {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [where, setWhere] = useState("");

  const load = async () => {
    const answer = await call<any>("log_tail", 120);
    setLines(answer?.lines || []);
    setWhere(answer?.path || "");
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <PanelSection title="Activity">
      <PanelSectionRow>
        <Field
          label={where || "no log yet"}
          description="What the engine did, in its own words."
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <Focusable
          style={{
            maxHeight: "60vh",
            overflowY: "scroll",
            fontFamily: "monospace",
            fontSize: "12px",
            lineHeight: "1.5",
            background: "#0e1117",
            padding: "8px",
            borderRadius: "4px",
          }}
        >
          {lines.length === 0 ? (
            <div>Nothing yet. The log appears the first time a game starts.</div>
          ) : (
            lines.map((line, index) => (
              <div key={index} style={{ color: COLOUR[line.kind] || "#c7d1db" }}>
                {line.text}
              </div>
            ))
          )}
        </Focusable>
      </PanelSectionRow>
    </PanelSection>
  );
};

/** The backend says what kind of line it is. This only picks the colour. */
const COLOUR: Record<string, string> = { bad: BAD, warn: WARN, good: GOOD };

// ------------------------------------------------------------------- page

export const BlockslotPage: FC = () => (
  <SidebarNavigation
    title="Blockslot"
    showTitle
    pages={[
      { title: "Games", content: <GamesPage />, route: "/blockslot/games" },
      { title: "Sync", content: <SyncPage />, route: "/blockslot/sync" },
      { title: "Save sets", content: <SetsPage />, route: "/blockslot/sets" },
      { title: "Settings", content: <SettingsPage />, route: "/blockslot/settings" },
      { title: "Activity", content: <ActivityPage />, route: "/blockslot/activity" },
    ]}
  />
);
