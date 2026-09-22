import { developerFetch } from "../../infrastructure/api/developerFetch";

export type OperationalStatus =
  | "REPLY_SCHEDULED"
  | "REPLY_READY"
  | "OVERDUE"
  | "SYSTEM_INCIDENT"
  | "DELIVERY_UNCERTAIN"
  | "RECOVERY_PENDING"
  | "NEEDS_ATTENTION"
  | "MANUAL_MODE"
  | "MEDIUM_MARKET_LIMIT"
  | "LOW_MARKET_LIMIT"
  | "IGNORED"
  | "NONE";
export type MarketTier = "HIGH" | "MEDIUM" | "LOW" | "UNCLASSIFIED";
export type MarketTierProjection = {
  marketTier: MarketTier;
  effectiveProspectInvestment:
    "MAXIMUM" | "HIGH" | "STANDARD" | "LOW" | "BUYER_AUTHORITY";
  highValueProspect: boolean;
  verifiedBuyer: boolean;
  repliesUsedToday: number;
  dailyReplyBudget: number | "FULL" | null;
  budgetStatus: "AVAILABLE" | "EXHAUSTED";
  effectiveResourceStatus?:
    "AVAILABLE" | "NURTURE_LIMIT" | "SALES_OVERRIDE" | "BUYER_AUTHORITY";
  activeSalesOpportunity?: {
    active: boolean;
    offer_status: string | null;
    offering_id: string | null;
    offer_title: string | null;
    configured_price_minor: number | null;
    currency: string | null;
    expires_at: string | null;
  };
  nextBudgetResetAt: string;
  prospectReplyLimit: "NOT_APPLICABLE" | null;
  changed?: boolean;
  scheduleAdvanced?: boolean;
  advancedOperation?: { operation_id: string; next_retry_at: string } | null;
};
export type OperationalProjection = {
  operationalStatus: OperationalStatus;
  operationalCategory?: string;
  automaticRecoveryEligible?: boolean;
  candidateBudgetRemaining?: number | null;
  candidateCount?: number | null;
  responseProviderAttempts?: number | null;
  latestInboundMessageId?: number | null;
  causalOperationId?: string | null;
  systemIncidentReason?: string | null;
  deliveryCertainty?: string;
  deliveryUncertaintyAcknowledged?: boolean;
  responseObligation?: { required: boolean; source: string; version: string };
  operatorAlertActive?: boolean;
  operationalStatusReason: string | null;
  nextAutomaticAttemptAt: string | null;
  pendingReplyPreview: string | null;
  overdueSince: string | null;
  operationState: string | null;
  operationId: string | null;
  inboundMessageId: number | null;
  generationAttempts: number;
  sendAttempts: number;
  hasActiveClaim: boolean;
  attentionOccurrenceId: string | null;
  attentionAcknowledgedAt: string | null;
  attentionAcknowledgedBy: string | null;
};
export type Relationship = Partial<OperationalProjection> & {
  personKey: string;
  telegramUserId: number;
  localFanvueUserId?: number | null;
  customerCommerceProfileId?: string | null;
  displayName: string;
  username: string | null;
  identityStatus: string;
  buyerStatus: string | null;
  lifetimeVerifiedRevenueMinor: number | null;
  qualifyingPurchaseCount: number | null;
  latestActivityAt: string;
  latestMessagePreview: string | null;
  latestSpeaker?: "CUSTOMER" | "AVA" | null;
  activePurchaseIntent: boolean;
  activeSalesSession: boolean;
  controlMode?: "AVA_AUTO" | "HUMAN_OPERATOR";
  needsAttention?: boolean;
  isBuyer?: boolean;
  lastCustomerInboundAt?: string | null;
  lastVisibleOutboundAt?: string | null;
  operatorClassification?: "HIGH_VALUE_PROSPECT" | null;
  highValueProspect?: boolean;
  effectiveAttentionPriority?: string;
  marketTier?: MarketTier;
  communicationDisposition?: "ACTIVE" | "IGNORED";
  ignored?: boolean;
  repliesUsedToday?: number;
  dailyReplyBudget?: number;
  nextResetAt?: string | null;
  timeWaster?: boolean;
  failedPresentationCount?: number;
  verifiedPurchaseCount?: number;
};
export type RelationshipMessage = {
  eventKey: string;
  direction: "CUSTOMER" | "AVA";
  content: string;
  timestamp: string;
  telegramMessageId: number | null;
  messageType: string;
  purchaseIntentId: string | null;
  origin?: "AI" | "HUMAN_OPERATOR";
};
export type RelationshipControl = {
  mode: "AVA_AUTO" | "HUMAN_OPERATOR";
  controlVersion: number;
  communicationDisposition?: "ACTIVE" | "IGNORED";
  ignored?: boolean;
  ignoreVersion?: number;
  ignoredAt?: string | null;
  ignoredBy?: string | null;
  unignoredAt?: string | null;
  unignoredBy?: string | null;
  resumeAfterInboundMessageId?: number | null;
  changedAt: string | null;
  changedBy: string;
  reason: string | null;
  lastManualActivityAt: string | null;
  activePurchaseIntent: boolean;
  activeSalesSession: boolean;
};
export type RelationshipSort =
  | "LATEST_ACTIVITY"
  | "LIFETIME_SPEND"
  | "COUNTRY_TIER_HIGH_TO_LOW"
  | "COUNTRY_TIER_LOW_TO_HIGH";
