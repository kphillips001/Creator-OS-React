export type ContentStudioOption = {
  label: string;
  value: string;
};

export type ContentStudioConfiguration = {
  success: boolean;
  error: string | null;
  modes: ContentStudioOption[];
  promptCount: {
    minimum: number;
    maximum: number;
    default: number;
  };
  providers: ContentStudioOption[];
  defaults: {
    mode: string;
    provider: string;
  };
};
