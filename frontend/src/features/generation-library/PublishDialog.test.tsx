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
  it("shows only X and Telegram Broadcast marketing destinations", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [
        { value: "x", label: "X", available: true },
        { value: "telegram_wall", label: "Telegram Broadcast", available: true },
        { value: "telegram_chat", label: "Telegram Chat", available: true },
      ],
      xAccounts: [
        { accountName: "AvaBlackthorne", label: "@avablackthorne" },
        { accountName: "AvaBlackthorneX", label: "@avablackthorneX" },
      ],
    }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    expect(await screen.findByLabelText("X")).toBeChecked();
    expect(screen.getByLabelText("@avablackthorne")).toBeChecked();
    expect(screen.getByLabelText("@avablackthorneX")).not.toBeChecked();
    expect(screen.getByLabelText("Telegram Broadcast")).toBeInTheDocument();
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

  it("publishes either or both X accounts with shared or separate captions", async () => {
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
    fetch.mockImplementation(() => jsonResponse({ success: true, message: "Published to 2 X account(s)." }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    fireEvent.click(await screen.findByLabelText("@avablackthorneX"));
    expect(screen.getByLabelText("Use same caption for both accounts")).toBeChecked();
    fireEvent.change(screen.getByLabelText("Enter Your Own Caption"), { target: { value: "Shared caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to X" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String((fetch.mock.calls[1]![1] as RequestInit).body)).xTargets).toEqual([
      expect.objectContaining({ accountName: "AvaBlackthorne", caption: "Shared caption" }),
      expect.objectContaining({ accountName: "AvaBlackthorneX", caption: "Shared caption" }),
    ]);
    fetch.mockRestore();
  });

  it("supports separate captions for both X accounts", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => jsonResponse({
      success: true, generatedImageId: "generated-1", defaultDestination: "x",
      destinations: [{ value: "x", label: "X", available: true }],
      xAccounts: [
        { accountName: "AvaBlackthorne", label: "@avablackthorne" },
        { accountName: "AvaBlackthorneX", label: "@avablackthorneX" },
      ],
    }));
    fetch.mockImplementation(() => jsonResponse({ success: true, message: "Published to 2 X account(s)." }));
    render(<PublishDialog record={record} onClose={vi.fn()} onPublished={vi.fn()} />);

    fireEvent.click(await screen.findByLabelText("@avablackthorneX"));
    fireEvent.click(screen.getByLabelText("Use same caption for both accounts"));
    fireEvent.change(screen.getByLabelText("Caption for @avablackthorne"), { target: { value: "Main caption" } });
    fireEvent.change(screen.getByLabelText("Caption for @avablackthorneX"), { target: { value: "Second caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish to X" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String((fetch.mock.calls[1]![1] as RequestInit).body)).xTargets).toEqual([
      expect.objectContaining({ accountName: "AvaBlackthorne", caption: "Main caption" }),
      expect.objectContaining({ accountName: "AvaBlackthorneX", caption: "Second caption" }),
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
