export type TestChatUser = {
  name: string;
  relationship: string;
  buyerTier: string;
};

export type TestChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type TestChatDecision = {
  intent: string;
  relationship: string;
  sell: boolean;
  provider_selected: string | null;
  reason: string;
  product: string | null;
  asset: string | null;
  commerce_lookup_attempted: boolean;
  requested_media_type: string | null;
  requested_themes: string[];
  offering_selected: boolean;
  offering_id: string | null;
  offering_type: string | null;
  offering_title: string | null;
  price_minor: number | null;
  currency: string | null;
  primary_sales_channel: string;
  provider: string | null;
  fulfillable: boolean;
  recommendation_reason: string | null;
  no_offering_reason: string | null;
  delivery_url: string | null;
  legacy_offer_requested?: boolean;
  commerce_offer_authorized?: boolean;
  final_offer_authorized?: boolean;
  commerce_execution_policy?: string | null;
  customer_sales_decision?: string | null;
  customer_sales_reason_code?: string | null;
  authoritative_offering_selected?: boolean;
  selection_source?: string | null;
  commerce_prompt_mode?: string | null;
  legacy_recommendation_used?: boolean;
  commerce_mode?: string | null;
  compatibility_mode?: boolean;
  delivery_source?: string | null;
  memory_source?: string | null;
  eligibility_source?: string | null;
  recommendation_source?: string | null;
  legacy_memory_mutated?: boolean;
  legacy_delivery_used?: boolean;
  recommendation_diagnostics?: RecommendationDiagnostics | null;
  commerce_learning_profile?: CommerceLearningProfile | null;
};

export type RecommendationComponent = {
  key: string; rawValue: number | boolean | null;
  weightedContribution: number; weight?: number | null; explanation: string;
  affectedRanking: boolean; evidence: Record<string, unknown>;
};

export type RankedRecommendation = {
  rank: number; offeringId: string; title: string;
  offeringType?: string; priceMinor?: number; currency?: string;
  publishedAt: string | null; activeIntentMatch: boolean;
  components: RecommendationComponent[]; reason: string;
  selected: boolean; finalScore: number;
};

export type RecommendationDiagnostics = {
  selectionReason?: string; exclusionReasons?: string[];
  recommendationEngineVersion?: string;
  recommendationSummary?: string;
  candidateCount?: number; eligibleCount?: number; rejectedCount?: number;
  activeIntentApplied?: boolean;
  recommendationTrace?: RankedRecommendation[];
};

export type CommerceLearningProfile = {
  preferences: Record<string, Record<string, {
    score: number; confidence: number; observations: number;
  }>>;
  outcomeCounts: Record<string, number>;
  preferredOfferingType: string | null;
  preferredPriceMinMinor: number | null;
  preferredPriceMaxMinor: number | null;
  repeatPurchaseFrequency: number;
  confidence: number;
  evidenceCount: number;
};

export type TestChatTurn = TestChatDecision & { reply: string };

export type TestChatSession = {
  sessionId: string;
  testUser: TestChatUser;
  messages: TestChatMessage[];
  reply?: string;
  decision?: TestChatDecision;
  externalSendsDisabled: boolean;
};
