export const RECREATE_RUNTIME_STAGES = [
  "Uploading reference image", "Analyzing uploaded image", "Building creative direction",
  "Generating canonical prompt", "Submitting generation", "Waiting for provider", "Generation complete",
] as const;

export type RecreateRuntimeState = {
  activeStage: number;
  message: string;
  state: "running" | "failed" | "complete";
  failedStage?: number;
};
