export type CoachTopic = {
  topic: string; mentions: number; messageCount: number;
  conversationCount: number; messageIds: number[]; trend: null;
};
export type CoachOverview = {
  totalConversationsReviewed: number; totalMessagesReviewed: number;
  averageConversationLength: number; returningVisitors: number;
  topicsDiscussed: CoachTopic[];
  conversationEndings: { ava: number; visitor: number; unknown: number };
  questionsAsked: number; conversationContinuationRate: number;
  inboundMessages: number; outboundMessages: number;
};
export type CoachEvidenceItem = {
  insight_type?: string; title: string; description: string;
  evidence: Record<string, unknown>; confidence: number;
};
export type CoachRecommendation = CoachEvidenceItem & {
  recommendation_id: string; expected_impact: string;
  status: "PENDING" | "APPROVED_FOR_VERSION" | "REJECTED" | "DISMISSED" | "ACTIVATED";
  version_label: string; approved_at: string | null;
};
export type AvaCoachDashboard = {
  overview: CoachOverview;
  snapshot: {
    snapshot_id: string; created_at: string;
    period_start: string | null; period_end: string | null;
  } | null;
  insights: CoachEvidenceItem[];
  recommendations: CoachRecommendation[];
  appliedImprovements: Array<{
    improvement_id: string; recommendation_id: string; title: string;
    description: string; confidence: number; evidence: Record<string, unknown>;
    status: "APPROVED_FOR_VERSION" | "ACTIVATED";
    version_label: string; applied_at: string;
  }>;
  versions: Array<{
    version_id: string; version_label: string;
    status: "BASELINE" | "DRAFT" | "ACTIVE" | "RETIRED"; notes: string;
  }>;
  observationalOnly: boolean;
};
