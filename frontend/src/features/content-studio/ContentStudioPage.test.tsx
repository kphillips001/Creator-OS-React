import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "../../app/router/router";
import { ContentStudioPage } from "./ContentStudioPage";
import {
  CanonicalPromptPlannerSection,
  parsePlannerResponse,
} from "./components/CanonicalPromptPlannerSection";
import { type PlannerBatchItem, updatePlannerBatchItems } from "./types/plannerBatch";

const stylesheetText = readFileSync(
  resolve("src/features/content-studio/styles/content-studio.css"),
  "utf8",
);

const readyContext = {
  success: true,
  error: null,
  creatorProfileExists: true,
  activeReferenceExists: true,
  activeReferenceAssetId: 42,
  activeReferenceLastUsedAt: "2026-07-16T12:30:00",
};

const configuration = {
  success: true,
  error: null,
  modes: [
    { value: "premium_teaser", label: "Premium Teaser" },
    { value: "spicy", label: "Spicy" },
    { value: "story_sequence", label: "Story Sequence" },
  ],
  promptCount: { minimum: 1, maximum: 20, default: 5 },
  providers: [
    { value: "seedream_5_0_pro", label: "Seedream 5.0 Pro" },
    { value: "nano_banana_pro", label: "Nano Banana Pro" },
    { value: "wan_2_7_image_edit", label: "WAN 2.7" },
    { value: "nano_banana", label: "Nano Banana 2" },
    { value: "seedream_4_5", label: "Seedream 4.5" },
  ],
  defaults: { mode: "premium_teaser", provider: "seedream_5_0_pro" },
};

function mockContext(
  value: object,
  configurationValue: object = configuration,
  archiveValue: object[] = [],
  plannerAnswer = "",
) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, options?: RequestInit) => {
    let responseValue = url.endsWith("/configuration")
      ? configurationValue
      : url.endsWith("/generations/run-inspire")
        ? {
            success: true,
            error: null,
            generation: {
              runId: "run-inspire", jobId: "job-inspire", promptPlanId: "plan-inspire",
              status: "succeeded", message: "Generation completed successfully.",
              provider: "seedream_5_0_pro", completedCount: 6, failedCount: 0,
              processedCount: 6, totalCount: 6, progress: 100,
              images: Array.from({ length: 6 }, (_, index) => ({
                index,
                url: `/api/v1/content-studio/generations/run-inspire/images/${index}`,
              })),
            },
          }
      : url.endsWith("/generations/run-live")
        ? {
            success: true,
            error: null,
            generation: {
              runId: "run-live", jobId: "job-live", promptPlanId: "plan-live",
              status: "partial", message: "Generation completed with partial success.",
              provider: "seedream_5_0_pro", completedCount: 1, failedCount: 9,
              processedCount: 10, totalCount: 10, progress: 100,
              images: [{ index: 0, url: "/api/v1/content-studio/generations/run-live/images/0" }],
            },
          }
      : url.endsWith("/prompt-workshop/archive")
        ? { success: true, error: null, batches: archiveValue }
        : value;
    if (options?.method === "POST") {
      if (url.endsWith("/prompt-planner/ask")) {
        const plannerBody = options.body as FormData;
        responseValue = {
          success: true,
          error: null,
          answer: plannerAnswer || `answer for ${plannerBody.get("question")}${plannerBody.get("image") ? " with image" : ""}`,
        };
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve(responseValue),
          ok: true,
          status: 200,
        });
      }
      const body = JSON.parse(String(options.body)) as { explicit?: boolean; tags?: string };
      if (url.endsWith("/inspire")) {
        responseValue = { success: true, error: null, runId: "run-inspire" };
      } else if (url.endsWith("/generations")) {
        responseValue = { success: true, error: null, runId: "run-live" };
      } else if (url.endsWith("/prompt-workshop/generate")) {
        responseValue = {
          success: true,
          error: null,
          batch: {
            batchId: "batch-new",
            createdAt: "2026-07-17T12:00:00",
            lane: "explicit",
            prompts: ["generated prompt one", "generated prompt two"],
            requestText: "hotel sequence",
            usedPromptNumbers: [],
          },
        };
      } else if (url.endsWith("/prompt-preview")) {
        const previewBody = body as unknown as {
          creativeMode: string;
          creativeTags: string;
          promptCount: number;
        };
        responseValue = {
          success: true,
          error: null,
          preview: {
            creativeMode: previewBody.creativeMode,
            creativeRationale: "Created by the current prompt planner.",
            planId: "plan-preview",
            promptMetadata: { canonical_planner: "creator_os", prompt_builder: "canonical_premium_prompt_planner" },
            prompts: ["preview prompt one", "preview prompt two"],
            signature: previewBody,
          },
        };
      } else if (url.includes("/prompt-workshop/archive/") && url.endsWith("/use")) {
        responseValue = { success: true, error: null };
      } else {
        const tags = url.endsWith("/surprise")
            ? `surprised ${body.tags}`
            : body.explicit
              ? `explicitly enhanced ${body.tags}`
              : `enhanced ${body.tags}`;
        responseValue = { success: true, error: null, tags };
      }
    }
    return Promise.resolve({
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve(responseValue),
      ok: true,
      status: 200,
    });
  }));
}

