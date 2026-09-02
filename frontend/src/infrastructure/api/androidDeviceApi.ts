export type AndroidDeviceState =
  | "CONNECTED"
  | "UNAUTHORIZED"
  | "OFFLINE"
  | "MULTIPLE_DEVICES"
  | "NOT_CONNECTED"
  | "ADB_NOT_AVAILABLE"
  | "ADB_TIMEOUT"
  | "ADB_ERROR";

export type AndroidDeviceStatus = {
  available: boolean;
  state: AndroidDeviceState;
  serial: string | null;
  model: string | null;
  manufacturer: string | null;
  adb_available: boolean;
  scrcpy_available: boolean;
  mirror_available: boolean;
  mirror_running: boolean;
  message: string | null;
};

export type AndroidMirrorResult = { result: "STARTED" | "ALREADY_OPEN"; serial: string };
export type AndroidSleepResult = { result: "SLEPT"; serial: string; mirror_closed: boolean };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/device/android${path}`, init);
  const body = await response.json().catch(() => null) as (T & { detail?: string }) | null;
  if (!response.ok || !body) throw new Error(body?.detail || "Unable to access the Android phone.");
  return body;
}

export const androidDeviceApi = {
  status: () => request<AndroidDeviceStatus>("/status"),
  mirror: () => request<AndroidMirrorResult>("/mirror", { method: "POST" }),
  sleep: () => request<AndroidSleepResult>("/sleep", { method: "POST" }),
};
