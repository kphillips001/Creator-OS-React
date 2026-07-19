export const PROMPT_SOURCES = [
  { label: "Original", value: "Original Tags" },
  { label: "Enhanced", value: "Enhanced Tags" },
  { label: "Surprise Me", value: "Surprise Me Tags" },
  { label: "Enhanced Explicit", value: "Enhanced Explicit Tags" },
  { label: "Prompt Workshop", value: "Prompt Workshop" },
] as const;

export type PromptSource = typeof PROMPT_SOURCES[number]["value"];

export type CreativeToolInputs = {
  creativeTags: string;
  enhancedExplicitTags: string;
  enhancedTags: string;
  explicitTags: string;
  surpriseTags: string;
};

export type CreativeTagActionResponse = {
  success: boolean;
  error: string | null;
  tags: string;
};
