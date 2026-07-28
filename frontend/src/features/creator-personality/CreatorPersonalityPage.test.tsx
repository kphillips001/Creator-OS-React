import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreatorPersonalityPage } from "./CreatorPersonalityPage";
import type { CreatorPersonality } from "./types";

const profile: CreatorPersonality = {
  id: 2, fanvue_account_id: "2", persona_name: "Ava Blackthorne",
  display_name: "Ava Blackthorne", age: 29, gender: "female",
  location: "Coastal East Coast city", is_active: true,
  archetype: "Small-town sweetheart", personality_description: "Warm and playful.",
  backstory: "Small-town roots.", lifestyle_context: "Coastal city life.",
  lifestyle_vibe: "Coastal relaxation.", daily_routine: "Coffee before work.",
  hobbies: "Road trips.", likes: "Meaningful conversations.", dislikes: "Dishonesty.",
  ideal_user_type: "Kind and genuine.", turn_ons: "Confidence.",
  turn_offs: "Arrogance.", sexual_style: "Connection and trust.",
  sexual_likes: "Chemistry.", sexual_dislikes: "Pressure.", kinks: "Playful teasing.",
  fantasy_style: "Shared experiences.", tone_style: "Warm and conversational.",
  flirt_style: "Playful teasing.", tease_intensity: 7, push_pull_style: "medium",
  mystery_level: "medium", response_style: "Natural.", pacing_style: "Gradual.",
  question_frequency: "medium", emotional_depth: "high", affection_style: "Supportive.",
  jealousy_style: "Secure.", availability_style: "Independent.",
  conversation_hooks: "Travel.", retention_hooks: "Remember details.",
  escalation_style: "Through trust.", escalation_triggers: "Positive chemistry.",
  self_value_style: "Confident and welcoming.", persona_intensity: 7,
  boundaries: "Mutual respect.", sexual_boundaries: "Consensual adults.",
  hard_limits: "No harmful scenarios.", response_rules: "Make people feel welcome.",
  created_at: "2026-06-21T10:53:03", updated_at: "2026-06-21T10:53:03",
};

const response = (body: unknown, ok = true) => Promise.resolve({
  ok,
  json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.unstubAllGlobals());

describe("CreatorPersonalityPage", () => {
  it("loads the existing canonical profile and all logical sections", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(profile)));
    render(<CreatorPersonalityPage />);

    expect(await screen.findByDisplayValue("Ava Blackthorne")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Coastal East Coast city")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Warm and playful.")).toBeInTheDocument();
    for (const heading of [
      "Identity", "Personality", "Lifestyle", "Relationships",
      "Conversation Style", "Attraction & Sexuality", "Escalation",
      "Boundaries", "Response Rules",
    ]) {
      expect(screen.getByRole("heading", { name: heading, level: 2 })).toBeInTheDocument();
    }
    expect(screen.getByText(/Visual identity, creative direction, and generation behavior are managed separately/)).toBeInTheDocument();
  });

  it("saves edits to the same endpoint and displays the persisted response", async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => response(profile))
      .mockImplementationOnce((_url: string, options: RequestInit) => {
        const body = JSON.parse(String(options.body));
        return response({ ...profile, ...body, updated_at: "2026-07-27T12:00:00" });
      });
    vi.stubGlobal("fetch", fetch);
    render(<CreatorPersonalityPage />);

    const tone = await screen.findByDisplayValue("Warm and conversational.");
    fireEvent.change(tone, { target: { value: "Edited exact value" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Personality" }));

    expect(await screen.findByText("Creator personality saved.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1]?.[0]).toMatch(/\/creator\/personality$/);
    expect(fetch.mock.calls[1]?.[1]).toMatchObject({ method: "PUT" });
    const payload = JSON.parse(String(fetch.mock.calls[1]?.[1]?.body));
    expect(payload.tone_style).toBe("Edited exact value");
    expect(payload.id).toBeUndefined();
    expect(payload.fanvue_account_id).toBeUndefined();
    await waitFor(() => expect(screen.getByDisplayValue("Edited exact value")).toBeInTheDocument());
  });
});
