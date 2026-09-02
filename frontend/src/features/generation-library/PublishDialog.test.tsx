import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PublishDialog } from "./PublishDialog";
import type { GenerationRecord } from "./types";

const record: GenerationRecord = {
  image_id: "generated-1", image_url: "/image.png", provider_id: "seedream", prompt_text: "Portrait",
  creative_mode: "premium_teaser", generation_date: "2026-01-01T00:00:00Z", status: "active",
  generation_job_id: "job-1", generation_request_id: "request-1", generation_result_id: "result-1",
  prompt_plan_id: "plan-1", reference_asset_id: 1, imported_asset_id: null,
  provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
};

const jsonResponse = (value: unknown, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  statusText: status === 200 ? "OK" : "Error",
  json: () => Promise.resolve(value),
  text: () => Promise.resolve(JSON.stringify(value)),
} as Response);

describe("PublishDialog", () => {
  it("shows X, Telegram Broadcast, and Instagram handoff destinations", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [
        { value: "x", label: "X", available: true },
        { value: "telegram_wall", label: "Telegram Broadcast", available: true },
        { value: "telegram_chat", label: "Telegram Chat", available: true },
        { value: "instagram", label: "Instagram", available: true },
      ],
      xAccounts: [
        { accountName: "AvaBlackthorne", label: "@avablackthorne" },
        { accountName: "AvaBlackthorneX", label: "@avablackthorneX" },
      ],
    }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    expect(await screen.findByLabelText("X")).toBeChecked();
    expect(screen.getByLabelText("@avablackthorne")).toBeChecked();
    expect(screen.queryByLabelText("@avablackthorneX")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Enable X-AUTO replies")).toBeChecked();
    expect(screen.getByLabelText("Telegram Broadcast")).toBeInTheDocument();
    expect(screen.getByLabelText("Instagram")).toBeInTheDocument();
    expect(screen.queryByText("Telegram Chat")).not.toBeInTheDocument();
    expect(screen.queryByText("Fanvue")).not.toBeInTheDocument();
    const selectedImage = within(screen.getByLabelText("Selected image preview")).getByRole("img");
    expect(selectedImage).toHaveAttribute("src", record.image_url);
    fireEvent.change(screen.getByLabelText("Enter Your Own Caption"), { target: { value: "Manual caption" } });
    expect(selectedImage).toBeVisible();
    const captionPreview = screen.getByRole("heading", { name: "Caption preview" }).closest("section");
    expect(within(captionPreview as HTMLElement).getByText("Manual caption")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to X" })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(1);
    fetch.mockRestore();
  });

  it("hands the exact image and caption to Instagram without Telegram controls", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [
        { value: "x", label: "X", available: true },
        { value: "telegram_wall", label: "Telegram Broadcast", available: true },
        { value: "instagram", label: "Instagram", available: true },
      ],
      xAccounts: [{ accountName: "AvaBlackthorne", label: "@avablackthorne" }],
    }));
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, state: "HANDOFF_READY",
      message: "Sent to phone — finish your post in Instagram.",
      generatedImageId: "generated-1",
    }));
    const onPublished = vi.fn();
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={onPublished} />);

    fireEvent.click(await screen.findByLabelText("Instagram"));
    expect(screen.queryByLabelText("Include CTA buttons")).not.toBeInTheDocument();
    const editor = screen.getByLabelText("Enter Your Own Caption");
    expect(editor).toHaveAttribute("placeholder", "Type or paste your own Instagram caption here.");
    fireEvent.change(editor, { target: { value: "Instagram caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to Instagram" }));

    await waitFor(() => expect(onPublished).toHaveBeenCalledWith(
      "Sent to phone — finish your post in Instagram.",
    ));
    expect(String(fetch.mock.calls[1]![0])).toContain(
      "/generation-library/generated-1/publish/instagram/handoff",
    );
    expect(JSON.parse(String((fetch.mock.calls[1]![1] as RequestInit).body))).toEqual({
      caption: "Instagram caption",
    });
    fetch.mockRestore();
  });

  it("publishes an edited generated caption to the selected destination", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [
        { value: "x", label: "X", available: true },
        { value: "telegram_wall", label: "Telegram Broadcast", available: true },
      ],
      xAccounts: [
        { accountName: "AvaBlackthorne", label: "@avablackthorne" },
        { accountName: "AvaBlackthorneX", label: "@avablackthorneX" },
      ],
    }));
    fetch.mockImplementationOnce(() => jsonResponse({ success: true, captionResultId: "caption-1", themes: [{ theme: "Theme", captions: ["Generated caption"] }] }));
    fetch.mockImplementationOnce(() => jsonResponse({ success: true, message: "Published to Telegram." }));
    const onPublished = vi.fn();
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={onPublished} />);

    fireEvent.click(await screen.findByLabelText("Telegram Broadcast"));
    fireEvent.click(screen.getByRole("button", { name: "Generate Captions" }));
    fireEvent.click(await screen.findByRole("button", { name: "Generated caption" }));
    fireEvent.change(screen.getByLabelText("Enter Your Own Caption"), { target: { value: "Edited caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to Telegram Broadcast" }));
    await waitFor(() => expect(onPublished).toHaveBeenCalledWith("Published to Telegram."));
    expect(screen.getByLabelText("Enter Your Own Caption")).toHaveValue("Edited caption");
    expect(fetch).toHaveBeenCalledTimes(3);
    await waitFor(() => expect(fetch.mock.calls[1]![0]).toContain("/publish/captions"));
    expect(JSON.parse(String((fetch.mock.calls[2]![1] as RequestInit).body))).toMatchObject({
      destination: "telegram_wall",
      caption: "Edited caption",
      selectedGeneratedCaption: "Generated caption",
    });
    fetch.mockRestore();
  });

  it("publishes all semantic CTAs in canonical order regardless of click order", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "telegram_wall",
      destinations: [{ value: "telegram_wall", label: "Telegram Broadcast", available: true }],
    }));
    fetch.mockImplementationOnce(() => jsonResponse({ success: true, message: "Published to Telegram." }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    fireEvent.change(await screen.findByLabelText("Enter Your Own Caption"), { target: { value: "Caption" } });
    expect(screen.queryByRole("button", { name: "🔒 Vault" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Include CTA buttons"));
    const vault = screen.getByRole("button", { name: "🔒 Vault" });
    const chat = screen.getByRole("button", { name: "💬 Chat" });
    const tip = screen.getByRole("button", { name: "❤️ Tip" });
    expect(vault).toHaveAttribute("aria-pressed", "false");
    expect(chat).toHaveAttribute("aria-pressed", "false");
    expect(tip).toHaveAttribute("aria-pressed", "false");
    expect(chat).toBeEnabled();
    expect(tip).toBeEnabled();
    expect(screen.queryByText("Button Text")).not.toBeInTheDocument();
    expect(screen.queryByText("Button URL")).not.toBeInTheDocument();
    fireEvent.click(tip);
    fireEvent.click(chat);
    fireEvent.click(vault);
    expect(vault).toHaveAttribute("aria-pressed", "true");
    expect(chat).toHaveAttribute("aria-pressed", "true");
    expect(tip).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Publish to Telegram Broadcast" }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const payload = JSON.parse(String((fetch.mock.calls[1]![1] as RequestInit).body));
    expect(payload).toMatchObject({ ctaEnabled: true, selectedCtas: ["VAULT", "CHAT", "TIP"] });
    expect(payload).not.toHaveProperty("ctaLabel");
    expect(payload).not.toHaveProperty("ctaUrl");
    fetch.mockRestore();
  });

  it("publishes the visible X account with explicit per-post X-AUTO policy", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [
        { value: "x", label: "X", available: true },
        { value: "telegram_wall", label: "Telegram Broadcast", available: true },
      ],
      xAccounts: [
        { accountName: "AvaBlackthorne", label: "@avablackthorne" },
        { accountName: "AvaBlackthorneX", label: "@avablackthorneX" },
      ],
    }));
    fetch.mockImplementation(() => jsonResponse({ success: true, message: "Published to 1 X account(s)." }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    expect(await screen.findByLabelText("@avablackthorne")).toBeChecked();
    expect(screen.queryByLabelText("@avablackthorneX")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Enable X-AUTO replies"));
    fireEvent.change(screen.getByLabelText("Enter Your Own Caption"), { target: { value: "Shared caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to X" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const payload = JSON.parse(String((fetch.mock.calls[1]![1] as RequestInit).body));
    expect(payload.xAutoRepliesEnabled).toBe(false);
    expect(payload.xTargets).toEqual([
      expect.objectContaining({ accountName: "AvaBlackthorne", caption: "Shared caption" }),
    ]);
    fetch.mockRestore();
  });

  it("keeps caption edits visible when publishing fails", async () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "telegram_wall",
      destinations: [{ value: "telegram_wall", label: "Telegram Broadcast", available: true }],
    }));
    fetch.mockImplementationOnce(() => jsonResponse({
      success: false,
      error: "Telegram authentication failed.",
      exceptionType: "TelegramAuthenticationError",
    }, 400));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    const editor = await screen.findByLabelText("Enter Your Own Caption");
    fireEvent.change(editor, { target: { value: "Keep this edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to Telegram Broadcast" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "TelegramAuthenticationError: Telegram authentication failed.",
    );
    expect(editor).toHaveValue("Keep this edit");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(console.info).toHaveBeenCalledWith(
      "[Generation Library Publish] Response",
      expect.objectContaining({ status: 400, responseBody: expect.stringContaining("Telegram authentication failed.") }),
    );
    fetch.mockRestore();
  });

  it("shows FastAPI detail responses instead of a generic publishing error", async () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "telegram_wall",
      destinations: [{ value: "telegram_wall", label: "Telegram Broadcast", available: true }],
    }));
    fetch.mockImplementationOnce(() => jsonResponse({ detail: "Method Not Allowed" }, 405));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    fireEvent.change(await screen.findByLabelText("Enter Your Own Caption"), { target: { value: "Caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to Telegram Broadcast" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Method Not Allowed");
    expect(console.error).toHaveBeenCalledWith(
      "[Generation Library Publish] Exception",
      expect.objectContaining({ exceptionType: "Error", exceptionMessage: "Method Not Allowed" }),
    );
    fetch.mockRestore();
  });
});
