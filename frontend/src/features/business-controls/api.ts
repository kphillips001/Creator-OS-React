import type {
  Relationship,
  RelationshipFilter,
  RelationshipList,
  RelationshipSort,
} from "../relationships/api";

export type GlobalControls = {
  avaBot: {
    desired: "ON" | "OFF";
    effective: "ON" | "OFF" | "STARTING" | "ATTENTION";
    reason: string | null;
  };
  contentSellingEnabled: boolean;
  sessionSellingEnabled: boolean;
};

export type CustomerControls = {
  identity: {
    telegramUserId: number;
    telegramChatId: number | null;
  };
  configured: {
    avaChatEnabled: boolean;
    contentSellingEnabled: boolean;
    sessionSellingEnabled: boolean;
    relationshipMode: "AVA_AUTO" | "HUMAN_OPERATOR";
    controlVersion: number;
  };
  effective: {
    chatAllowed: boolean;
    chatReason: string | null;
    contentSellingAllowed: boolean;
    contentSellingReason: string | null;
    sessionSellingAllowed: boolean;
    sessionSellingReason: string | null;
  };
  global: {
    avaBotDesired: "ON" | "OFF";
    avaBotEffective: "ON" | "OFF" | "STARTING" | "ATTENTION";
    contentSellingEnabled: boolean;
    sessionSellingEnabled: boolean;
  };
};

type Transition<T> = { state: T };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  const body = (await response.json()) as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to update controls.");
  return body;
}

const json = (method: "PATCH" | "POST", body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

export const controlsApi = {
  global: () => request<GlobalControls>("/api/v1/operations/global-controls"),
  setAvaBot: (value: boolean) =>
    request<Transition<GlobalControls>>(
      `/api/v1/operations/global-controls/ava-bot/${value ? "turn-on" : "turn-off"}`,
      json("POST"),
    ),
  setGlobalContent: (value: boolean) =>
    request<Transition<GlobalControls>>(
      "/api/v1/operations/global-controls/content-selling",
      json("PATCH", { value }),
    ),
  setGlobalSession: (value: boolean) =>
    request<Transition<GlobalControls>>(
      "/api/v1/operations/global-controls/session-selling",
      json("PATCH", { value }),
    ),
  relationships: (
    search = "",
    sort: RelationshipSort = "LATEST_ACTIVITY",
    filter: RelationshipFilter = "ALL",
  ) => {
    const query = new URLSearchParams({ limit: "100", sort, filter });
    if (search) query.set("search", search);
    return request<RelationshipList>(`/api/v1/relationships?${query}`);
  },
  customer: (key: string) =>
    request<CustomerControls>(
      `/api/v1/relationships/${encodeURIComponent(key)}/automation-controls`,
    ),
  setCustomer: (
    key: string,
    control: "ava-chat" | "content-selling" | "session-selling",
    value: boolean,
  ) =>
    request<Transition<CustomerControls>>(
      `/api/v1/relationships/${encodeURIComponent(key)}/automation-controls/${control}`,
      json("PATCH", { value }),
    ),
};

export type CustomerControlRow = {
  person: Relationship;
  controls: CustomerControls | null;
  error?: string;
};
