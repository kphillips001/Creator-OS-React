import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreatorWorldModelPage } from "./CreatorWorldModelPage";
import type { CreatorWorldModelDocument } from "./types";

const document: CreatorWorldModelDocument = {
  id: 1,
  creator_profile_id: 2,
  fanvue_account_id: "2",
  internal_home_base: "Ava’s internal home base is Wilmington.",
  public_location_description: "Ava lives in a coastal East Coast city.",
  home_and_indoor_environments: "Bedroom, living room, kitchen, and office.",
  coastal_environments: "Beaches, marshes, and downtown.",
  mountains_lakes_and_small_town_escapes: "Mountains, lakes, and cabins.",
  climate_and_seasonal_behavior: "Use regional seasonal rhythm.",
  seasonal_activities: "Spring, summer, fall, and winter activities.",
  holiday_rhythm: "Timely and tasteful holiday concepts.",
  travel_and_variety_guidance: "Use the full range of Ava’s world.",
  created_at: "2026-07-27T14:00:00",
  updated_at: "2026-07-27T14:00:00",
};

const response = (body: unknown, ok = true) => Promise.resolve({
  ok,
  json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.unstubAllGlobals());

describe("CreatorWorldModelPage", () => {
  it("loads nine large editable sections with privacy kept separate", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response(document)));
    render(<CreatorWorldModelPage />);

    expect(await screen.findByLabelText(/Internal Home Base/)).toHaveValue(
      document.internal_home_base,
    );
    expect(screen.getByLabelText(/Public Location Description/)).toHaveValue(
      document.public_location_description,
    );
    expect(screen.getByLabelText(/Home and Indoor Environments/)).toHaveValue(
      document.home_and_indoor_environments,
    );
    expect(screen.getByLabelText(/Coastal Environments/)).toHaveValue(
      document.coastal_environments,
    );
    expect(screen.getByLabelText(/Mountains, Lakes/)).toHaveValue(
      document.mountains_lakes_and_small_town_escapes,
    );
    expect(screen.getByLabelText(/Climate and Seasonal Behavior/)).toHaveValue(
      document.climate_and_seasonal_behavior,
    );
    expect(screen.getByLabelText(/Seasonal Activities/)).toHaveValue(
      document.seasonal_activities,
    );
    expect(screen.getByLabelText(/Holiday Rhythm/)).toHaveValue(
      document.holiday_rhythm,
    );
    expect(screen.getByLabelText(/Travel and Variety Guidance/)).toHaveValue(
      document.travel_and_variety_guidance,
    );
    expect(screen.getAllByRole("textbox")).toHaveLength(9);
    expect(screen.getByRole("button", { name: "Save Document" })).toBeDisabled();
  });

  it("tracks dirty state and saves only World Model fields", async () => {
    const fetch = vi.fn()
      .mockImplementationOnce(() => response(document))
      .mockImplementationOnce((_url: string, options: RequestInit) => {
        const body = JSON.parse(String(options.body));
        return response({
          ...document,
          ...body,
          updated_at: "2026-07-27T15:00:00",
        });
      });
    vi.stubGlobal("fetch", fetch);
    render(<CreatorWorldModelPage />);

    const publicLocation = await screen.findByLabelText(
      /Public Location Description/,
    );
    const save = screen.getByRole("button", { name: "Save Document" });
    fireEvent.change(publicLocation, {
      target: { value: "Updated public location" },
    });

    expect(save).toBeEnabled();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    fireEvent.click(save);

    expect(await screen.findByText("World Model saved.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Document" })).toBeDisabled();
    const request = fetch.mock.calls[1]?.[1];
    expect(request).toMatchObject({ method: "PUT" });
    const payload = JSON.parse(String(request?.body));
    expect(Object.keys(payload)).toHaveLength(9);
    expect(payload).not.toHaveProperty("creator_profile_id");
    expect(payload).not.toHaveProperty("fanvue_account_id");
    expect(payload.public_location_description).toBe(
      "Updated public location",
    );
  });
});
