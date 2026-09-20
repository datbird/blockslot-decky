/** Talking to the backend, and the shapes it answers with. */

import { call as backend } from "@decky/api";

export interface Game {
  appid: number;
  name: string;
  cloud: boolean | null;
  saves: boolean | null;
  on: boolean;
  set: string | null;
  shortcut: boolean;
  hub: string;
  hub_device: string;
}

export interface Step {
  label: string;
  ok: boolean;
  detail: string;
}

export interface LogLine {
  text: string;
  kind: "bad" | "warn" | "good" | "";
}

export interface SaveSet {
  name: string;
  root: string;
  devices: number;
}

export interface SyncSettings {
  url: string;
  apikey: string;
  folder: string;
  hub_id: string;
  hub_name: string;
  device_dir: string;
}

export interface EngineState {
  engine: string;
  installed: boolean;
  current: boolean;
  have_source: boolean;
  ludusavi: string;
  ludusavi_found: boolean;
  ludusavi_archive: boolean;
  device_name: string;
  settings_file: string;
  log: string;
  steam: string;
}

/**
 * Call a backend method. A failed call is null, never a thrown error.
 *
 * Arguments are positional, in the order main.py declares them. That is how
 * the loader hands them over, so a name here would mean nothing to it.
 */
export async function call<T = any>(method: string, ...args: any[]): Promise<T | null> {
  try {
    return await backend<any[], T>(method, ...args);
  } catch (error) {
    console.error("Blockslot: " + method + " failed", error);
    return null;
  }
}

/** Steam's own API, read loosely: the types ship a partial view of it. */
const steam = (): any => (window as any).SteamClient;

/**
 * What Steam currently has as this game's launch option.
 *
 * The file on disk is stale while Steam runs, so it is never the source here.
 * RegisterForAppDetails fires once with the current details, which is all this
 * needs, and the registration is dropped straight after.
 */
export async function currentLaunchOptions(appid: number): Promise<string> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (value: string) => {
      if (!done) {
        done = true;
        resolve(value);
      }
    };
    try {
      const handle = steam().Apps.RegisterForAppDetails(appid, (details: any) => {
        finish(details?.strLaunchOptions ?? "");
        try {
          handle.unregister();
        } catch (error) {
          try {
            (handle as any)();
          } catch (ignored) {
            /* some builds hand back a plain function */
          }
        }
      });
    } catch (error) {
      finish("");
    }
    // Never leave a toggle waiting on a callback that does not come.
    setTimeout(() => finish(""), 1500);
  });
}

/**
 * Turn sync on or off for one game.
 *
 * Steam is asked to set the option rather than the file being edited, because
 * Steam holds that file in memory and would write over any edit on exit.
 * Returns an error string, the word "choose" plus the sets to pick from, or
 * null when it worked.
 */
export async function setSync(
  game: Game,
  on: boolean,
  saveSet?: string
): Promise<{ error?: string; chooseSet?: string[] }> {
  const existing = await currentLaunchOptions(game.appid);
  const answer = await call<any>(
    "launch_option",
    game.appid,
    on,
    existing,
    saveSet ?? null
  );
  if (!answer?.ok) {
    if (answer?.choose_set?.length) return { chooseSet: answer.choose_set };
    return { error: answer?.error || "Could not work out what to set." };
  }
  try {
    steam().Apps.SetAppLaunchOptions(game.appid, answer.option);
  } catch (error) {
    return { error: "Steam refused the change: " + error };
  }
  return {};
}
