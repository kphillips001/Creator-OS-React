import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "../../app/router/router";
import { ContentStudioPage } from "./ContentStudioPage";
import { CanonicalPromptPlannerSection } from "./components/CanonicalPromptPlannerSection";

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

function mockContext(value: object, configurationValue: object = configuration, archiveValue: object[] = []) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, options?: RequestInit) => {
    let responseValue = url.endsWith("/configuration")
      ? configurationValue
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
          answer: `answer for ${plannerBody.get("question")}${plannerBody.get("image") ? " with image" : ""}`,
        };
        return Promise.resolve({
          headers: new Headers({ "content-type": "application/json" }),
          json: () => Promise.resolve(responseValue),
          ok: true,
          status: 200,
        });
      }
      const body = JSON.parse(String(options.body)) as { explicit?: boolean; tags?: string };
      if (url.endsWith("/generations")) {
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
        const tags = url.endsWith("/lucky")
          ? body.explicit ? "lucky explicit tags" : "lucky premium tags"
          : url.endsWith("/surprise")
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
      "Premium Creative Mode / Prompt Count / Provider",
      "Creative Director Tools",
      "Canonical Prompt Planner Q&A",
      "Prompt Workshop",
      "Manual Prompt",
      "Prompt Preview",
    ];

    await screen.findByRole("region", { name: titles[0] });
    for (const title of titles) {
      expect(screen.getByRole("region", { name: title })).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeInTheDocument();
    }

    const renderedTitles = Array.from(
      container.querySelectorAll(".workflow-section h2"),
      (heading) => heading.textContent,
    );
    expect(renderedTitles).toEqual(titles);
    expect(screen.getByRole("region", { name: "Generate Images" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Generate Images" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Premium Images" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(screen.queryByText("Active Reference")).not.toBeInTheDocument();
    expect(screen.queryByText("Active Reference selected: Asset #42")).not.toBeInTheDocument();
    expect(screen.queryByText(/Last used:/)).not.toBeInTheDocument();
    expect(screen.getByText(
      "Premium creator workflow for provider-neutral prompt planning and generation review.",
    )).toBeInTheDocument();
  });

  it("uses a responsive vertical flow without the removed dashboard panels", () => {
    render(<ContentStudioPage />);

    expect(stylesheetText).toMatch(/\.content-studio__workflow\s*\{[^}]*flex-direction:\s*column/);
    expect(stylesheetText).toContain("(max-width: 680px)");
    expect(screen.queryByText("Creative workflow")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reference Image" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Prompt Workspace" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Generation Timeline" })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("region", { name: "Creative Director Tools" })).not.toBeInTheDocument();
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
    expect(screen.getByRole("region", { name: "Generate Images" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("region", { name: "Canonical Prompt Planner Q&A" })).not.toHaveAttribute("aria-disabled");
  });

  it("loads creator defaults, provider options, and validates prompt count locally", async () => {
    render(<ContentStudioPage />);

    const mode = await screen.findByLabelText("Premium Creative Mode") as HTMLSelectElement;
    const count = await screen.findByLabelText("Prompt Count") as HTMLInputElement;
    const provider = screen.getByLabelText("Provider") as HTMLSelectElement;

    expect(mode.value).toBe("premium_teaser");
    expect(Array.from(mode.options, (option) => [option.text, option.value])).toEqual([
      ["Standard", "premium_teaser"],
      ["Spicy", "spicy"],
    ]);
    expect(count).toHaveAttribute("min", "1");
    expect(count).toHaveAttribute("max", "20");
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
    expect(fetch).toHaveBeenCalledTimes(3);
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

  it("runs every Creative Director tag action through the backend and keeps editable session state", async () => {
    render(<ContentStudioPage />);

    const premiumTags = await screen.findByLabelText("Premium Creative Tags") as HTMLTextAreaElement;
    const explicitTags = screen.getByLabelText("Explicit Tags") as HTMLTextAreaElement;
    await waitFor(() => expect(screen.getByRole("button", { name: /🎲 I Feel Lucky/ })).toBeEnabled());

    fireEvent.click(screen.getByRole("button", { name: /🎲 I Feel Lucky/ }));
    await waitFor(() => expect(premiumTags.value).toBe("lucky premium tags"));
    expect(screen.getByLabelText("Original")).toBeChecked();

    fireEvent.change(premiumTags, { target: { value: "hotel robe" } });
    fireEvent.click(screen.getByRole("button", { name: /Enhance Premium Tags/ }));
    const enhanced = screen.getByLabelText("Enhanced Premium Tags") as HTMLTextAreaElement;
    await waitFor(() => expect(enhanced.value).toBe("enhanced hotel robe"));
    expect(screen.getByLabelText("Enhanced")).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /Surprise Me/ }));
    const surprised = screen.getByLabelText("Surprise Me Tags") as HTMLTextAreaElement;
    await waitFor(() => expect(surprised.value).toBe("surprised hotel robe"));
    expect(screen.getByLabelText("Surprise Me")).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /🔥 I Feel Lucky/ }));
    await waitFor(() => expect(explicitTags.value).toBe("lucky explicit tags"));

    fireEvent.change(explicitTags, { target: { value: "explicit hotel" } });
    fireEvent.click(screen.getByRole("button", { name: /Enhance Explicit Tags/ }));
    const enhancedExplicit = screen.getByLabelText("Enhanced Explicit Tags") as HTMLTextAreaElement;
    await waitFor(() => expect(enhancedExplicit.value).toBe("explicitly enhanced explicit hotel"));
    expect(screen.getByLabelText("Enhanced Explicit")).toBeChecked();

    expect(screen.getByRole("radio", { name: "Prompt Workshop" })).toBeInTheDocument();
    const postCalls = vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === "POST");
    expect(postCalls).toHaveLength(5);
    expect(postCalls[0]![0]).toBe("/api/v1/content-studio/creative-tags/lucky");
    expect(JSON.parse(String(postCalls[0]![1]?.body))).toEqual({ explicit: false, promptCount: 5 });
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

    expect(await screen.findByLabelText("Premium Creative Tags")).toBeDisabled();
    expect(screen.getByRole("region", { name: "Creative Director Tools" })).toHaveAttribute("aria-disabled", "true");
  });

  it("generates and edits Prompt Workshop batches and reuses the backend archive", async () => {
    const archivedBatch = {
      batchId: "batch-archived",
      createdAt: "2026-07-16T11:30:00",
      lane: "premium",
      prompts: ["archived prompt one", "archived prompt two"],
      requestText: "archived hotel brief",
      usedPromptNumbers: [2],
    };
    mockContext(readyContext, configuration, [archivedBatch]);
    render(<ContentStudioPage />);

    const brief = await screen.findByLabelText("Prompt Workshop Brief");
    await waitFor(() => expect(brief).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Prompt Mode"), { target: { value: "explicit" } });
    fireEvent.change(brief, { target: { value: "hotel sequence" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate Prompts" }));

    const firstPrompt = await screen.findByLabelText("Prompt 1") as HTMLTextAreaElement;
    expect(firstPrompt.value).toBe("generated prompt one");
    fireEvent.change(firstPrompt, { target: { value: "edited generated prompt" } });
    expect(firstPrompt.value).toBe("edited generated prompt");

    fireEvent.click(screen.getByRole("button", { name: "Accept Selected" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: "Prompt Workshop" })).toBeChecked());
    fireEvent.click(screen.getByRole("button", { name: "Accept All" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy Prompt" }));
    expect(await screen.findByText("edited generated prompt", { selector: "pre" })).toBeInTheDocument();

    fireEvent.click(screen.getByText("Prompt Workshop Archive"));
    expect(screen.getByText("archived prompt one")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent("used archived prompt two");
    fireEvent.click(screen.getByRole("button", { name: "Use Archived" }));
    await waitFor(() => expect(screen.getByText("Archived prompt selected.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Load Batch" }));
    await waitFor(() => expect((screen.getByLabelText("Prompt 1") as HTMLTextAreaElement).value).toBe("archived prompt one"));

    const generateCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/prompt-workshop/generate"));
    expect(JSON.parse(String(generateCall?.[1]?.body))).toEqual({
      lane: "explicit",
      promptCount: 5,
      requestText: "hotel sequence",
    });
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/prompt-workshop/archive/batch-new/use"))).toBe(true);
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/prompt-workshop/archive/batch-archived/use"))).toBe(true);
  });

  it("uses Manual Prompt as the preview override and preserves valid preview edits", async () => {
    render(<ContentStudioPage />);

    const creativeTags = await screen.findByLabelText("Premium Creative Tags");
    const manualRegion = screen.getByRole("region", { name: "Manual Prompt" });
    const manualPrompt = within(manualRegion).getByLabelText("Manual Prompt");
    const previewRegion = screen.getByRole("region", { name: "Prompt Preview" });
    const createButton = within(previewRegion).getByRole("button", { name: "Create Prompt Preview" });

    expect(manualPrompt).toHaveValue("");
    expect(createButton).toBeDisabled();
    fireEvent.change(creativeTags, { target: { value: "original premium tags" } });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.change(manualPrompt, { target: { value: "manual override prompt" } });
    fireEvent.click(createButton);

    const previewPrompt = await within(previewRegion).findByLabelText("Prompt 1") as HTMLTextAreaElement;
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
    const copyLink = within(previewRegion).getByRole("link", { name: "Copy Prompt Batch" });
    expect(decodeURIComponent(copyLink.getAttribute("href") ?? "")).toContain("Prompt 1: edited preview prompt");

    fireEvent.change(manualPrompt, { target: { value: "changed manual prompt" } });
    expect(within(previewRegion).queryByRole("link", { name: "Copy Prompt Batch" })).not.toBeInTheDocument();
    expect(within(previewRegion).getByText(/Prompt Preview is ready/)).toBeInTheDocument();
    fireEvent.change(manualPrompt, { target: { value: "manual override prompt" } });
    expect((within(previewRegion).getByLabelText("Prompt 1") as HTMLTextAreaElement).value).toBe("edited preview prompt");

    fireEvent.click(within(previewRegion).getByText("Advanced Details"));
    expect(within(previewRegion).getByText("Prompt Plan: plan-preview")).toBeInTheDocument();
    expect(within(previewRegion).getByText("Creative Mode: premium_teaser")).toBeInTheDocument();
    expect(within(previewRegion).getByText(/canonical_premium_prompt_planner/)).toBeInTheDocument();

    fireEvent.click(within(previewRegion).getByRole("button", { name: "Regenerate Prompt Preview" }));
    await waitFor(() => expect(previewCalls()).toHaveLength(2));
    expect(within(previewRegion).getByText("Premium Prompt Preview regenerated.")).toBeInTheDocument();
  });

  it("runs Canonical Prompt Planner Q&A with transient images and newest-first session history", async () => {
    render(<ContentStudioPage />);

    const planner = await screen.findByRole("region", { name: "Canonical Prompt Planner Q&A" });
    fireEvent.click(within(planner).getByText("Canonical Prompt Planner Q&A"));
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
    fireEvent.click(screen.getByText("Canonical Prompt Planner Q&A"));
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

  it("renders planner answers as direct Markdown responses and copies the source answer", async () => {
    const markdown = "# Direction\n\n- First beat\n- **Bold beat**\n\n1. Frame\n2. Finish\n\n*soft*\n\n```text\ncode block\n```";
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve({ success: true, error: null, answer: markdown }),
      ok: true,
      status: 200,
    }));
    render(<CanonicalPromptPlannerSection disabled={false} />);
    fireEvent.click(screen.getByText("Canonical Prompt Planner Q&A"));
    fireEvent.change(screen.getByLabelText("Ask Canonical Prompt Planner"), { target: { value: "Plan this" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Planner" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Direction" })).toBeInTheDocument();
    expect(screen.getByText("Bold beat").tagName).toBe("STRONG");
    expect(screen.getByText("soft").tagName).toBe("EM");
    expect(screen.getByText("code block").tagName).toBe("CODE");
    expect(document.querySelectorAll(".canonical-prompt-planner__response details")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(markdown);
  });

  it("submits generation inputs and renders backend-owned live progress and completed images", async () => {
    render(<ContentStudioPage />);

    const tags = await screen.findByLabelText("Premium Creative Tags");
    expect(screen.queryByRole("region", { name: "Live Generation" })).not.toBeInTheDocument();
    expect(stylesheetText).toMatch(/\.generation-live__images\s*\{[^}]*display:\s*grid/);
    expect(stylesheetText).toMatch(/\.generation-live__slot img,[\s\S]*?aspect-ratio:\s*1/);
    const count = screen.getByLabelText("Prompt Count") as HTMLInputElement;
    await waitFor(() => expect(count.value).toBe("5"));
    fireEvent.change(count, { target: { value: "10" } });
    await waitFor(() => expect(count.value).toBe("10"));
    fireEvent.change(tags, { target: { value: "hotel mirror scene" } });
    const generate = screen.getByRole("button", { name: "Generate Premium Images" });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);
    const liveRegion = await screen.findByRole("region", { name: "Live Generation" });
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
      promptSource: "hotel mirror scene",
      promptSourceLabel: "Original Tags",
      promptBatch: [],
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
  });
});
