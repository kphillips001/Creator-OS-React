export type PromptPlannerResponse = {
  success: boolean;
  error: string | null;
  answer: string;
};

export type PromptPlannerHistoryItem = {
  question: string;
  answer: string;
  imageName: string;
};

export type CanonicalPlannerItem = {
  id: string;
  title: string;
  fullText: string;
  description: string;
  plannerQuestion: string;
  origin: "canonical_planner";
};
