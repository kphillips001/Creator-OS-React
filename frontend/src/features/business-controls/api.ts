import type { RelationshipSort } from "../relationships/api";

export type CustomerInventoryFilter = "ALL" | "BUYERS" | "PROSPECTS" | "TELEGRAM" | "FANVUE" | "X";
export type CustomerSnapshotItem = { item_id:string; subject_type:string; subject_id:string; section:string; label:string; description:string; value:unknown; attributes:Record<string,unknown>; source_authority:string; source_platform:string; confidence:number; usage_policy:string; lifecycle_status:string; observed_at:string|null; last_observed_at:string|null; correctable:boolean; native_reference:Record<string,string>; inferred:boolean; exclusion_reason:string|null };
export type CustomerSnapshot = { identity_summary:Record<string,string|null>; sections:Record<string,CustomerSnapshotItem[]>; excluded_items:CustomerSnapshotItem[]; sources:string[]; mapping_state:string };
export type IntelligenceProposal = { proposalId:string; label:string; meaning:string; subjectLabel:string; sourceLabel:string; usagePolicy:string; validationState:"READY"|"ALREADY_KNOWN"|"CONFLICT"|"NEEDS_CORRECTION"|"NEEDS_REVIEW"; warnings:string[]; current?:{label:string;attributes:Record<string,unknown>} };
export type IntelligencePreview = { mutationPerformed:false; providerCalls:number; parser:string; proposals:IntelligenceProposal[] };
export type CustomerInventoryItem = {
  rowKey: string; rowKind: "CANONICAL_CUSTOMER" | "TELEGRAM_PROSPECT";
  operationalEligibilityReason?: "PRIVATE_TELEGRAM_RELATIONSHIP" | "VERIFIED_EXTERNAL_MAPPING" | "EXPLICIT_OPERATOR_ONBOARDING" | "CANONICAL_INTELLIGENCE" | "OTHER_CERTIFIED_REASON";
  personKey: string; localFanvueUserId: number | null; displayName: string; username: string | null;
  metadataComplete: boolean; providerEvidenceAvailable: boolean;
  telegramObservation?: { sources:string[]; sourceChannelId:number|null; privateChatEstablished:boolean; participantStatus:string|null };
  platforms: { fanvue: string; telegram: string; x: string };
  identityStatus: string; buyerStatus: "BUYER" | "PROSPECT"; isBuyer: boolean;
  commerce: { lifetimeGrossMinor: number | null; lifetimeNetMinor: number | null; purchaseCount: number; firstPurchaseAt: string | null; lastPurchaseAt: string | null; lastSyncedAt: string | null; ownedAssetCount?: number };
  lifetimeVerifiedRevenueMinor: number | null; qualifyingPurchaseCount: number;
  controlAvailability: "AVAILABLE" | "UNAVAILABLE";
  controls: { avaChatEnabled: boolean; contentSellingEnabled: boolean; sessionSellingEnabled: boolean } | null;
  relationshipKey: string | null; hasConversation: boolean; telegramUserId: number | null; xNumericId: string | null; xLinkId?: string | null; latestActivityAt: string | null;
  activePurchaseIntent: boolean; activeSalesSession: boolean;
};
type CustomerInventoryList = { items: CustomerInventoryItem[]; total: number; page: number; pageSize: number };

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
  display: () => request<GlobalControls>("/api/v1/operations/global-controls/display-status"),
  relationshipFacts: (customerId: number) => request<unknown[]>(`/api/v1/operations/relationship-facts?customer_id=${customerId}`),
  contextPreview: (customerId: number, message: string) => request<Record<string, any>>(`/api/v1/operations/relationship-context-preview?customer_id=${customerId}&message=${encodeURIComponent(message)}`),
  customerSnapshot: (key:{customerId?:number;telegramUserId?:number|string}) => request<CustomerSnapshot>(`/api/v1/operations/customer-snapshot?${key.customerId!=null?`customer_id=${key.customerId}`:`telegram_user_id=${key.telegramUserId}`}`),
  previewNaturalIntelligence: (body:{customerId:number;customerName:string;text:string;sourceType:string}) => request<IntelligencePreview>(`/api/v1/operations/intelligence/natural-language/preview`,json("POST",body)),
  applyNaturalIntelligence: (body:{customerId:number;customerName:string;text:string;sourceType:string;selectedProposalIds:string[];silentProposalIds:string[]}) => request<{success:boolean;createdCount:number}>(`/api/v1/operations/intelligence/natural-language/apply`,json("POST",body)),
  metadataPreview: (customerId: number) => request<Record<string, any>>(`/api/v1/operations/customer-identity/fanvue/${customerId}/metadata-enrichment-preview`),
  applyMetadata: (customerId: number) => request<Record<string, any>>(`/api/v1/operations/customer-identity/fanvue/${customerId}/metadata-enrichment`, json("POST")),
  telegramReadiness: () => request<Record<string, any>>(`/api/v1/operations/telegram-identity-readiness`),
  findTelegramSubscribers: (search:string) => request<Record<string, any>>(`/api/v1/operations/telegram-identity/broadcast-members?search=${encodeURIComponent(search)}&limit=20`),
  persistTelegramObservation: (body:Record<string,unknown>) => request<Record<string, any>>(`/api/v1/operations/telegram-identity/broadcast-observations`,json("POST",body)),
  verifyTelegram: (telegramUserId: string, localFanvueUserId: number, verificationNote: string) => request<Record<string, any>>(`/api/v1/operations/telegram-identity-readiness/${telegramUserId}/verify`, json("POST", { localFanvueUserId, verificationNote })),
  previewTelegram: (telegramUserId: string, localFanvueUserId: number) => request<Record<string, any>>(`/api/v1/operations/telegram-identity-readiness/${telegramUserId}/preview`, json("POST", { localFanvueUserId, verificationNote: "Preview only; no mutation." })),
  xObservations: () => request<any[]>(`/api/v1/operations/customer-identity/x/observations`),
  previewX: (body: Record<string, unknown>) => request<Record<string, any>>(`/api/v1/operations/customer-identity/x/preview`, json("POST", body)),
  verifyX: (body: Record<string, unknown>) => request<Record<string, any>>(`/api/v1/operations/customer-identity/x/verify`, json("POST", body)),
  deactivateX: (linkId: string, reason: string) => request<Record<string, any>>(`/api/v1/operations/customer-identity/x/${linkId}/deactivate`, json("POST", { reason })),
  previewFact: (body: Record<string, unknown>) => request<Record<string, any>>(`/api/v1/operations/relationship-facts/preview`, json("POST", body)),
  createFact: (body: Record<string, unknown>) => request<Record<string, any>>(`/api/v1/operations/relationship-facts`, json("POST", body)),
  correctFact: (factId: string, replacement: Record<string, unknown>, reason: string) => request<Record<string, any>>(`/api/v1/operations/relationship-facts/${factId}/correct`, json("POST", { replacement, reason })),
  deactivateFact: (factId: string, reason: string) => request<Record<string, any>>(`/api/v1/operations/relationship-facts/${factId}/deactivate`, json("POST", { reason })),
  factHistory: (factId: string) => request<Record<string, any>>(`/api/v1/operations/relationship-facts/${factId}/history`),
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
  inventory: (
    search = "",
    sort: RelationshipSort = "LATEST_ACTIVITY",
    filter: CustomerInventoryFilter = "ALL",
  ) => {
    const query = new URLSearchParams({ page_size: "100", sort, filter });
    if (search) query.set("search", search);
    return request<CustomerInventoryList>(`/api/v1/operations/customer-controls-inventory?${query}`);
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
  person: CustomerInventoryItem;
  controls: CustomerControls | null;
  error?: string;
};