export type RelationshipFilter =
  | "ALL"
  | "NEEDS_ATTENTION"
  | "BUYERS"
  | "PROSPECTS"
  | "MANUAL"
  | "ACTIVE_SESSION"
  | "ACTIVE_INTENT"
  | "HIGH_VALUE_PROSPECT"
  | "IGNORED";
export type RelationshipSummary = {
  total: number;
  needsAttention: number;
  buyers: number;
  prospects: number;
  manual: number;
  replyScheduled?: number;
  highValueProspects?: number;
  ignored?: number;
};
export type RelationshipList = {
  items: Relationship[];
  nextCursor: string | null;
  hasMore: boolean;
  sort: RelationshipSort;
  filter?: RelationshipFilter;
  countryTiers?: MarketTier[];
  summary?: RelationshipSummary;
};
export type Transcript = {
  person?: Relationship;
  items: RelationshipMessage[];
  olderCursor: string | null;
  hasMoreOlder: boolean;
};
export type IntelligenceOffer = {
  title: string;
  type: string | null;
  priceMinor: number | null;
  presentedAt?: string | null;
  purchasedAt?: string | null;
  status?: string;
  ownershipStatus?: string;
};
export type OfferReadinessRequirement = {
  key: string;
  label: string;
  status: "SATISFIED" | "REMAINING" | "UNAVAILABLE";
  current: number | boolean | null;
  required: number | boolean | null;
  blocking: boolean;
  explanation: string;
};
export type OfferReadiness = {
  status: string;
  distance: string;
  qualifyingSignals: {
    sexualEngagementCount: number | null;
    sexualReceptivenessThreshold: number;
    sustainedSexualReceptiveness: boolean;
  };
  requirements: OfferReadinessRequirement[];
  hotPath: {
    label: string;
    status: "SATISFIED" | "BLOCKED" | "UNAVAILABLE";
    authorized: boolean;
    sustainedConversationSatisfied: boolean | null;
    sustainedConversationCount: number | null;
    sustainedConversationRequired: number | null;
    sustainedSexualReceptiveness: boolean | null;
    sexualEngagementCount: number | null;
    sexualEngagementRequired: number | null;
    currentHotToneQualified: boolean | null;
    noPriorPaidOfferExposure: boolean | null;
    commercialSafeguardsPassed: boolean | null;
    blockers: string[];
    reason: string | null;
    note: string;
  };
  bypass: { available: boolean; note: string };
  summary: string;
};
export type PPVEscalation = {
  stage:
    | "WARMING"
    | "COMMERCIAL_INTEREST"
    | "COMMERCIAL_EVALUATION"
    | "READY_TO_OFFER"
    | "OFFER_PRESENTED"
    | "AWAITING_PURCHASE"
    | "FOLLOW_UP_ELIGIBLE"
    | "NUDGE_SENT"
    | "BACKOFF"
    | "PURCHASED"
    | "COMMERCIAL_RE_ENTRY";
  warmupStatus: "IN_PROGRESS" | "COMPLETE" | "UNKNOWN" | "ALTERNATE_PATH";
  commercialSignal: string;
  commercialIntent: string;
  currentOffer: IntelligenceOffer | null;
  lastOffer: IntelligenceOffer | null;
  offerEligibility: string;
  purchaseIntentState: string;
  paidOffersPresented: number;
  verifiedPurchases: number | null;
  messagesSinceLastOffer: number | null;
  followUpStatus: string;
  nudgeStatus: string;
  backoffStatus: string;
  conversationPolicy: null | {
    responsePurpose: string | null;
    supporterBoundaryCommunicated: boolean;
    timeWaster: boolean;
    timeWasterReason: string | null;
    optionalReplyAllowance: number | null;
    optionalRepliesUsedToday: number | null;
    nextResetAt: string | null;
    sexualAccessGated: boolean;
    relationshipActive: boolean;
    commercialReentry: boolean;
  };
  nextAction: string;
  why: string;
  offerReadiness: OfferReadiness;
  evidence: {
    salesBrainDecision: string;
    salesBrainReason: string;
    freshCommercialIntentDetected: boolean;
    sexualEngagementDetected: boolean;
    sustainedSexualReceptiveness: boolean;
    proactiveProgressionAuthorized: boolean | null;
    proactiveHotOpportunityAuthorized: boolean | null;
    purchaseIntentPresent: boolean;
    confirmedPaidOfferPresent: boolean;
    followThroughAuthorityAvailable: boolean;
  };
};
export type RelationshipIntelligence = {
  person: Relationship;
  mappingStatus: "VERIFIED" | "UNMAPPED";
  partial: boolean;
  operatorClassification: "HIGH_VALUE_PROSPECT" | null;
  effectiveAttentionPriority: string;
  behavioralIntelligence: {
    buyingIntent: string;
    currentSignal: string;
    salesStage: string;
  };
  ppvEscalation: PPVEscalation;
  customerValue: {
    buyerStatus: string;
    valueTier: string | null;
    attentionTier: string | null;
    lifetimeSpendMinor: number | null;
    purchaseCount: number | null;
    repeatBuyer: boolean;
    relationshipLifecycle: string;
    relationshipInvestment: string;
    continuationValue: string;
    timeWasterRisk: string;
    timeWaster: boolean;
    failedPresentationCount: number;
    verifiedPurchaseCount: number;
    timeWasterThreshold: number;
    retention: string;
  };
  salesPerformance: {
    offersPresented: number;
    offersPurchased: number;
    offersNotPurchased: number;
    conversionRate: number | null;
    lastOffer: IntelligenceOffer | null;
    lastPurchase: IntelligenceOffer | null;
  };
  commercialState: {
    activePurchaseIntent: IntelligenceOffer | null;
    activeSalesSession: {
      state: string;
      stage: string;
      type: string | null;
    } | null;
    activeOffer: IntelligenceOffer | null;
  };
  purchaseHistory: IntelligenceOffer[];
  relationshipIntelligence: {
    location: string | null;
    timezone: string | null;
    interests: string[];
    pets: string[];
    music: string[];
    preferences: string[];
  };
};
export type OfferCard = { eligibilityReason?: string | null; ownershipEvidence?: string;
  offeringId: string;
  title: string;
  description: string | null;
  type: string;
  priceMinor: number;
  currency: string;
  thumbnailUrl: string;
  status: "AVAILABLE" | "OFFERED_BEFORE" | "ACTIVE_OFFER" | "PURCHASED";
  owned: boolean;
  eligible: boolean;
  presentationCount: number;
  recommended: boolean;
  activePurchaseIntentId: string | null;
};
export type OfferInventory = {
  items: OfferCard[];
  view: string;
  hidePurchased: boolean;
  businessConnectionId: string | null;
};
export type PreparedOffer = {
  offering: Pick<
    OfferCard,
    "offeringId" | "title" | "type" | "priceMinor" | "currency" | "thumbnailUrl"
  >;
  businessConnectionId: string | null;
  controlVersion: number;
  defaultMessage: string;
};
export type AttentionScope =
  | "CUSTOMER_ONLY"
  | "MULTIPLE_CUSTOMERS"
  | "GLOBAL_SYSTEM"
  | "OBSOLETE"
  | "AMBIGUOUS";
