export type SocialCreativeDirectionDocument = {
  id: number | null;
  creator_profile_id: number;
  fanvue_account_id: string;
  purpose: string;
  wardrobe: string;
  visual_style: string;
  seasonal_guidance: string;
  things_to_avoid: string;
  created_at: string | null;
  updated_at: string | null;
};

export type SocialCreativeDirectionUpdate = Pick<
  SocialCreativeDirectionDocument,
  "purpose" | "wardrobe" | "visual_style" | "seasonal_guidance" | "things_to_avoid"
>;
