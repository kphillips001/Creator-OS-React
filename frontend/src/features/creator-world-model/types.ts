export type CreatorWorldModelDocument = {
  id: number | null;
  creator_profile_id: number;
  fanvue_account_id: string;
  internal_home_base: string;
  public_location_description: string;
  home_and_indoor_environments: string;
  coastal_environments: string;
  mountains_lakes_and_small_town_escapes: string;
  climate_and_seasonal_behavior: string;
  seasonal_activities: string;
  holiday_rhythm: string;
  travel_and_variety_guidance: string;
  created_at: string | null;
  updated_at: string | null;
};

export type CreatorWorldModelUpdate = Pick<
  CreatorWorldModelDocument,
  | "internal_home_base"
  | "public_location_description"
  | "home_and_indoor_environments"
  | "coastal_environments"
  | "mountains_lakes_and_small_town_escapes"
  | "climate_and_seasonal_behavior"
  | "seasonal_activities"
  | "holiday_rhythm"
  | "travel_and_variety_guidance"
>;