export type AttentionAction =
  | "ACKNOWLEDGE_ONLY"
  | "REQUEUE_CORRECTIVE_REPLY"
  | "RESOLVE_AS_SUPERSEDED"
  | "CONFIRM_DELIVERED"
  | "CONFIRM_NOT_DELIVERED"
  | "WAIT_FOR_AUTOMATION"
  | "REVIEW_SIMILAR_CASES"
  | "ESCALATE_GLOBAL_REPAIR"
  | "NO_AUTOMATED_RESOLUTION";
export type AttentionSimilarCase = {
  relationshipKey: string;
  attentionOccurrenceId: string;
  displayLabel: string;
};
export type AttentionInspectionResult = {
  schemaVersion: string;
  inspectionId: string;
  relationshipKey: string;
  attentionOccurrenceId: string;
  inspectedAt: string;
  whyFlagged: string;
  currentImpact: string;
  currentObligation: string;
  willAvaContinueAutomatically: boolean;
  avaAutoState: "ON" | "OFF" | "MANUAL";
  currentOperationState:
    | "REPLY_SCHEDULED"
    | "PROCESSING"
    | "NO_FURTHER_AUTOMATIC_ATTEMPT"
    | "COMPLETED"
    | "WAITING";
  isConditionStillRelevant: boolean;
  rootCauseScope: AttentionScope;
  rootCauseSummary: string;
  affectedCurrentCustomersCount: number;
  similarCurrentCases: AttentionSimilarCase[];
  futureCustomersPotentiallyAffected: boolean;
  globalRepairAlreadyExists: boolean;
  recommendedResolutionType: AttentionAction;
  recommendedResolutionSummary: string;
  operatorExplanation: string;
  exactProposedActions: string[];
  customerVisibleSendPossible: boolean;
  providerGenerationPossible: boolean;
  databaseChangeRequired: boolean;
  riskLevel: "LOW" | "MEDIUM" | "HIGH";
  approvalRequired: boolean;
  dispositionReason: string | null;
  confidence: number;
  inspectionWarnings: string[];
  cannotSafelyResolveReason: string | null;
  deliveryEvidence?: {
    providerAcceptanceEvidence: boolean;
    providerReadbackEvidence: boolean;
    destinationVerified: boolean;
    telegramMessageIdAvailable: boolean;
    presentationMode: string;
  };
  resolutionChoices?: Array<"CONFIRM_DELIVERED"|"CONFIRM_NOT_DELIVERED"|"LEAVE_UNRESOLVED">;
};
export type AttentionPlan = {
  plan_id: string;
  inspection_id: string;
  relationship_key: string;
  attention_occurrence_id: string;
  root_cause_scope: AttentionScope;
  action_type: AttentionAction;
  approval_state: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  execution_state: string;
  provider_generation_possible: boolean;
  customer_visible_send_possible: boolean;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  expires_at: string;
};
export type AttentionInspectionResponse = {
  inspection: { inspection_id: string };
  result: AttentionInspectionResult;
  plan: AttentionPlan | null;
};
export type AttentionExecution = {
  execution_id: string;
  plan_id: string;
  action_type: AttentionAction;
  status: "EXECUTING" | "SUCCEEDED" | "FAILED";
  result: Record<string, unknown> | null;
  completed_at: string | null;
};
export type ConversationFinding = {
  findingId: string;
  targetMessageReference: string;
  severity: "OK" | "MINOR" | "MATERIAL" | "CRITICAL";
  category: string;
  whatHappened: string;
  whyItIsProblematic: string;
  rootCauseCategory: string;
  validatedScope:
    | "CONVERSATION_ONLY"
    | "MULTIPLE_CUSTOMERS"
    | "GLOBAL_SYSTEM"
    | "OBSOLETE"
    | "AMBIGUOUS";
  confidence: number;
  similarCaseCount: number;
  suggestedCorrection: string;
  repairCandidate: boolean;
  proposedScope?: string;
  authorityConflict?: boolean;
  authoritativeEvidenceSummary?: string;
};
export type ConversationAnalysisResponse = {
  analysisId: string;
  staleState: "CURRENT" | "STALE";
  analysis: {
    overallQuality: string;
    conversationSummary: string;
    operatorSummary: string;
    validatedScope: string;
    globalRepairCandidate: boolean;
    analyzedAt?: string;
    relationshipKey?: string;
    schemaVersion?: string;
  };
  findings: ConversationFinding[];
  similarCaseSummary: { similarCaseCount: number; relationshipReferences?: string[]; searchBasis?: string };
};
export type RepairProposal = {
  proposal_id: string;
  analysis_id: string;
  finding_id: string;
  validated_scope: string;
  root_cause_category: string;
  failure_signature: string;
  affected_relationship_count: number;
  violated_invariant: string;
  proposed_invariant: string;
  expected_effect: string;
  preserved_behavior: string[];
  known_risks: string[];
  regression_requirements: string[];
  repair_category: string;
  risk: string;
  created_at: string;
  expires_at: string;
  status: string;
};
export type RepairExecution = {
  execution_id: string;
  state:
    | "AUTHORIZED"
    | "EXECUTING"
    | "TESTING"
    | "FAILED"
    | "STALE"
    | "EXPIRED"
    | "READY_FOR_DEPLOYMENT";
  workflow: string;
  baseline_sha: string;
  files_changed: string[];
  tests_result: unknown;
  failure_reason: string | null;
  ready_for_deployment_at: string | null;
};

