export type GenerationRecord = {
  image_id: string;
  image_url: string;
  provider_id: string;
  prompt_text: string;
  creative_mode: string | null;
  generation_date: string;
  status: string;
  generation_job_id: string;
  generation_request_id: string;
  generation_result_id: string;
  prompt_plan_id: string;
  reference_asset_id: number | null;
  imported_asset_id: number | null;
  provider_metadata: Record<string, unknown>;
  prompt_metadata: Record<string, unknown>;
  generation_metadata: Record<string, unknown>;
  creator_profile_id?: number;
};

export type GenerationCardAction =
  | "publish"
  | "edit"
  | "photoshoot"
  | "video"
  | "move-to-asset-library"
  | "remove";

export type GenerationActionResponse = {
  message?: string;
  redirect?: string;
  error?: string;
  detail?: string;
  todo?: boolean;
  image_id?: string;
  status?: string;
  review_state?: string;
  source_image_url?: string;
  context_refresh?: boolean;
  session_id?: string;
  generation_id?: string;
  already_moved?: boolean;
};

export type GenerationLibraryResponse = {
  records: GenerationRecord[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  providers: string[];
  modes: string[];
  error?: string;
};

export type PublishDestination = "x" | "telegram_wall" | "telegram_chat";

export type PublishContext = {
  success: boolean;
  generatedImageId: string;
  defaultDestination: PublishDestination;
  destinations: Array<{
    value: PublishDestination;
    label: string;
    available: boolean;
  }>;
  error?: string;
};

export type CaptionTheme = {
  theme: string;
  captions: string[];
};
