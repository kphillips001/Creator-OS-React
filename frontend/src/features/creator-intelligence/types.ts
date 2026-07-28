export type HealthStatus = "Healthy" | "Warning" | "Offline" | "Needs Attention";
export type DiagnosticEvidence = Array<Record<string, unknown>>;
export type HealthItem = {
  label: string; status: HealthStatus; summary?: string;
  classification?: string; root_cause?: string;
  evidence: string | DiagnosticEvidence; confidence?: number;
  automatic_resolution?: boolean; resolution_reason?: string;
  recommended_action?: string; affected_components?: string[];
  last_updated?: string;
};
export type IntelligenceItem = { label: string; value: number };
export type Recommendation = { title: string; why: string; action: string };

export type CreatorIntelligence = {
  generatedAt: string;
  relationshipMode: {
    mode: "OFF" | "RELATIONSHIP" | "LIVE";
    customersMet: number; returningVisitors: number;
    wouldHaveSoldToday: number; mostRequestedOffering: string;
    customersReadyForCommerce: number; highInterestCustomers: number;
  };
  systemHealth: HealthItem[];
  today: {
    activeConversations: number | null; waitingReplies: number | null; purchaseIntentsWaiting: number;
    offers: number; purchases: number; revenueMinor: number; conversionRate: number;
    recommendations: number; learningEvents: number;
  };
  recommendations: Recommendation[];
  avaCoachSummary?: {
    latest_analysis_at: string | null; conversations_reviewed: number;
    pending_recommendations: number; approved_for_version: number;
  };
  commerceLearning: { profiles: number; eventsToday: number; confidence: string; trend: string; signals?: Array<{ label: string; value: string }> };
  contentPipeline: Record<string, number>;
  customerOpportunities: IntelligenceItem[];
  revenueOpportunities: IntelligenceItem[];
  problems: Array<{
    title: string; detail: string; severity: HealthStatus;
    diagnostic?: HealthItem;
  }>;
};
