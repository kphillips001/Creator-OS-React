export type CreatorLifestyleDocument = {
  id: number | null;
  creator_profile_id: number;
  fanvue_account_id: string;
  career: string;
  lifestyle_overview: string;
  favorite_activities: string;
  weekend_escapes: string;
  small_town_roots: string;
  outdoor_lifestyle: string;
  personal_style: string;
  created_at: string | null;
  updated_at: string | null;
};

export type CreatorLifestyleUpdate = Pick<
  CreatorLifestyleDocument,
  | "career"
  | "lifestyle_overview"
  | "favorite_activities"
  | "weekend_escapes"
  | "small_town_roots"
  | "outdoor_lifestyle"
  | "personal_style"
>;
