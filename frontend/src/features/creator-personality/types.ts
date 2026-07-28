export type CreatorPersonality = {
  id: number;
  fanvue_account_id: string;
  display_name: string;
  created_at: string;
  updated_at: string;
  persona_name: string;
  age: number;
  gender: string;
  location: string;
  is_active: boolean;
  archetype: string;
  personality_description: string;
  backstory: string;
  lifestyle_context: string;
  lifestyle_vibe: string;
  daily_routine: string;
  hobbies: string;
  likes: string;
  dislikes: string;
  ideal_user_type: string;
  turn_ons: string;
  turn_offs: string;
  sexual_style: string;
  sexual_likes: string;
  sexual_dislikes: string;
  kinks: string;
  fantasy_style: string;
  tone_style: string;
  flirt_style: string;
  tease_intensity: number;
  push_pull_style: string;
  mystery_level: string;
  response_style: string;
  pacing_style: string;
  question_frequency: string;
  emotional_depth: string;
  affection_style: string;
  jealousy_style: string;
  availability_style: string;
  conversation_hooks: string;
  retention_hooks: string;
  escalation_style: string;
  escalation_triggers: string;
  self_value_style: string;
  persona_intensity: number;
  boundaries: string;
  sexual_boundaries: string;
  hard_limits: string;
  response_rules: string;
};

export type CreatorPersonalityUpdate = Omit<
  CreatorPersonality,
  "id" | "fanvue_account_id" | "display_name" | "created_at" | "updated_at"
>;
