export type PromptPreviewSignature = {
  creativeMode: string;
  creativeTags: string;
  promptCount: number;
};

export type PromptPreview = {
  planId: string;
  creativeMode: string;
  creativeRationale: string;
  promptMetadata: Record<string, unknown>;
  prompts: string[];
  signature: PromptPreviewSignature;
};

export type PromptPreviewResponse = {
  success: boolean;
  error: string | null;
  preview: PromptPreview;
};
