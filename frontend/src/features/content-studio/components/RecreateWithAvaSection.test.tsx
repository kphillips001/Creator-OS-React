import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecreateWithAvaSection } from "./RecreateWithAvaSection";

const analysis = { scene: "Loft", pose: "Seated", camera_angle: "Eye level", camera_framing: "Medium", lighting: "Window", composition: "Centered", wardrobe_concept: "Silk dress", expression: "Confident", mood: "Warm", environment: "Interior", color_palette: "Amber", styling: "Editorial", elements_to_preserve: ["lighting"], elements_to_ignore: ["uploaded subject face"], identity_transfer_prohibited: true, confidence: .9 };
const image = () => new File(["image"], "source.webp", { type: "image/webp" });

describe("RecreateWithAvaSection one-click workflow", () => {
  const runtime = () => ({ onRuntimeChange: vi.fn(), onRuntimeReset: vi.fn() });
  beforeEach(() => {
    vi.stubGlobal("URL", { createObjectURL: () => "blob:preview", revokeObjectURL: vi.fn() });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes("recreate/analyze") ? { success: true, error: null, analysis } : { success: true, error: null, tags: "Enhanced scene" }), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  it("shows one primary action, hides analysis, and automatically analyzes, enhances, and generates", async () => {
    const generate = vi.fn<(source: string, enhanced: string) => Promise<void>>().mockResolvedValue(undefined);
    const callbacks = runtime(); render(<RecreateWithAvaSection disabled={false} onGenerate={generate} {...callbacks} />);
    const action = screen.getByRole("button", { name: "Recreate With Ava" });
    expect(action).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Analyze Image" })).not.toBeInTheDocument();
    expect(screen.queryByText("Camera Angle")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Inspiration image"), { target: { files: [image()] } });
    expect(action).toBeEnabled(); fireEvent.click(action);
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
    expect(callbacks.onRuntimeChange.mock.calls.map(([state]) => state.activeStage)).toEqual(expect.arrayContaining([0, 1, 2, 3, 6]));
    expect(generate.mock.calls[0]?.[0]).toContain("Pose: Seated");
    expect(generate.mock.calls[0]?.[0]).not.toContain("source.webp");
    expect(generate.mock.calls[0]?.[1]).toBe("Enhanced scene");
    expect(screen.queryByText("Scene")).not.toBeInTheDocument();
    expect(await screen.findByText("More Options")).toBeInTheDocument();
  });

  it("routes dropped and pasted images through the same upload selection behavior", () => {
    const callbacks = runtime();
    const view = render(<RecreateWithAvaSection disabled={false} onGenerate={vi.fn()} {...callbacks} />);
    const upload = screen.getByRole("button", { name: "Upload inspiration image" });
    const dropped = new File(["drop"], "dropped.png", { type: "image/png" });
    fireEvent.drop(upload, { dataTransfer: { files: [dropped] } });
    expect(screen.getByText("dropped.png")).toBeInTheDocument();
    expect(callbacks.onRuntimeReset).toHaveBeenCalledTimes(1);

    view.unmount();
    const pastedCallbacks = runtime();
    render(<RecreateWithAvaSection disabled={false} onGenerate={vi.fn()} {...pastedCallbacks} />);
    const pasteTarget = screen.getByRole("button", { name: "Upload inspiration image" });
    const pasted = new File(["paste"], "clipboard-image.webp", { type: "image/webp" });
    const event = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "clipboardData", { value: { items: [{ type: "image/webp", getAsFile: () => pasted }] } });
    fireEvent(pasteTarget, event);
    expect(event.defaultPrevented).toBe(true);
    expect(screen.getByText("clipboard-image.webp")).toBeInTheDocument();
    expect(pastedCallbacks.onRuntimeReset).toHaveBeenCalledTimes(1);
  });

  it("ignores non-image and disabled paste without preventing browser behavior", () => {
    const view = render(<RecreateWithAvaSection disabled={false} onGenerate={vi.fn()} {...runtime()} />);
    const textPaste = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(textPaste, "clipboardData", { value: { items: [{ type: "text/plain", getAsFile: () => null }] } });
    fireEvent(screen.getByRole("button", { name: "Upload inspiration image" }), textPaste);
    expect(textPaste.defaultPrevented).toBe(false);
    expect(screen.getByRole("button", { name: "Recreate With Ava" })).toBeDisabled();

    view.unmount();
    render(<RecreateWithAvaSection disabled onGenerate={vi.fn()} {...runtime()} />);
    const disabledPaste = new Event("paste", { bubbles: true, cancelable: true });
    const pasted = new File(["paste"], "ignored.png", { type: "image/png" });
    Object.defineProperty(disabledPaste, "clipboardData", { value: { items: [{ type: "image/png", getAsFile: () => pasted }] } });
    fireEvent(screen.getByRole("button", { name: "Upload inspiration image" }), disabledPaste);
    expect(disabledPaste.defaultPrevented).toBe(false);
    expect(screen.queryByText("ignored.png")).not.toBeInTheDocument();
  });

  it("prevents duplicate clicks while the workflow is running", async () => {
    let finish!: () => void; const generate = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<RecreateWithAvaSection disabled={false} onGenerate={generate} {...runtime()} />);
    fireEvent.change(screen.getByLabelText("Inspiration image"), { target: { files: [image()] } });
    fireEvent.click(screen.getByRole("button", { name: "Recreate With Ava" }));
    const running = await screen.findByRole("button", { name: /Recreating With Ava/ });
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1)); fireEvent.click(running);
    expect(generate).toHaveBeenCalledTimes(1); finish();
  });

  it("attributes a prompt-preview failure to canonical prompt generation", async () => {
    const callbacks = runtime();
    render(<RecreateWithAvaSection disabled={false} onGenerate={vi.fn(async () => { throw new Error("Failed while creating canonical prompt."); })} {...callbacks} />);
    fireEvent.change(screen.getByLabelText("Inspiration image"), { target: { files: [image()] } });
    fireEvent.click(screen.getByRole("button", { name: "Recreate With Ava" }));
    await waitFor(() => expect(callbacks.onRuntimeChange).toHaveBeenCalledWith(expect.objectContaining({ activeStage: 3, failedStage: 3, state: "failed" })));
  });

  it("preserves the image on failure, supports retry, and resets when removed", async () => {
    const mockedFetch = vi.mocked(fetch); mockedFetch.mockRejectedValueOnce(new Error("Analysis unavailable"));
    const callbacks = runtime(); render(<RecreateWithAvaSection disabled={false} onGenerate={vi.fn()} {...callbacks} />);
    fireEvent.change(screen.getByLabelText("Inspiration image"), { target: { files: [image()] } });
    fireEvent.click(screen.getByRole("button", { name: "Recreate With Ava" }));
    await waitFor(() => expect(callbacks.onRuntimeChange).toHaveBeenCalledWith(expect.objectContaining({ failedStage: 1 })));
    expect(screen.getByText("source.webp")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recreate With Ava" }));
    await waitFor(() => expect(callbacks.onRuntimeChange).toHaveBeenCalledWith(expect.objectContaining({ state: "complete" })));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.getByRole("button", { name: "Recreate With Ava" })).toBeDisabled();
  });
});