describe("ContentStudioPage", () => {
  it("parses complete multiline planner items without absorbing global narrative", () => {
    const parsed = parsePlannerResponse(
      "Planning note.\n\n1. **Golden Hour Marina Walk**\n"
      + "Ava wears a coral crop top and denim shorts while walking beside the marina at sunset,\n"
      + "brushing her hair back as she glances toward the water.\n\n"
      + "- **Trail Cool-Down**\nA fitted athletic set after a shaded hike.\n\n"
      + "# Final note\nKeep the collection varied.",
      "Give me two ideas",
    );

    expect(parsed.ideas).toEqual([
      expect.objectContaining({
        description: expect.stringContaining("brushing her hair back"),
        fullText: expect.stringContaining(
          "Golden Hour Marina Walk — Ava wears a coral crop top and denim shorts",
        ),
        origin: "canonical_planner",
        plannerQuestion: "Give me two ideas",
        title: "Golden Hour Marina Walk",
      }),
      expect.objectContaining({
        fullText: "Trail Cool-Down — A fitted athletic set after a shaded hike.",
        title: "Trail Cool-Down",
      }),
    ]);
    expect(parsed.narrative).toContain("Planning note.");
    expect(parsed.narrative).toContain("# Final note");
    expect(parsed.narrative).toContain("Keep the collection varied.");
  });

  it("keeps one-line planner descriptions complete", () => {
    const parsed = parsePlannerResponse(
      "1. White crop top and denim shorts while walking the dock at sunset.",
      "Summer looks",
    );
    expect(parsed.ideas[0]?.fullText).toBe(
      "White crop top and denim shorts while walking the dock at sunset.",
    );
  });

  beforeEach(() => mockContext(readyContext));

  it("renders the Content Studio route instead of the generic placeholder", async () => {
    render(<RouterProvider router={router} />);
    fireEvent.click(screen.getByRole("link", { name: "Content Studio" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Content Studio" }),
    ).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/content-studio/context",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByText("Foundation ready")).not.toBeInTheDocument();
  });

  it("renders the specified vertical workflow hierarchy", async () => {
    const { container } = render(<ContentStudioPage />);

    const titles = [
      "Creative Direction",
      "Canonical Prompt Planner Q&A",
      "Creative Settings",
      "Prompt Workshop",
      "Manual Prompt",
    ];

    await screen.findByRole("region", { name: "Creative Direction Workspace" });
    for (const title of titles) {
      expect(screen.getByRole("region", { name: title === "Creative Direction" ? "Creative Direction Workspace" : title })).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeInTheDocument();
    }

    const renderedTitles = Array.from(
      container.querySelectorAll(".workflow-section h2"),
      (heading) => heading.textContent,
    );
    expect(renderedTitles).toEqual(titles);
    expect(screen.getByRole("button", { name: "🚀 Create Images" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Generate Prompts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate Premium Images" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(screen.queryByText("Active Reference")).not.toBeInTheDocument();
    expect(screen.queryByText("Active Reference selected: Asset #42")).not.toBeInTheDocument();
    expect(screen.queryByText(/Last used:/)).not.toBeInTheDocument();
    expect(screen.getByText(
      "Premium creator workflow for provider-neutral prompt planning and generation review.",
    )).toBeInTheDocument();
  });

  it("uses a responsive vertical flow without the removed dashboard panels", () => {
    render(<StrictMode><ContentStudioPage /></StrictMode>);

    expect(stylesheetText).toMatch(/\.content-studio__workflow\s*\{[^}]*flex-direction:\s*column/);
    expect(stylesheetText).toContain("(max-width: 680px)");
    expect(screen.queryByText("Creative workflow")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reference Image" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Prompt Workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Generation Timeline" })).not.toBeInTheDocument();
  });

  it("presents Inspire Me first and keeps Creative Studio collapsed until opened", async () => {
    const { container } = render(<ContentStudioPage />);

    const inspireWorkspace = await screen.findByRole("region", {
      name: "Inspire Me Workspace",
    });
    const creativeStudioSummary = screen.getByText("🎨 Creative Studio").closest("summary");
    const creativeStudio = creativeStudioSummary?.closest("details");

    expect(inspireWorkspace).toHaveTextContent(
      "Let Creator_OS automatically create today's best content for Ava using Creator Intelligence and Creative Intelligence.",
    );
    expect(inspireWorkspace).not.toHaveTextContent("Inspire Me Status");
    expect(inspireWorkspace).not.toHaveTextContent("Inspire Me Live Preview");
    expect(screen.queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(creativeStudio).not.toHaveAttribute("open");
    const inspirePosition = (
      container.querySelector(".inspire-workspace") as HTMLElement
    ).compareDocumentPosition(creativeStudio as Node);
    expect(inspirePosition & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(creativeStudioSummary as HTMLElement);
    expect(creativeStudio).toHaveAttribute("open");
    expect(screen.queryByText("Creative Studio Status")).not.toBeInTheDocument();
    expect(screen.queryByText("Creative Studio Live Preview")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Creative Concept"), {
      target: { value: "keep accordion open" },
    });
    expect(creativeStudio).toHaveAttribute("open");
  });

  it("keeps autonomous and manual generation previews independent", async () => {
    render(<ContentStudioPage />);
    const inspire = await screen.findByRole("button", { name: "✨ Inspire Me" });
    await waitFor(() => expect(inspire).toBeEnabled());
    fireEvent.click(inspire);

    const inspirePreview = screen.getByText("Inspire Me Live Preview")
      .closest(".workflow-live-preview") as HTMLElement;
    await waitFor(() => expect(
      within(inspirePreview).getAllByRole("img", { name: /Generated image \d of 6/ }),
    ).toHaveLength(6));

    fireEvent.click(screen.getByText("🎨 Creative Studio").closest("summary") as HTMLElement);
    fireEvent.change(screen.getByLabelText("Creative Concept"), {
      target: { value: "manual hotel scene" },
    });
    const manualGenerate = screen.getByRole("button", {
      name: "🚀 Create Images",
    });
    await waitFor(() => expect(manualGenerate).toBeEnabled());
    fireEvent.click(manualGenerate);

    const manualPreview = screen.getByText("Creative Studio Live Preview")
      .closest(".workflow-live-preview") as HTMLElement;
    await waitFor(() => expect(
      within(manualPreview).getByRole("img", { name: "Generated image 1 of 5" }),
    ).toBeInTheDocument());
    expect(within(inspirePreview).getAllByRole("img", {
      name: /Generated image \d of 6/,
    })).toHaveLength(6);
  });

  it("keeps manual results visible when Inspire Me runs afterward", async () => {
    render(<ContentStudioPage />);

    fireEvent.click((await screen.findByText("🎨 Creative Studio")).closest("summary") as HTMLElement);
    fireEvent.change(screen.getByLabelText("Creative Concept"), {
      target: { value: "manual rooftop scene" },
    });
    const manualGenerate = screen.getByRole("button", {
      name: "🚀 Create Images",
    });
    await waitFor(() => expect(manualGenerate).toBeEnabled());
    fireEvent.click(manualGenerate);

    const manualPreview = screen.getByText("Creative Studio Live Preview")
      .closest(".workflow-live-preview") as HTMLElement;
    await waitFor(() => expect(
      within(manualPreview).getByRole("img", { name: "Generated image 1 of 5" }),
    ).toBeInTheDocument());

    const inspire = screen.getByRole("button", { name: "✨ Inspire Me" });
    fireEvent.click(inspire);
    const inspirePreview = screen.getByText("Inspire Me Live Preview")
      .closest(".workflow-live-preview") as HTMLElement;
    await waitFor(() => expect(
      within(inspirePreview).getAllByRole("img", { name: /Generated image \d of 6/ }),
    ).toHaveLength(6));

    expect(within(manualPreview).getByRole("img", {
      name: "Generated image 1 of 5",
    })).toBeInTheDocument();
    expect(within(manualPreview).queryByRole("img", {
      name: /Generated image \d of 6/,
    })).not.toBeInTheDocument();
  });

  it("blocks the workflow when no Creator Profile exists", async () => {
    mockContext({
      success: true,
      error: null,
      creatorProfileExists: false,
      activeReferenceExists: false,
      activeReferenceAssetId: null,
      activeReferenceLastUsedAt: null,
    });
    render(<ContentStudioPage />);

    expect(await screen.findByText(
      "Creator Profile required before selecting a Reference Image.",
    )).toBeInTheDocument();
    expect(screen.getByText("Creator Profile required before using Content Studio.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Creative Direction Workspace" })).not.toBeInTheDocument();
  });

  it("shows the missing-reference state and disables dependent sections", async () => {
    mockContext({
      success: true,
      error: null,
      creatorProfileExists: true,
      activeReferenceExists: false,
      activeReferenceAssetId: null,
      activeReferenceLastUsedAt: null,
    });
    render(<ContentStudioPage />);

    expect(await screen.findByText(
      "No active Reference Image selected for this Creator Profile.",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "Select an active Reference Image before creating premium work.",
    )).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🚀 Create Images" })).toBeDisabled();
    expect(screen.getByRole("region", { name: "Canonical Prompt Planner Q&A" })).not.toHaveAttribute("aria-disabled");
  });

  it("loads creator defaults, provider options, and validates prompt count locally", async () => {
    render(<ContentStudioPage />);

    const mode = await screen.findByLabelText("Premium Creative Mode") as HTMLSelectElement;
    const count = await screen.findByLabelText("Prompt Count") as HTMLInputElement;
    const provider = screen.getByLabelText("Provider") as HTMLSelectElement;
    const advancedSettings = screen.getByText("Advanced Settings").closest("details");

    expect(mode.value).toBe("premium_teaser");
    expect(Array.from(mode.options, (option) => [option.text, option.value])).toEqual([
      ["Standard", "premium_teaser"],
      ["Spicy", "spicy"],
    ]);
    expect(count).toHaveAttribute("min", "1");
    expect(count).toHaveAttribute("max", "20");
    expect(advancedSettings).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Advanced Settings"));
    expect(advancedSettings).toHaveAttribute("open");
    expect(provider.value).toBe("seedream_5_0_pro");
    await waitFor(() => expect(count.value).toBe("5"));
    expect(provider.value).toBe("seedream_5_0_pro");
    expect(Array.from(provider.options, (option) => option.text)).toEqual([
      "Seedream 5.0 Pro",
      "Nano Banana Pro",
      "WAN 2.7",
      "Nano Banana 2",
      "Seedream 4.5",
    ]);

    fireEvent.change(mode, { target: { value: "spicy" } });
    fireEvent.change(count, { target: { value: "99" } });
    fireEvent.change(provider, { target: { value: "wan_2_7_image_edit" } });
    expect(mode.value).toBe("spicy");
    expect(count.value).toBe("20");
    expect(provider.value).toBe("wan_2_7_image_edit");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("maps a historical story-sequence default to the Standard UI option", async () => {
    mockContext(readyContext, {
      ...configuration,
      defaults: { ...configuration.defaults, mode: "story_sequence" },
    });
    render(<ContentStudioPage />);

    const mode = await screen.findByLabelText("Premium Creative Mode") as HTMLSelectElement;

    expect(mode.value).toBe("premium_teaser");
    expect(Array.from(mode.options, (option) => option.value)).toEqual([
      "premium_teaser",
      "spicy",
    ]);
  });

  it("lays out configuration controls in a wrapping responsive row", async () => {
    render(<ContentStudioPage />);
    await screen.findByLabelText("Provider");

    expect(stylesheetText).toMatch(/\.creative-configuration\s*\{[^}]*display:\s*flex/);
    expect(stylesheetText).toMatch(/@media\s*\(max-width:\s*680px\)/);
    expect(stylesheetText).toMatch(/\.creative-configuration\s*\{[^}]*flex-direction:\s*column/);
  });

  it("runs manual Create Images through enhancement, prompt construction, and generation without exposing prompts", async () => {
    render(<StrictMode><ContentStudioPage /></StrictMode>);

    const premiumTags = await screen.findByLabelText("Creative Concept") as HTMLTextAreaElement;
    const explicitTags = screen.getByLabelText("Explicit Tags") as HTMLTextAreaElement;

    fireEvent.change(premiumTags, { target: { value: "hotel robe" } });
    expect(premiumTags.value).toBe("hotel robe");
    const createImages = screen.getByRole("button", { name: "🚀 Create Images" });
    fireEvent.click(createImages);
    fireEvent.click(createImages);
    await screen.findByRole("img", { name: "Generated image 1 of 5" });
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
    expect(screen.queryByText("Surprise Me Tags")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Surprise Me/ })).not.toBeInTheDocument();

    fireEvent.change(explicitTags, { target: { value: "explicit hotel" } });
    fireEvent.click(screen.getByRole("button", { name: /Enhance Explicit Tags/ }));
    const enhancedExplicit = screen.getByLabelText("Enhanced Explicit Tags") as HTMLTextAreaElement;
    await waitFor(() => expect(enhancedExplicit.value).toBe("explicitly enhanced explicit hotel"));
    expect(screen.queryByText("Prompt Source")).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    const postCalls = vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === "POST");
    expect(postCalls).toHaveLength(4);
    expect(postCalls[0]![0]).toBe("/api/v1/content-studio/creative-tags/enhance");
    expect(JSON.parse(String(postCalls[0]![1]?.body))).toEqual({
      explicit: false,
      origin: "manual_creative_concept",
      tags: "hotel robe",
    });
    expect(postCalls[1]![0]).toBe("/api/v1/content-studio/prompt-preview");
    expect(postCalls[2]![0]).toBe("/api/v1/content-studio/generations");
    expect(JSON.parse(String(postCalls[1]![1]?.body))).toEqual({
      creativeMode: "premium_teaser",
      creativeTags: "[ORIGINAL USER TAGS — mandatory: hotel robe] [ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: enhanced hotel robe]",
      promptCount: 5,
    });
  });

  it("creates six images from Inspire Me without exposing concepts or prompts", async () => {
    render(<ContentStudioPage />);

    const concept = await screen.findByLabelText("Creative Concept");
    const inspire = screen.getByRole("button", { name: "✨ Inspire Me" });
    await waitFor(() => expect(inspire).toBeEnabled());
    expect(screen.queryByText("Inspire Today's Post")).not.toBeInTheDocument();

    fireEvent.click(inspire);

    expect(concept).toHaveValue("");
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
    const images = await screen.findAllByRole("img", {
      name: /Generated image \d of 6/,
    });
    expect(images).toHaveLength(6);
    expect(screen.queryByRole("region", { name: "Next Step" })).not.toBeInTheDocument();
    const call = vi.mocked(fetch).mock.calls.find(
      ([url]) => String(url).endsWith("/content-studio/inspire"),
    );
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      provider: "seedream_5_0_pro",
    });
  });

  it("removes Surprise Me and the ordinary Prompt Preview workflow", async () => {
    render(<ContentStudioPage />);

    await screen.findByLabelText("Creative Concept");
    expect(screen.queryByRole("button", { name: /Surprise Me/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Surprise Me Tags")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Generate Prompts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
  });

  it("supports selecting all planner ideas and clearing the selection", async () => {
    mockContext(
      readyContext,
      configuration,
      [],
      "1. Candlelit window portrait with a thoughtful side glance.\n2. Balcony pose with wind moving the robe.",
    );
    render(<ContentStudioPage />);

    const premiumTags = await screen.findByLabelText("Creative Concept") as HTMLTextAreaElement;
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Give me ideas" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));

    const selectAll = await screen.findByRole("checkbox", { name: "Select All" });
    const bulkAction = screen.getByRole("button", { name: /Enhance & Generate \(0\)/ });
    expect(bulkAction).toBeDisabled();
    expect(screen.getByText("Selected: 0")).toBeInTheDocument();
    fireEvent.click(selectAll);
    expect(screen.getByText("Selected: 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enhance & Generate \(2\)/ })).toBeEnabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);
    fireEvent.click(checkboxes[1]!);
    expect(selectAll).not.toBeChecked();
    expect((selectAll as HTMLInputElement).indeterminate).toBe(true);
    expect(screen.getByText("Selected: 1")).toBeInTheDocument();
    fireEvent.click(checkboxes[1]!);
    expect(selectAll).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Clear Selection" }));
    expect(selectAll).not.toBeChecked();
    expect(screen.getByText("Selected: 0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enhance & Generate$/ })).not.toBeInTheDocument();

    fireEvent.change(premiumTags, { target: { value: "manual enhancement remains" } });
    fireEvent.click(screen.getByRole("button", { name: "🚀 Create Images" }));
    await screen.findByRole("img", { name: "Generated image 1 of 5" });
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/creative-tags/enhance"))).toHaveLength(1);
  });

  it("enhances a planner idea and then invokes the existing image generation workflow", async () => {
    mockContext(
      readyContext,
      configuration,
      [],
      "1. **Golden Hour Marina Walk**\n"
      + "Ava wears a coral crop top and denim shorts while walking beside the marina at sunset, "
      + "brushing her hair back as she glances toward the water.",
    );
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    let resolveEnhancement: ((value: Response) => void) | undefined;
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/creative-tags/enhance")) {
        return new Promise<Response>((resolve) => { resolveEnhancement = resolve; });
      }
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    const premiumTags = await screen.findByLabelText("Creative Concept");
    fireEvent.change(premiumTags, { target: { value: "silk robe" } });
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Give me one idea" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));

    const ideaCheckbox = await screen.findByRole("checkbox", { name: /Select Golden Hour Marina Walk/ });
    fireEvent.click(ideaCheckbox);
    const orchestrate = screen.getByRole("button", { name: /Enhance & Generate \(1\)/ });
    expect(orchestrate).toBeEnabled();
    fireEvent.click(orchestrate);

    expect(ideaCheckbox).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Select All" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enhancing & Generating…" })).toBeDisabled();
    expect(screen.getByText("Processing 1 of 1")).toBeInTheDocument();
    resolveEnhancement!({
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve({
        success: true,
        error: null,
        tags: "creator-aware marina movement with confident editorial energy",
      }),
      ok: true,
      status: 200,
    } as Response);

    const enhancementCall = await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/creative-tags/enhance"));
      expect(call).toBeDefined();
      return call;
    });
    expect(JSON.parse(String(enhancementCall?.[1]?.body))).toMatchObject({
      origin: "canonical_planner",
      plannerItemTitle: "Golden Hour Marina Walk",
      plannerQuestion: "Give me one idea",
      tags: expect.stringContaining("brushing her hair back as she glances toward the water"),
    });
    const generationCall = await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/generations"));
      expect(call).toBeDefined();
      return call;
    });
    expect(vi.mocked(fetch).mock.calls.indexOf(enhancementCall!)).toBeLessThan(vi.mocked(fetch).mock.calls.indexOf(generationCall!));
    const generationBody = JSON.parse(String(generationCall![1]?.body));
    expect(generationBody).toMatchObject({
      creativeMode: "premium_teaser",
      origin: "canonical_planner",
      plannerLineage: {
        enhancedResult: "creator-aware marina movement with confident editorial energy",
        plannerItemTitle: "Golden Hour Marina Walk",
        plannerQuestion: "Give me one idea",
        selectedPlannerItem: expect.stringContaining("walking beside the marina at sunset"),
      },
      promptCount: 1,
      promptSourceLabel: "Enhanced Tags",
      provider: "seedream_5_0_pro",
    });
    expect(generationBody.promptSource).toContain(
      "[ORIGINAL USER TAGS — mandatory: Golden Hour Marina Walk — Ava wears a coral crop top",
    );
    expect(generationBody.promptSource).toContain(
      "[ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: creator-aware marina movement",
    );
    expect(generationBody.promptSource).not.toContain("silk robe");
    expect(generationBody.promptSource).not.toContain("mandatory: ]");
    expect(await screen.findByRole("region", { name: "Live Generation" })).toBeInTheDocument();
  });

  it("processes selected planner ideas sequentially and leaves their selection intact", async () => {
    mockContext(readyContext, configuration, [], "1. First selected idea.\n2. Second selected idea.");
    render(<ContentStudioPage />);

    await screen.findByLabelText("Creative Concept");
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Two ideas" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select All" }));
    fireEvent.click(screen.getByRole("button", { name: /Enhance & Generate \(2\)/ }));

    expect(screen.getByText("Processing 1 of 2")).toBeInTheDocument();
    await waitFor(() => expect(
      vi.mocked(fetch).mock.calls.filter(([url, options]) => String(url).endsWith("/generations") && options?.method === "POST"),
    ).toHaveLength(2), { timeout: 3000 });
    await waitFor(() => expect(screen.queryByText(/Processing \d of 2/)).not.toBeInTheDocument(), { timeout: 3000 });

    const workflowCalls = vi.mocked(fetch).mock.calls.filter(([url, options]) => (
      String(url).endsWith("/creative-tags/enhance")
      || (String(url).endsWith("/generations") && options?.method === "POST")
      || (String(url).endsWith("/generations/run-live") && options?.method !== "POST")
    ));
    expect(workflowCalls.map(([url]) => (
      String(url).endsWith("/creative-tags/enhance")
        ? "enhance"
        : String(url).endsWith("/generations/run-live") ? "settle" : "generate"
    ))).toEqual(["enhance", "generate", "settle", "enhance", "generate", "settle"]);
    const generationBodies = workflowCalls
      .filter(([url]) => String(url).endsWith("/generations"))
      .map(([, options]) => JSON.parse(String(options?.body)) as { promptCount: number });
    expect(generationBodies.every((body) => body.promptCount === 1)).toBe(true);
    expect(screen.getByText("Selected: 2")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select All" })).toBeChecked();
    expect(screen.getByRole("button", { name: /Enhance & Generate \(2\)/ })).toBeEnabled();
    const aggregateProgress = screen.getByRole("region", { name: "Live Generation" });
    expect(within(aggregateProgress).getByText("2 of 2 Processed")).toBeInTheDocument();
    expect(within(aggregateProgress).getByText("Completed: 2")).toBeInTheDocument();
    expect(within(aggregateProgress).getByText("Failed: 0")).toBeInTheDocument();
    expect(within(aggregateProgress).getByText("Generation batch completed successfully.")).toBeInTheDocument();
    await waitFor(() => expect(within(aggregateProgress).getAllByRole("img", { name: /Generated image/ })).toHaveLength(2));
    expect(within(aggregateProgress).getByLabelText("Generated image slots")).toHaveStyle({ "--generation-columns": "2" });
    expect(within(aggregateProgress).queryByRole("img", { name: /Waiting for generated image/ })).not.toBeInTheDocument();
  });

  it("keeps one stable card per planner item across repeated payloads, rerenders, and Strict Mode", async () => {
    const plannerAnswer = Array.from(
      { length: 7 },
      (_, index) => `${index + 1}. Planner idea ${index + 1}.`,
    ).join("\n");
    mockContext(readyContext, configuration, [], plannerAnswer);
    const view = render(<StrictMode><ContentStudioPage /></StrictMode>);

    await screen.findByLabelText("Creative Concept");
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Seven ideas" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select All" }));
    fireEvent.click(screen.getByRole("button", { name: /Enhance & Generate \(7\)/ }));

    await waitFor(() => expect(
      vi.mocked(fetch).mock.calls.filter(([url, options]) => (
        String(url).endsWith("/generations") && options?.method === "POST"
      )),
    ).toHaveLength(7), { timeout: 7000 });
    await waitFor(() => expect(screen.getByText("7 of 7 Processed")).toBeInTheDocument(), { timeout: 7000 });

    const liveRegion = screen.getByRole("region", { name: "Live Generation" });
    expect(within(liveRegion).getAllByRole("img", { name: /Generated image/ })).toHaveLength(7);
    for (let ordinal = 1; ordinal <= 7; ordinal += 1) {
      expect(within(liveRegion).getAllByText(`${ordinal} of 7`)).toHaveLength(1);
    }

    view.rerender(<StrictMode><ContentStudioPage /></StrictMode>);
    expect(within(liveRegion).getAllByRole("img", { name: /Generated image/ })).toHaveLength(7);
    for (let ordinal = 1; ordinal <= 7; ordinal += 1) {
      expect(within(liveRegion).getAllByText(`${ordinal} of 7`)).toHaveLength(1);
    }
  });

  it("reconciles repeated completion updates into the existing planner item", () => {
    const initial: PlannerBatchItem[] = [{
      error: "",
      id: "planner-item-1",
      imageUrl: "",
      jobId: null,
      ordinal: 0,
      status: "generating",
    }];
    const completion = {
      imageUrl: "/api/v1/content-studio/generations/run-1/images/0",
      jobId: "job-1",
      status: "completed" as const,
    };

    const completed = updatePlannerBatchItems(initial, "planner-item-1", completion);
    const repeated = updatePlannerBatchItems(completed, "planner-item-1", completion);

    expect(repeated).toHaveLength(1);
    expect(repeated[0]).toMatchObject({ id: "planner-item-1", ordinal: 0, ...completion });
  });

  it("continues the planner batch when one selected idea fails enhancement", async () => {
    mockContext(readyContext, configuration, [], "1. First failing idea.\n2. Second successful idea.");
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/creative-tags/enhance") && String(options?.body).includes("First failing idea")) {
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve({ success: false, error: "First idea failed", tags: "" }),
          ok: true,
          status: 200,
        } as Response);
      }
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    await screen.findByLabelText("Creative Concept");
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Two ideas" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select All" }));
    fireEvent.click(screen.getByRole("button", { name: /Enhance & Generate \(2\)/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("First idea failed");
    await waitFor(() => expect(
      vi.mocked(fetch).mock.calls.filter(([url, options]) => String(url).endsWith("/generations") && options?.method === "POST"),
    ).toHaveLength(1));
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/creative-tags/enhance"))).toHaveLength(2);
    await waitFor(() => expect(screen.getByText("2 of 2 Processed")).toBeInTheDocument());
    expect(screen.getByText("Completed: 1")).toBeInTheDocument();
    expect(screen.getByText("Failed: 1")).toBeInTheDocument();
    expect(screen.getByText("Generation batch completed with 1 failed.")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /Generated image/ })).toHaveLength(1);
  });

  it("does not generate when planner idea enhancement fails", async () => {
    mockContext(readyContext, configuration, [], "1. Window portrait idea.");
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/creative-tags/enhance")) return Promise.resolve({
        headers: new Headers({ "content-type": "application/json" }),
        json: () => Promise.resolve({ success: false, error: "Enhancement unavailable", tags: "" }),
        ok: true,
        status: 200,
      } as Response);
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    await screen.findByLabelText("Creative Concept");
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "One idea" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select Window portrait idea/ }));
    fireEvent.click(screen.getByRole("button", { name: /Enhance & Generate \(1\)/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enhancement unavailable");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/generations"))).toBe(false);
    await waitFor(() => expect(screen.getByRole("button", { name: /Enhance & Generate \(1\)/ })).toBeEnabled());
  });

  it("stops before prompt generation when Create Images enhancement fails", async () => {
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/creative-tags/enhance")) {
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve({ success: false, error: "Enhancement unavailable", tags: "" }),
          ok: true,
          status: 200,
        } as Response);
      }
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    fireEvent.change(await screen.findByLabelText("Creative Concept"), { target: { value: "hotel robe" } });
    fireEvent.click(screen.getByRole("button", { name: "🚀 Create Images" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enhancement unavailable");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/prompt-preview"))).toBe(false);
    expect(screen.queryByRole("button", { name: "Review Prompts" })).not.toBeInTheDocument();
  });

  it("stops before generation and surfaces the prompt-build error", async () => {
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/prompt-preview")) {
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve({ success: false, error: "Prompt Preview failed", preview: null }),
          ok: true,
          status: 200,
        } as Response);
      }
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    fireEvent.change(await screen.findByLabelText("Creative Concept"), { target: { value: "hotel robe" } });
    fireEvent.click(screen.getByRole("button", { name: "🚀 Create Images" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Prompt Preview failed");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/generations"))).toBe(false);
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/creative-tags/enhance"))).toHaveLength(1);
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/prompt-preview"))).toHaveLength(1);
  });

  it("uses the existing Creative Director error feedback for idea enhancement failures", async () => {
    mockContext(readyContext, configuration, [], "1. Window portrait idea.");
    const defaultFetch = vi.mocked(fetch).getMockImplementation();
    vi.mocked(fetch).mockImplementation((url: RequestInfo | URL, options?: RequestInit) => {
      if (String(url).endsWith("/creative-tags/enhance")) {
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve({ success: false, error: "Enhancement unavailable", tags: "" }),
          ok: true,
          status: 200,
        } as Response);
      }
      return defaultFetch!(url, options);
    });
    render(<ContentStudioPage />);

    await screen.findByLabelText("Creative Concept");
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "One idea" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /Select Window portrait idea/ }));
    fireEvent.click(screen.getByRole("button", { name: /Enhance & Generate \(1\)/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enhancement unavailable");
    await waitFor(() => expect(screen.getByRole("button", { name: /Enhance & Generate \(1\)/ })).toBeEnabled());
  });

  it("disables Creative Director controls when the active reference is missing", async () => {
    mockContext({
      success: true,
      error: null,
      creatorProfileExists: true,
      activeReferenceExists: false,
      activeReferenceAssetId: null,
      activeReferenceLastUsedAt: null,
    });
    render(<ContentStudioPage />);

    expect(await screen.findByLabelText("Creative Concept")).toBeDisabled();
    expect(screen.getByRole("region", { name: "Creative Direction Workspace" })).toHaveAttribute("aria-disabled", "true");
  });

  it("generates and edits Prompt Workshop batches without rendering its archive", async () => {
    mockContext(readyContext, configuration);
    render(<ContentStudioPage />);

    const brief = await screen.findByLabelText("Prompt Workshop Brief");
    await waitFor(() => expect(brief).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Prompt Mode"), { target: { value: "explicit" } });
    fireEvent.change(brief, { target: { value: "hotel sequence" } });
    fireEvent.click(within(screen.getByRole("region", { name: "Prompt Workshop" })).getByRole("button", { name: "Generate Prompts" }));

    const firstPrompt = await screen.findByLabelText("Prompt 1") as HTMLTextAreaElement;
    expect(firstPrompt.value).toBe("generated prompt one");
    fireEvent.change(firstPrompt, { target: { value: "edited generated prompt" } });
    expect(firstPrompt.value).toBe("edited generated prompt");

    fireEvent.click(screen.getByRole("button", { name: "Accept Selected" }));
    const manualRegion = screen.getByRole("region", { name: "Manual Prompt" });
    await waitFor(() => expect(within(manualRegion).getByLabelText("Manual Prompt")).toHaveValue("edited generated prompt"));
    fireEvent.click(screen.getByRole("button", { name: "Accept All" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy Prompt" }));
    expect(await screen.findByText("edited generated prompt", { selector: "pre" })).toBeInTheDocument();

    expect(screen.queryByText("Prompt Workshop Archive")).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/prompt-workshop/archive"))).toBe(false);

    const generateCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/prompt-workshop/generate"));
    expect(JSON.parse(String(generateCall?.[1]?.body))).toEqual({
      lane: "explicit",
      promptCount: 5,
      requestText: "hotel sequence",
    });
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/prompt-workshop/archive/batch-new/use"))).toBe(true);
  });

  it.skip("uses Manual Prompt as the preview override and preserves valid preview edits", async () => {
    render(<ContentStudioPage />);

    const creativeTags = await screen.findByLabelText("Creative Concept");
    const manualRegion = screen.getByRole("region", { name: "Manual Prompt" });
    const manualPrompt = within(manualRegion).getByLabelText("Manual Prompt");
    const promptLauncher = screen.getByRole("region", { name: "Generate Prompts" });
    const createButton = within(promptLauncher).getByRole("button", { name: "Generate Prompts" });

    expect(manualPrompt).toHaveValue("");
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
    expect(within(promptLauncher).queryByRole("button", { name: "Review Prompts" })).not.toBeInTheDocument();
    expect(createButton).toBeDisabled();
    fireEvent.change(creativeTags, { target: { value: "original premium tags" } });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.change(manualPrompt, { target: { value: "manual override prompt" } });
    fireEvent.click(createButton);

    const reviewButton = await within(promptLauncher).findByRole("button", { name: "Review Prompts" });
    expect(screen.queryByLabelText("Prompt 1")).not.toBeInTheDocument();
    fireEvent.click(reviewButton);
    const previewDialog = screen.getByRole("dialog", { name: "Prompt Preview" });
    const previewPrompt = within(previewDialog).getByLabelText("Prompt 1") as HTMLTextAreaElement;
    expect(previewPrompt.value).toBe("preview prompt one");
    const previewCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/prompt-preview"));
    await waitFor(() => expect(previewCalls()).toHaveLength(1));
    expect(JSON.parse(String(previewCalls()[0]![1]?.body))).toEqual({
      creativeMode: "premium_teaser",
      creativeTags: "manual override prompt",
      promptCount: 5,
    });

    fireEvent.change(previewPrompt, { target: { value: "edited preview prompt" } });
    expect(previewPrompt.value).toBe("edited preview prompt");
    const copyLink = within(previewDialog).getByRole("link", { name: "Copy Prompt Batch" });
    expect(decodeURIComponent(copyLink.getAttribute("href") ?? "")).toContain("Prompt 1: edited preview prompt");

    fireEvent.change(manualPrompt, { target: { value: "changed manual prompt" } });
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
    expect(within(promptLauncher).queryByRole("button", { name: "Review Prompts" })).not.toBeInTheDocument();
    fireEvent.change(manualPrompt, { target: { value: "manual override prompt" } });
    fireEvent.click(within(promptLauncher).getByRole("button", { name: "Review Prompts" }));
    const reopenedDialog = screen.getByRole("dialog", { name: "Prompt Preview" });
    expect((within(reopenedDialog).getByLabelText("Prompt 1") as HTMLTextAreaElement).value).toBe("edited preview prompt");

    fireEvent.click(within(reopenedDialog).getByText("Advanced Details"));
    expect(within(reopenedDialog).getByText("Prompt Plan: plan-preview")).toBeInTheDocument();
    expect(within(reopenedDialog).getByText("Creative Mode: premium_teaser")).toBeInTheDocument();
    expect(within(reopenedDialog).getByText(/canonical_premium_prompt_planner/)).toBeInTheDocument();

    fireEvent.click(within(reopenedDialog).getByRole("button", { name: "Regenerate Prompt Preview" }));
    await waitFor(() => expect(previewCalls()).toHaveLength(2));
    expect(within(screen.getByRole("dialog", { name: "Prompt Preview" })).getByText("Premium Prompt Preview regenerated.")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("dialog", { name: "Prompt Preview" })).getByRole("button", { name: "Save & Close" }));
    expect(screen.queryByRole("dialog", { name: "Prompt Preview" })).not.toBeInTheDocument();
  });

  it("runs Canonical Prompt Planner Q&A with transient images and newest-first session history", async () => {
    render(<ContentStudioPage />);

    const planner = await screen.findByRole("region", { name: "Canonical Prompt Planner Q&A" });
    const question = within(planner).getByLabelText("Ask Canonical Prompt Planner");
    const ask = within(planner).getByRole("button", { name: "Ask Planner" });
    const manual = within(screen.getByRole("region", { name: "Manual Prompt" })).getByLabelText("Manual Prompt");

    expect(ask).toBeDisabled();
    fireEvent.change(manual, { target: { value: "unrelated manual state" } });
    fireEvent.change(question, { target: { value: "  first question  " } });
    fireEvent.click(ask);
    expect(await within(planner).findByText("answer for first question", { selector: "p" })).toBeInTheDocument();

    fireEvent.click(within(planner).getByRole("button", { name: "Ask Canonical Prompt Planner another question" }));
    expect(question).toHaveValue("");
    const image = new File(["image bytes"], "pose.webp", { type: "image/webp" });
    fireEvent.change(within(planner).getByLabelText("Add Image"), { target: { files: [image] } });
    fireEvent.change(question, { target: { value: "second question" } });
    fireEvent.click(ask);
    expect(await within(planner).findByText("answer for second question with image", { selector: "p" })).toBeInTheDocument();
    const responses = planner.querySelectorAll(".canonical-prompt-planner__response");
    expect(responses).toHaveLength(2);
    expect(responses[0]).toHaveTextContent("second question");
    expect(responses[0]).toHaveTextContent("pose.webp");
    expect(responses[1]).toHaveTextContent("first question");
    expect(planner.querySelector(".canonical-prompt-planner__history details")).not.toBeInTheDocument();
    const plannerCalls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/prompt-planner/ask"));
    expect((plannerCalls[0]![1]?.body as FormData).get("question")).toBe("first question");
    const submittedImage = (plannerCalls[1]![1]?.body as FormData).get("image") as File;
    expect(submittedImage.name).toBe("pose.webp");
    expect(submittedImage.type).toBe("image/webp");

    fireEvent.click(within(planner).getByRole("button", { name: "Clear" }));
    expect(within(planner).queryByText("Canonical Prompt Planner Responses")).not.toBeInTheDocument();
    expect(question).toHaveValue("");
    expect(manual).toHaveValue("unrelated manual state");
  });

  it("prevents duplicate planner submissions while loading and renders controlled backend errors", async () => {
    let resolveRequest: ((response: object) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      resolveRequest = (responseValue) => resolve({
        headers: new Headers({ "content-type": "application/json" }),
        json: () => Promise.resolve(responseValue),
        ok: true,
        status: 200,
      });
    })));
    render(<CanonicalPromptPlannerSection disabled={false} />);
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));

    const loadingButton = screen.getByRole("button", { name: "Asking Canonical Prompt Planner..." });
    expect(loadingButton).toBeDisabled();
    fireEvent.click(loadingButton);
    expect(fetch).toHaveBeenCalledTimes(1);
    resolveRequest?.({ success: false, error: "Planner provider is unavailable.", answer: "" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Planner provider is unavailable.");
    expect(screen.getByRole("button", { name: "Ask Planner" })).toBeEnabled();
  });

  it("renders planner recommendations as self-contained aligned rows without a copy action", async () => {
    const markdown = "# Direction\n\n- First beat\n- **Bold beat**\n\n1. Frame\n2. Finish\n\n*soft*\n\n```text\ncode block\n```";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve({ success: true, error: null, answer: markdown }),
      ok: true,
      status: 200,
    }));
    render(<CanonicalPromptPlannerSection disabled={false} />);
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Plan this" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Direction" })).toBeInTheDocument();
    expect(screen.getByText("Bold beat").tagName).toBe("STRONG");
    expect(screen.getByText("soft").tagName).toBe("EM");
    expect(screen.getByText("code block").tagName).toBe("CODE");
    expect(document.querySelectorAll(".canonical-prompt-planner__response details")).toHaveLength(0);
    expect(document.querySelectorAll(".canonical-prompt-planner__recommendation")).toHaveLength(4);
    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
    expect(screen.getByRole("button", { name: /Enhance & Generate \(0\)/ })).toBeDisabled();
    expect(document.querySelectorAll(".canonical-prompt-planner__ideas")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
    expect(stylesheetText).toMatch(/\.canonical-prompt-planner__content label\.canonical-prompt-planner__recommendation\s*\{[^}]*grid-template-columns:\s*1rem minmax\(0, 1fr\)[^}]*column-gap:\s*\.875rem/);
    expect(stylesheetText).toMatch(/\.canonical-prompt-planner__recommendation input\s*\{[^}]*grid-column:\s*1[^}]*grid-row:\s*1/);
    expect(stylesheetText).toMatch(/\.canonical-prompt-planner__idea-text\s*\{[^}]*grid-column:\s*2[^}]*grid-row:\s*1/);
    expect(stylesheetText).toMatch(/\.canonical-prompt-planner__bulk-actions button\s*\{[^}]*min-height:\s*2\.125rem/);
  });

  it("submits generation inputs and renders backend-owned live progress and completed images", async () => {
    mockContext(readyContext, configuration, [], "1. Continue with a closer window portrait.\n2. Explore a seated variation.");
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    render(<ContentStudioPage />);

    const tags = await screen.findByLabelText("Creative Concept");
    const plannerInput = screen.getByLabelText("Ask Canonical Prompt Planner") as HTMLTextAreaElement;
    fireEvent.change(plannerInput, { target: { value: "Continue this direction" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));
    expect(await screen.findAllByRole("checkbox")).toHaveLength(3);
    expect(screen.queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Next Step" })).not.toBeInTheDocument();
    expect(stylesheetText).toMatch(/\.generation-live__images\s*\{[^}]*display:\s*grid/);
    expect(stylesheetText).toMatch(/\.generation-live__slot img,[\s\S]*?aspect-ratio:\s*1/);
    const count = await screen.findByLabelText("Prompt Count") as HTMLInputElement;
    await waitFor(() => expect(count.value).toBe("5"));
    fireEvent.change(count, { target: { value: "10" } });
    await waitFor(() => expect(count.value).toBe("10"));
    fireEvent.change(tags, { target: { value: "hotel mirror scene" } });
    const generate = screen.getByRole("button", { name: "🚀 Create Images" });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);
    const liveRegion = await screen.findByRole("region", { name: "Live Generation" });
    expect(screen.queryByRole("region", { name: "Next Step" })).not.toBeInTheDocument();
    await waitFor(() => expect(
      within(liveRegion).getAllByRole("img", { name: /Waiting for generated image/ }),
    ).toHaveLength(10));
    const reservedSlots = within(liveRegion).getAllByRole("figure");
    expect(within(liveRegion).getByLabelText("Generated image slots")).toHaveStyle({ "--generation-columns": "5" });

    const generationCall = await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/generations"));
      expect(call).toBeDefined();
      return call;
    });
    expect(JSON.parse(String(generationCall?.[1]?.body))).toEqual({
      provider: "seedream_5_0_pro",
      promptSource: "[ORIGINAL USER TAGS — mandatory: hotel mirror scene] [ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: enhanced hotel mirror scene]",
      promptSourceLabel: "Enhanced Tags",
      promptBatch: ["preview prompt one", "preview prompt two"],
      creativeMode: "premium_teaser",
      promptCount: 10,
      creatorContext: { activeReferenceAssetId: 42, status: "ready" },
    });
    expect(await screen.findByText("Completed: 1", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.getByText("Failed: 9")).toBeInTheDocument();
    expect(screen.getByText("Provider: seedream_5_0_pro")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Generated image 1 of 10" })).toHaveAttribute(
      "src", "/api/v1/content-studio/generations/run-live/images/0",
    );
    expect(within(liveRegion).getAllByRole("img", { name: /Waiting for generated image/ })).toHaveLength(9);
    const completedSlots = within(liveRegion).getAllByRole("figure");
    expect(completedSlots).toHaveLength(10);
    completedSlots.forEach((slot, index) => expect(slot).toBe(reservedSlots[index]));
    expect(screen.getByText("Generation completed with partial success.")).toBeInTheDocument();

    const nextStep = screen.getByRole("region", { name: "Next Step" });
    expect(within(nextStep).getByText("Continue building on this creative direction or begin a new one.")).toBeInTheDocument();
    fireEvent.click(within(nextStep).getByRole("button", { name: /Continue Exploring/ }));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(screen.getAllByText("Continue this direction")).toHaveLength(2);
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);

    fireEvent.click(within(nextStep).getByRole("button", { name: /Ask Another Question/ }));
    await waitFor(() => expect(plannerInput).toHaveFocus());
    expect(plannerInput).toHaveValue("Continue this direction");
    expect(screen.getByText("Continue with a closer window portrait.")).toBeInTheDocument();

    fireEvent.click(within(nextStep).getByRole("button", { name: /Start New Session/ }));
    await waitFor(() => expect(plannerInput).toHaveFocus());
    expect(plannerInput).toHaveValue("");
    expect(screen.queryByText("Canonical Prompt Planner Responses")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Select All" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Generated image 1 of 10" })).toBeInTheDocument();
    expect(screen.getByText("Generation completed with partial success.")).toBeInTheDocument();
  });
});
