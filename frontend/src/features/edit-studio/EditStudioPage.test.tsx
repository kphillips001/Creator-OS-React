import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { navigationGroups } from "../../app/navigation/navigation";
import { EditStudioPage } from "./EditStudioPage";
import { calculateCropDrag } from "./quickEditTools";

const generationRecord = {
  image_id: "generated-1", image_url: "/image.png", provider_id: "seedream_5_0_pro",
  prompt_text: "Portrait", creative_mode: "premium_teaser", generation_date: "2026-01-01T00:00:00Z",
  status: "pending_edit", generation_job_id: "job-1", generation_request_id: "request-1",
  generation_result_id: "result-1", prompt_plan_id: "plan-1", reference_asset_id: 1,
  imported_asset_id: null, provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
};
const candidateRecord = {
  ...generationRecord, image_id: "candidate-1", image_url: "/candidate.png",
  status: "edit_candidate", prompt_text: "Edited portrait", generation_job_id: "edit-job-1",
};

const response = (body: unknown, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  text: () => Promise.resolve(JSON.stringify(body)),
} as Response);

afterEach(() => vi.restoreAllMocks());

const renderPage = () => render(
  <MemoryRouter initialEntries={["/content/edit"]}>
    <Routes>
      <Route path="/content/edit" element={<EditStudioPage />} />
      <Route path="/library/generations" element={<div>Generation Library destination</div>} />
    </Routes>
  </MemoryRouter>,
);

