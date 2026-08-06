import { afterEach, describe, expect, it, vi } from "vitest";
import { installButtonPressFeedback } from "./installButtonPressFeedback";

describe("global button press feedback", () => {
  afterEach(() => { document.body.innerHTML = ""; vi.restoreAllMocks(); });

  it("keeps the pressed marker through a synchronous loading transition", () => {
    let releaseFrame: FrameRequestCallback | undefined;
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => { releaseFrame = callback; return 1; }));
    const uninstall = installButtonPressFeedback();
    const button = document.createElement("button");
    button.textContent = "Generate";
    document.body.append(button);
    const down = new Event("pointerdown", { bubbles: true });
    Object.defineProperty(down, "button", { value: 0 });
    button.dispatchEvent(down);
    button.disabled = true;
    button.dispatchEvent(new Event("pointerup", { bubbles: true }));
    expect(button).toHaveAttribute("data-creator-pressed", "true");
    releaseFrame?.(0);
    expect(button).not.toHaveAttribute("data-creator-pressed");
    uninstall();
  });
});
