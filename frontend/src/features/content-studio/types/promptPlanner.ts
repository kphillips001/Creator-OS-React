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