describe("EditStudioPage", () => {
  it("calculates independent edges, all corners, and crop repositioning in source pixels", () => {
    const start = { x: 100, y: 200, width: 600, height: 900 };
    const bounds = { width: 1200, height: 1800 };
    expect(calculateCropDrag(start, "n", 0, 50, bounds)).toEqual({ x: 100, y: 250, width: 600, height: 850 });
    expect(calculateCropDrag(start, "s", 0, -100, bounds)).toEqual({ x: 100, y: 200, width: 600, height: 800 });
    expect(calculateCropDrag(start, "w", 75, 0, bounds)).toEqual({ x: 175, y: 200, width: 525, height: 900 });
    expect(calculateCropDrag(start, "e", 80, 0, bounds)).toEqual({ x: 100, y: 200, width: 680, height: 900 });
    for (const handle of ["nw", "ne", "sw", "se"] as const) {
      expect(calculateCropDrag(start, handle, 20, 30, bounds)).not.toEqual(start);
    }
    expect(calculateCropDrag(start, "move", 90, -50, bounds)).toEqual({ x: 190, y: 150, width: 600, height: 900 });
  });

  it("nests AI modes and exposes Crop through the Quick Edit tool workspace", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/quick-edit/source-info")) return response({ image_id: "generated-1", width: 1200, height: 1800 });
      if (url.endsWith("/quick-edit/crop") && init?.method === "POST") return response({ success: true, message: "Cropped image added to Generation Library.", result: { ...generationRecord, image_id: "cropped-1", status: "active" } });
      if (url.endsWith("/edit-studio/references")) return response([]);
      return response({ creator_profile_exists: true, pending_source: generationRecord, providers: [{ value: "seedream_5_0_pro", label: "Seedream" }] });
    });
    renderPage();

    expect(await screen.findByRole("button", { name: /Quick Edit/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI Edit/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Single Edit/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Quick Edit/ }));
    expect(screen.getByRole("heading", { name: "Choose Quick Edit Tool" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Crop/ }));
    expect(await screen.findByRole("img", { name: "Crop source" })).toHaveAttribute("src", "/image.png");
    expect(await screen.findByText("1200 × 1800 px")).toBeInTheDocument();
    expect(screen.getByLabelText("Crop aspect ratio")).toHaveValue("Free");
    expect(screen.getAllByRole("button", { name: /Resize crop/ })).toHaveLength(8);
    fireEvent.change(screen.getByLabelText("Crop aspect ratio"), { target: { value: "1:1" } });
    expect(screen.getByText("1200 × 1200 px")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply Crop" }));
    expect(await screen.findByText("Generation Library destination")).toBeInTheDocument();
    const request = fetch.mock.calls.find(([url]) => String(url).endsWith("/quick-edit/crop"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ source_image_id: "generated-1", width: 1200, height: 1200 });
  });

  it("is registered in Studios at the required route", () => {
    const studios = navigationGroups.find((group) => group.label === "Studios");
    expect(studios?.items.map(({ label }) => label)).toEqual([
      "Content Studio", "Regeneration Studio", "Photoshoot Studio", "Video Studio", "Edit Studio",
    ]);
    expect(studios?.items.find(({ label }) => label === "Edit Studio")?.path).toBe("/content/edit");
  });

  it("renders the missing creator profile gate without requesting configuration", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      creator_profile_exists: false, pending_source: null, providers: [],
    }));
    renderPage();
    expect(await screen.findByText("Creator Profile required before using Edit Studio.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("renders the no pending image gate", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      creator_profile_exists: true, pending_source: null, providers: [],
    }));
    renderPage();
    expect(await screen.findByText("Choose an image in Generation Library and click ✏️ Edit to start.")).toBeInTheDocument();
  });

  it("renders API providers and reveals reference controls only for Multi Edit", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/edit-studio/references")) return response([
        { asset_id: 12, label: "Identity portrait", preview_url: "/reference.png" },
      ]);
      return response({
        creator_profile_exists: true,
        pending_source: generationRecord,
        providers: [
          { value: "seedream_5_0_pro", label: "ByteDance Seedream 5.0 Pro Edit" },
          { value: "nano_banana_pro", label: "Google Nano Banana Pro Edit" },
          { value: "wan_2_7_image_edit", label: "WAN 2.7 Image Edit" },
          { value: "nano_banana", label: "Google Nano Banana 2 Edit" },
        ],
      });
    });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Selected Source Image" })).toBeInTheDocument();
    const sourceImage = screen.getByRole("img", { name: "Portrait" });
    expect(sourceImage).toHaveAttribute("src", "/image.png");
    expect(screen.queryByRole("heading", { name: "Reference Images" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Single Edit/ }));
    expect(screen.getByRole("img", { name: "Portrait" })).toBe(sourceImage);
    const providerSelect = await screen.findByLabelText("Provider") as HTMLSelectElement;
    expect(providerSelect).toHaveValue("seedream_5_0_pro");
    expect(Array.from(providerSelect.options).map((option) => option.text)).toEqual([
      "ByteDance Seedream 5.0 Pro Edit",
      "Google Nano Banana Pro Edit",
      "WAN 2.7 Image Edit",
      "Google Nano Banana 2 Edit",
    ]);
    expect(screen.queryByRole("option", { name: "ByteDance Seedream 4.5 Edit" })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Describe the exact change. Keep everything else the same.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Edit" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reference Images" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Multi Edit/ }));
    expect(screen.getByRole("img", { name: "Portrait" })).toBe(sourceImage);
    expect(screen.getByText("Use one or more reference images")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reference Images" })).toBeInTheDocument();
    expect(screen.getByLabelText("Provider")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Describe how the original image should use the selected reference images.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Edit" })).toBeInTheDocument();
    expect(screen.getByText("Optional. Add one or more reference images to guide the edit.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add Reference" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add Reference" }));
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2);
    expect(screen.queryByText("Role")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Role/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "Select a reference image..." })).toHaveLength(2);
    expect(screen.getAllByText("Choose a creative reference from your Reference Library or upload one.")).toHaveLength(2);
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Identity portrait" })).toHaveLength(2));
    expect(screen.queryByText("Advanced")).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/edit-studio/context"),
      expect.any(Object),
    );
  });

  it("returns the pending image through the backend and navigates to Generation Library", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/return-to-library")) return response({ success: true, message: "Returned." });
      if (url.endsWith("/references")) return response([]);
      return response({
        creator_profile_exists: true,
        pending_source: generationRecord,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Return to Library" }));

    expect(await screen.findByText("Generation Library destination")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/edit-studio/return-to-library"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("submits multiple Reference Library images without role metadata", async () => {
    let generationPayload: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/references")) return response([
        { asset_id: 12, label: "Wardrobe look", preview_url: "/wardrobe.png" },
        { asset_id: 13, label: "Pose guide", preview_url: "/pose.png" },
      ]);
      if (url.endsWith("/generate")) {
        generationPayload = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return response({ success: true, message: "Edit generated." });
      }
      return response({
        creator_profile_exists: true,
        pending_source: generationRecord,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Multi Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add Reference" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add Reference" }));
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Wardrobe look" })).toHaveLength(2));
    fireEvent.change(screen.getByLabelText("Reference 1 Reference Image"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Reference 2 Reference Image"), { target: { value: "13" } });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Use these visual references." } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Edit" }));

    expect(await screen.findByText("Edit generated.")).toBeInTheDocument();
    expect(generationPayload).toMatchObject({
      source_image_id: "generated-1",
      edit_mode: "multi_image",
      provider_id: "seedream_5_0_pro",
      prompt: "Use these visual references.",
      references: [
        { source: "reference_library", asset_id: 12 },
        { source: "reference_library", asset_id: 13 },
      ],
    });
  });

  it("uploads a reference and submits the returned asset without a role", async () => {
    let generationPayload: Record<string, unknown> | undefined;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/references/upload")) return response({
        asset_id: 20, label: "uploaded.png", preview_url: "/uploaded.png",
      });
      if (url.endsWith("/references")) return response([]);
      if (url.endsWith("/generate")) {
        generationPayload = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return response({ success: true, message: "Edit generated." });
      }
      return response({
        creator_profile_exists: true,
        pending_source: generationRecord,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Multi Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: "+ Add Reference" }));
    fireEvent.change(screen.getByLabelText("Reference 1 Asset Source"), { target: { value: "upload" } });
    fireEvent.change(screen.getByLabelText("Reference 1 Upload"), {
      target: { files: [new File(["image"], "uploaded.png", { type: "image/png" })] },
    });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Use the uploaded reference." } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Edit" }));

    expect(await screen.findByText("Edit generated.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/edit-studio/references/upload"),
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    expect(generationPayload).toMatchObject({
      references: [{ source: "upload", asset_id: 20 }],
    });
  });

  it("allows Multi Edit generation with the original image only", async () => {
    let generationPayload: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/references")) return response([]);
      if (url.endsWith("/generate")) {
        generationPayload = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return response({ success: true, message: "Edit generated." });
      }
      return response({
        creator_profile_exists: true,
        pending_source: generationRecord,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Multi Edit/ }));
    expect(await screen.findByText(/No creative reference images available/)).toBeInTheDocument();
    expect(screen.getByText(/Use Upload to add one/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Refine the original." } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Edit" }));

    await screen.findByText("Edit generated.");
    expect(generationPayload).toMatchObject({ edit_mode: "multi_image", references: [] });
  });

  it("shows generation state and automatically transitions from polling to candidate review", async () => {
    let statusCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/references")) return response([]);
      if (url.endsWith("/generate")) return response({
        success: true, message: "Edit generation started.", generation_job_id: "edit-job-1", generation_status: "queued",
      });
      if (url.endsWith("/generation/edit-job-1")) {
        statusCalls += 1;
        return response({
          generation_job_id: "edit-job-1", generation_status: statusCalls > 1 ? "succeeded" : "running", provider_id: "seedream_5_0_pro",
          candidate: statusCalls > 1 ? candidateRecord : null, error: null,
        });
      }
      return response({
        creator_profile_exists: true, pending_source: generationRecord, candidate: null,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Single Edit/ }));
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "Refine portrait." } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Edit" }));

    expect(await screen.findByText("Generating Edit...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Single Edit/ })).toBeDisabled();
    expect(await screen.findByRole("heading", { name: "Edited Candidate" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Edited portrait" })).toHaveAttribute("src", "/candidate.png");
    expect(statusCalls).toBe(2);
  });

  it.each([
    ["Approve", "/edit-studio/approve", "Generation Library destination"],
    ["Discard", "/edit-studio/discard", "Choose Edit Type"],
    ["Edit Again", "/edit-studio/edit-again", "Choose Edit Type"],
  ])("handles candidate review action %s", async (button, endpoint, expectedText) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/references")) return response([]);
      if (url.endsWith(endpoint)) {
        if (button === "Edit Again") return response({ success: true, message: "Ready.", working_source: candidateRecord });
        return response({
          success: true,
          message: button === "Discard" ? "Edited image discarded." : "Edited image approved.",
          ...(button === "Approve" ? { updated_record: { ...generationRecord, image_url: "/current-v2.png", status: "active" } } : {}),
        });
      }
      return response({
        creator_profile_exists: true, pending_source: generationRecord, candidate: candidateRecord,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: button }));
    expect(await screen.findByText(expectedText)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(endpoint), expect.objectContaining({ method: "POST" }));
  });

  it("keeps form input and permits retry after a polled generation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/references")) return response([]);
      if (url.endsWith("/generate")) return response({ success: true, message: "Started.", generation_job_id: "failed-job", generation_status: "queued" });
      if (url.endsWith("/generation/failed-job")) return response({
        generation_job_id: "failed-job", generation_status: "failed", provider_id: "seedream_5_0_pro", candidate: null, error: "Provider rejected edit.",
      });
      return response({
        creator_profile_exists: true, pending_source: generationRecord, candidate: null,
        providers: [{ value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" }],
      });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /AI Edit/ }));
    fireEvent.click(screen.getByRole("button", { name: /Single Edit/ }));
    const prompt = screen.getByLabelText("Prompt");
    fireEvent.change(prompt, { target: { value: "Keep this instruction." } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Edit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Provider rejected edit.");
    expect(prompt).toHaveValue("Keep this instruction.");
    expect(screen.getByRole("button", { name: "Generate Edit" })).toBeEnabled();
  });

  it.each([
    [404, "Edit Studio backend unavailable."],
    [500, "Unable to load Edit Studio."],
  ])("maps HTTP %s to a safe page error and logs backend details", async (status, expected) => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(
      { detail: "Internal backend detail" },
      status,
    ));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(screen.queryByText("Internal backend detail")).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      "Edit Studio backend request failed",
      expect.objectContaining({ status, error: "Internal backend detail" }),
    );
  });
});