async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { cache: "no-store", signal });
  const body = (await response.json()) as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load Chat.");
  return body;
}
async function command<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const contentType = response.headers.get("content-type")?.toLowerCase() || "";
  const raw = await response.text();
  type CommandResult = T & {
    detail?: string | { message?: string; code?: string; deliveryCertainty?: string };
  };
  let result: CommandResult | null = null;
  if (contentType.includes("application/json") && raw.trim()) {
    try {
      result = JSON.parse(raw) as CommandResult;
    } catch {
      throw new Error(`Relationship command returned invalid JSON (HTTP ${response.status}).`);
    }
  }
  if (!response.ok)
    throw new Error(
      typeof result?.detail === "string"
        ? result.detail
        : result?.detail?.message || raw.trim().slice(0, 300) ||
          `Relationship command failed (HTTP ${response.status}).`,
    );
  if (!result) throw new Error("Relationship command returned no JSON result.");
  return result;
}
async function developerRequest<T>(
  path: string,
  method = "GET",
  extraHeaders: Record<string, string> = {},
  body?: unknown,
): Promise<T> {
  const writes = method !== "GET";
  const headers = writes
    ? { "Content-Type": "application/json", ...extraHeaders }
    : extraHeaders;
  const response = await developerFetch(path, {
    method,
    cache: "no-store",
    headers,
    body: writes ? JSON.stringify(body ?? {}) : undefined,
  });
  const result = (await response.json().catch(() => null)) as
    (T & { detail?: string }) | null;
  if (!response.ok)
    throw new Error(result?.detail || "Relationship command failed.");
  if (!result) throw new Error("Relationship command returned no result.");
  return result;
}
export const relationshipsApi = {
  list: (
    search = "",
    sort: RelationshipSort = "LATEST_ACTIVITY",
    filter: RelationshipFilter = "ALL",
    cursor?: string | null,
    signal?: AbortSignal,
    countryTiers: MarketTier[] = [],
  ) => {
    const query = new URLSearchParams({ limit: "50", sort, filter });
    if (search) query.set("search", search);
    if (cursor) query.set("cursor", cursor);
    for (const tier of countryTiers) query.append("countryTier", tier);
    return read<RelationshipList>(`/api/v1/relationships?${query}`, signal);
  },
  messages: (key: string, cursor?: string | null, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: "40", includePerson: "false" });
    if (cursor) query.set("cursor", cursor);
    return read<Transcript>(
      `/api/v1/relationships/${encodeURIComponent(key)}/messages?${query}`,
      signal,
    );
  },
  completeMessages: async (key: string, signal?: AbortSignal) => {
    let cursor: string | null | undefined;
    const pages: RelationshipMessage[][] = [];
    const seen = new Set<string>();
    do {
      const page = await relationshipsApi.messages(key, cursor, signal);
      pages.unshift(page.items);
      cursor = page.olderCursor;
      if (cursor && seen.has(cursor))
        throw new Error("Transcript pagination did not advance.");
      if (cursor) seen.add(cursor);
    } while (cursor);
    const unique = new Map<string, RelationshipMessage>();
    for (const message of pages.flat()) unique.set(message.eventKey, message);
    return [...unique.values()].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  },
  intelligence: (key: string, signal?: AbortSignal) =>
    read<RelationshipIntelligence>(
      `/api/v1/relationships/${encodeURIComponent(key)}/intelligence`,
      signal,
    ),
  marketTier: (key: string) =>
    developerRequest<MarketTierProjection>(
      `/api/v1/relationships/${encodeURIComponent(key)}/market-tier`,
    ),
  setMarketTier: (
    key: string,
    marketTier: Exclude<MarketTier, "UNCLASSIFIED">,
  ) =>
    developerRequest<MarketTierProjection>(
      `/api/v1/relationships/${encodeURIComponent(key)}/market-tier`,
      "PUT",
      {},
      { marketTier },
    ),
  removeMarketTier: (key: string) =>
    developerRequest<MarketTierProjection>(
      `/api/v1/relationships/${encodeURIComponent(key)}/market-tier`,
      "DELETE",
    ),
  setHighValueProspect: (key: string) =>
    developerRequest<{
      intelligence: RelationshipIntelligence;
      scheduling: {
        scheduleAdvanced: boolean;
        advancedOperation: {
          operation_id: string;
          next_retry_at: string;
        } | null;
      };
    }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/operator-classification`,
      "PUT",
      {},
      { classification: "HIGH_VALUE_PROSPECT" },
    ),
  removeHighValueProspect: (key: string) =>
    developerRequest<{
      intelligence: RelationshipIntelligence;
      scheduling: { scheduleAdvanced: boolean; advancedOperation: null };
    }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/operator-classification`,
      "DELETE",
    ),
  control: (key: string, signal?: AbortSignal) =>
    read<RelationshipControl>(
      `/api/v1/relationships/${encodeURIComponent(key)}/control`,
      signal,
    ),
  takeover: (key: string) =>
    command<RelationshipControl>(
      `/api/v1/relationships/${encodeURIComponent(key)}/takeover`,
      {},
    ),
  returnToAva: (key: string) =>
    command<RelationshipControl>(
      `/api/v1/relationships/${encodeURIComponent(key)}/return-to-ava`,
      {},
    ),
  cancelReply: (key: string, operationId: string, inboundMessageId: number) =>
    command<{ operationId: string; state: string; changed: boolean; reason: string }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/cancel-reply`,
      { operationId, inboundMessageId },
    ),
  ignore: (key: string, expectedControlVersion: number) =>
    developerRequest<RelationshipControl>(
      `/api/v1/relationships/${encodeURIComponent(key)}/ignore`,
      "PUT",
      {},
      { expectedControlVersion },
    ),
  unignore: (key: string, expectedControlVersion: number) =>
    developerRequest<RelationshipControl>(
      `/api/v1/relationships/${encodeURIComponent(key)}/ignore`,
      "DELETE",
      {},
      { expectedControlVersion },
    ),
  acknowledgeAttention: (key: string, occurrenceId: string) =>
    command<OperationalProjection>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/${encodeURIComponent(occurrenceId)}/acknowledge`,
      {},
    ),
  inspectAttention: (key: string, occurrenceId: string, requestId: string) =>
    developerRequest<AttentionInspectionResponse>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/${encodeURIComponent(occurrenceId)}/inspect`,
      "POST",
      { "X-Creator-OS-Inspection-Key": requestId },
    ),
  similarAttention: (key: string, inspectionId: string) =>
    developerRequest<{ items: AttentionSimilarCase[] }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/inspections/${encodeURIComponent(inspectionId)}/similar`,
    ),
  createDeliveryResolutionPlan: (key: string, inspectionId: string,
      outcome: "CONFIRM_DELIVERED"|"CONFIRM_NOT_DELIVERED") =>
    developerRequest<AttentionPlan>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/inspections/${encodeURIComponent(inspectionId)}/delivery-plan`,
      "POST", {}, { outcome },
    ),
  approveAttentionPlan: (key: string, planId: string) =>
    developerRequest<AttentionPlan>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/plans/${encodeURIComponent(planId)}/approve`,
      "POST",
    ),
  rejectAttentionPlan: (key: string, planId: string) =>
    developerRequest<AttentionPlan>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/plans/${encodeURIComponent(planId)}/reject`,
      "POST",
    ),
  executeAttentionPlan: (key: string, planId: string) =>
    developerRequest<AttentionExecution>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/plans/${encodeURIComponent(planId)}/execute`,
      "POST",
    ),
  attentionExecution: (key: string, executionId: string) =>
    developerRequest<AttentionExecution>(
      `/api/v1/relationships/${encodeURIComponent(key)}/attention/executions/${encodeURIComponent(executionId)}`,
    ),
  analyzeConversation: (key: string) =>
    developerRequest<ConversationAnalysisResponse>(
      `/api/v1/relationships/${encodeURIComponent(key)}/conversation-analyses`,
      "POST",
      {},
      { targetType: "CONVERSATION" },
    ),
  createRepairProposal: (key: string, analysisId: string, findingId: string) =>
    developerRequest<{
      proposal: RepairProposal | null;
      scope: string;
      globalRepair: string;
      reason?: string;
      suggestedAction?: string;
    }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/conversation-analyses/${analysisId}/repair-proposals`,
      "POST",
      {},
      { findingId },
    ),
  approveRepairProposal: (key: string, proposalId: string) =>
    developerRequest<{
      authorization: { authorization_id: string };
      status: string;
    }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/conversation-repair-proposals/${proposalId}/approve`,
      "POST",
      {},
      {},
    ),
  executeRepair: (key: string, authorizationId: string) =>
    developerRequest<RepairExecution>(
      `/api/v1/relationships/${encodeURIComponent(key)}/conversation-repair-executions`,
      "POST",
      {},
      { authorizationId },
    ),
  repairExecution: (key: string, executionId: string) =>
    developerRequest<RepairExecution>(
      `/api/v1/relationships/${encodeURIComponent(key)}/conversation-repair-executions/${executionId}`,
    ),
  send: (
    key: string,
    text: string,
    idempotencyKey: string,
    expectedControlVersion: number,
  ) =>
    command<RelationshipMessage & { state: string; operationId: string; priceMinor?: number; currency?: string; error?: string }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/messages`,
      { text, idempotencyKey, expectedControlVersion },
    ),
  offerInventory: (
    key: string,
    view: string,
    type: string,
    search: string,
    hidePurchased: boolean,
  ) => {
    const query = new URLSearchParams({
      view,
      search,
      hidePurchased: String(hidePurchased),
    });
    if (type) query.set("type", type);
    return read<OfferInventory>(
      `/api/v1/relationships/${encodeURIComponent(key)}/offer-inventory?${query}`,
    );
  },
  prepareOffer: (
    key: string,
    offeringId: string,
    expectedControlVersion: number,
    businessConnectionId: string | null,
  ) =>
    command<PreparedOffer>(
      `/api/v1/relationships/${encodeURIComponent(key)}/offers/prepare`,
      { offeringId, expectedControlVersion, businessConnectionId },
    ),
  offerStatus: (key: string, operationId: string) => read<RelationshipMessage & {state: string; operationId: string; priceMinor?: number; currency?: string; error?: string}>(`/api/v1/relationships/${encodeURIComponent(key)}/offers/${encodeURIComponent(operationId)}`),
  sendOffer: (
    key: string,
    body: {
      offeringId: string;
      expectedControlVersion: number;
      businessConnectionId: string | null;
      text: string;
      idempotencyKey: string;
    },
  ) =>
    command<RelationshipMessage & { state: string; operationId: string; priceMinor?: number; currency?: string; error?: string }>(
      `/api/v1/relationships/${encodeURIComponent(key)}/offers`,
      body,
    ),
};
