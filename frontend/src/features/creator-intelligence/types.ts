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

export type SnapshotPeriod = "TODAY" | "YESTERDAY" | "LAST_7_DAYS" | "LAST_30_DAYS" | "THIS_MONTH" | "ALL_TIME";
export type SnapshotMetricValue = {
  status: "AVAILABLE" | "UNAVAILABLE";
  value: number | null;
  recordIds?: string[];
  reason?: string | null;
};
export type SnapshotPeriodMetadata = {
  key: SnapshotPeriod;
  timezone: string;
  start: string | null;
  end: string;
  generatedAt: string;
  interval: string;
};
export type PerformanceSnapshot = {
  period: SnapshotPeriodMetadata;
  commerce: {
    totalVerifiedRevenueMinor: SnapshotMetricValue;
    contentMediaRevenueMinor: SnapshotMetricValue;
    tipsRevenueMinor: SnapshotMetricValue;
    subscriptionRenewalRevenueMinor: SnapshotMetricValue;
    unclassifiedRevenueMinor: SnapshotMetricValue;
    qualifyingPurchases: SnapshotMetricValue;
    uniqueBuyers: SnapshotMetricValue;
    newBuyers: SnapshotMetricValue;
    repeatBuyers: SnapshotMetricValue;
    averagePurchaseValueMinor: SnapshotMetricValue;
    offersPresented: SnapshotMetricValue;
    offersPurchased: SnapshotMetricValue;
    offerConversion: SnapshotMetricValue;
    wouldHaveSold: SnapshotMetricValue;
  };
  peopleActivity: {
    activePeople: SnapshotMetricValue;
    newPeople: SnapshotMetricValue;
    returningPeople: SnapshotMetricValue;
    customerMessages: SnapshotMetricValue;
    avaMessages: SnapshotMetricValue;
  };
  dataQuality: Record<string, unknown>;
};
export type SnapshotDrillDown = {
  period: SnapshotPeriodMetadata;
  metric: string;
  count: number;
  amountMinor: number | null;
  presentation?: "BUSINESS_FACING";
  developerDetailsCollapsed?: boolean;
  pagination?: { page:number; pageSize:number; totalRows:number; hasMore:boolean };
  items: SnapshotDrillDownItem[];
};
export type SnapshotDrillDownItem = {
  rowKey: string;
  customer: { resolved:boolean; rowKey:string|null; displayName:string; handle:string|null; platform:string; buyerStatus:string };
  event: { type:string; label?:string|null; grossMinor:number|null; netMinor:number|null; occurredAt:string|null; status:string; purchaseType:string|null; attributionState:string|null; messageCount:number|null; presented?:number|null; purchased?:number|null; conversionRate?:number|null };
  context: { lifetimeGrossMinor:number; transactionCount:number; firstPurchaseAt:string|null; latestPurchaseAt:string|null; repeatBuyer:boolean };
  navigation: { customerKey:string|null; conversationKey:string|null };
  developerDetails: Record<string,string>;
};
export type CurrentSalesStatus = { activeSalesSessions:number; activePurchaseIntents:number; commercialFailures:number; asOf:"CURRENT" };

export type XLinkTrackingState = "TRACKED" | "TRACKING_UNAVAILABLE" | "NO_CTA" | "FAILED_CTA";
export type XLinkPerformanceItem = {
  primaryPostId: string;
  ctaPostId: string | null;
  accountName: string;
  caption: string;
  thumbnailUrl: string;
  publishedAt: string;
  trackingState: XLinkTrackingState;
  linkClicks: number | null;
};
export type XLinkPerformance = {
  period: SnapshotPeriodMetadata;
  items: XLinkPerformanceItem[];
  historicalBoundary: string;
};
