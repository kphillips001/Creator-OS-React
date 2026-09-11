export type CustomerSummaryMetrics = { total:number; buyers:number; activeSubscribers:number; formerSubscribers:number; highValue:number; activeSessions:number };
export type CustomerTransaction = { transactionId:string; type:"CONTENT"|"SUBSCRIPTION"|"RENEWAL"|"TIP"|"OTHER"; grossMinor:number; netMinor:number; occurredAt:string };
export type CustomerWorkspaceItem = {
  customerId:string; displayName:string; username:string|null; commercialStatuses:string[];
  totalSpendMinor:number; transactionCount:number; contentPurchaseCount:number; lastActivityAt:string|null;
  isBuyer:boolean; isHighValue:boolean; valueTier:string; attentionTier:string|null; retentionStatus:string;
  subscriptionStatus:string; subscriptionPeriodEnd:string|null; activeSalesSession:boolean; activePurchaseIntent:boolean;
  relationshipKey:string|null; hasTelegramRelationship:boolean; localFanvueUserId:number|null; identitySearchValues?:string[];
  transactions?:CustomerTransaction[]; subscription?:{status:string;periodEnd:string|null;providerBacked:boolean};
  customerValue?:Record<string,unknown>; commercialState?:Record<string,unknown>; ownership?:Record<string,unknown>[];
  interactionSafety?:{safetyStatus:"NORMAL"|"UNDERAGE_BLOCKED";decision:string;policyEnabled:boolean;reason:string|null;effectiveAt:string|null;history:Array<Record<string,unknown>>};
  abuseReview?:Record<string,unknown>|null;
};
export type CustomerListResponse = {items:CustomerWorkspaceItem[];summary:CustomerSummaryMetrics;total:number;page:number;pageSize:number;totalPages:number};
