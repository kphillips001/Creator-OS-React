import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BundlePromotionalTeaser } from "./BundleTeaserEditor";

const styles = readFileSync(resolve("src/features/photoshoot-gallery/photoshoot-gallery.css"), "utf8");

const state = {
  status: "NOT_CONFIGURED" as const, statusLabel: "Teaser Not Configured",
  commercialRole: "BUNDLE_PROMOTIONAL_TEASER" as const, sourceAssetId: null,
  teaserAssetId: null, blurStrength: 24, maskWidth: null, maskHeight: null,
  maskVersion: "selective_blur_mask_v1", maskUrl: null, previewUrl: null, error: null,
  candidates: [{ assetId: 1, shotOrder: 1, imageUrl: "/one" },
    { assetId: 2, shotOrder: 2, imageUrl: "/two" }],
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const context = (painted = true) => ({
  clearRect: vi.fn(), fillRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), arc: vi.fn(),
  ellipse: vi.fn(), fill: vi.fn(),
  getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([0, 0, 0, painted ? 255 : 0]) })),
  globalCompositeOperation: "source-over", fillStyle: "#fff",
});

function pointer(canvas: HTMLElement, type: string, x: number, y: number, pointerId = 1) {
  const event = new Event(type, { bubbles: true });
  Object.defineProperties(event, {
    pointerId: { value: pointerId }, clientX: { value: x }, clientY: { value: y },
  });
  fireEvent(canvas, event);
}

describe("Bundle promotional teaser", () => {
  it("selects any original and exposes focused blur controls", () => {
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    expect(screen.getAllByRole("button", { name: /as teaser source/ })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2 as teaser source" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    expect(screen.getByRole("dialog", { name: "Selective Blur Editor" })).toBeInTheDocument();
    expect(screen.getByRole("toolbar", { name: "Mask tools" }).querySelectorAll("button"))
      .toHaveLength(4);
    expect(Array.from(screen.getByRole("toolbar", { name: "Mask tools" }).querySelectorAll("button"))
      .map((button) => button.textContent)).toEqual([
        "Full Blur", "Ellipse Blur", "Blur Brush", "Eraser / Restore",
      ]);
    fireEvent.change(screen.getByLabelText("Brush Size"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Blur Strength"), { target: { value: "35" } });
    expect(screen.getByLabelText("Brush Size")).toHaveValue("70");
    expect(screen.getByLabelText("Blur Strength")).toHaveValue("35");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("uses one mask for Full Blur, Restore, Brush, Ellipse, and Reset without saving", () => {
    const mask = context();
    const composites: string[] = [];
    Object.defineProperty(mask, "globalCompositeOperation", {
      configurable: true, get: () => composites.at(-1) || "source-over",
      set: (value: string) => composites.push(value),
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const original = screen.getByAltText("Shot 1 working preview");
    Object.defineProperty(original, "naturalWidth", { value: 100 });
    Object.defineProperty(original, "naturalHeight", { value: 80 });
    fireEvent.load(original);
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 80, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(
      { left: 0, top: 0, width: 100, height: 80 } as DOMRect,
    );

    fireEvent.click(screen.getByRole("button", { name: "Full Blur" }));
    expect(mask.fillRect).toHaveBeenCalledWith(0, 0, 100, 80);
    expect(screen.getByLabelText("Blur Strength")).toHaveValue("40");
    expect(fetch).not.toHaveBeenCalled();
    const canonical = document.querySelector<HTMLImageElement>('img[src*="full-blur-preview"]')!;
    expect(canonical).toHaveAttribute("src",
      "/api/v1/assets/photoshoots/set-1/bundle-teaser/full-blur-preview?sourceAssetId=1");
    Object.defineProperty(canonical, "complete", { value: true });
    Object.defineProperty(canonical, "naturalWidth", { value: 864 });
    fireEvent.load(canonical);
    expect(mask.drawImage).toHaveBeenCalledWith(canonical, 0, 0, 100, 80);

    fireEvent.click(screen.getByRole("button", { name: "Eraser / Restore" }));
    pointer(canvas, "pointerdown", 20, 20);
    expect(composites).toContain("destination-out");
    fireEvent.click(screen.getByRole("button", { name: "Blur Brush" }));
    pointer(canvas, "pointerdown", 20, 20, 2);
    expect(composites.at(-1)).toBe("source-over");
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    pointer(canvas, "pointerdown", 30, 20, 3); pointer(canvas, "pointerup", 70, 60, 3);
    expect(screen.getByLabelText("Ellipse selection").querySelector("ellipse")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(mask.clearRect).toHaveBeenLastCalledWith(0, 0, 100, 80);
    expect(screen.getByLabelText("Ellipse selection").querySelector("ellipse")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    expect(document.querySelector('img[src*="full-blur-preview"]')).not.toBeInTheDocument();
  });

  it("selects Ellipse Blur with the existing active treatment and hides only Brush Size", () => {
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const brush = screen.getByRole("button", { name: "Blur Brush" });
    const ellipse = screen.getByRole("button", { name: "Ellipse Blur" });
    expect(brush).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(ellipse);
    expect(ellipse).toHaveAttribute("aria-pressed", "true");
    expect(brush).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByLabelText("Brush Size")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Blur Strength")).toBeInTheDocument();
    expect(styles).toMatch(/\.bundle-teaser-editor__tools button\[aria-pressed="true"\][^{]*\{[^}]*border-color:var\(--color-accent\)[^}]*background:var\(--color-accent-surface\)/);
  });

  it("creates scaled horizontal, vertical, circular, and multiple editable ellipses", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 400, writable: true });
    Object.defineProperty(canvas, "height", { value: 200, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 10, top: 20, width: 200, height: 100 } as DOMRect);

    pointer(canvas, "pointerdown", 20, 30);
    pointer(canvas, "pointermove", 110, 55);
    const selection = screen.getByLabelText("Ellipse selection");
    expect(selection.querySelector("ellipse")).toHaveAttribute("rx", "90");
    expect(selection.querySelector("ellipse")).toHaveAttribute("ry", "25");
    pointer(canvas, "pointerup", 110, 55);
    expect(selection.querySelectorAll("rect")).toHaveLength(8);

    pointer(canvas, "pointerdown", 150, 25, 2);
    pointer(canvas, "pointerup", 175, 95, 2);
    pointer(canvas, "pointerdown", 120, 40, 3);
    pointer(canvas, "pointerup", 160, 80, 3);
    expect(selection.querySelectorAll("g")).toHaveLength(3);
    expect(selection.querySelectorAll("ellipse")[2]).toHaveAttribute("rx", "40");
    expect(selection.querySelectorAll("ellipse")[2]).toHaveAttribute("ry", "40");
  });

  it("selects, moves, and clamps independently editable ellipses", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    pointer(canvas, "pointerdown", 20, 20); pointer(canvas, "pointerup", 80, 60);
    pointer(canvas, "pointerdown", 5, 5, 2); pointer(canvas, "pointerup", 15, 15, 2);
    const selection = screen.getByLabelText("Ellipse selection");
    expect(selection.querySelectorAll("g")).toHaveLength(2);
    pointer(canvas, "pointerdown", 50, 40, 3); pointer(canvas, "pointerup", 200, 200, 3);
    const first = selection.querySelector('g[data-ellipse-id="1"]')!;
    expect(first).toHaveClass("is-active");
    expect(first.querySelector("ellipse")).toHaveAttribute("cx", "70");
    expect(first.querySelector("ellipse")).toHaveAttribute("cy", "80");
    pointer(canvas, "pointerdown", 10, 10, 4); pointer(canvas, "pointerup", 10, 10, 4);
    expect(selection.querySelector('g[data-ellipse-id="2"]')).toHaveClass("is-active");
  });

  it("resizes from side and corner handles and clamps resizing to image bounds", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    pointer(canvas, "pointerdown", 20, 20); pointer(canvas, "pointerup", 70, 60);
    pointer(canvas, "pointerdown", 20, 40, 2); pointer(canvas, "pointerup", -30, 40, 2);
    let shape = screen.getByLabelText("Ellipse selection").querySelector("ellipse")!;
    expect(shape).toHaveAttribute("cx", "35");
    expect(shape).toHaveAttribute("rx", "35");
    pointer(canvas, "pointerdown", 70, 20, 3); pointer(canvas, "pointerup", 150, -20, 3);
    shape = screen.getByLabelText("Ellipse selection").querySelector("ellipse")!;
    expect(shape).toHaveAttribute("cx", "50");
    expect(shape).toHaveAttribute("cy", "30");
    expect(shape).toHaveAttribute("rx", "50");
    expect(shape).toHaveAttribute("ry", "30");
  });

  it("combines brush and ellipse pixels, erases ellipse areas, and Reset clears both and the preview", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    pointer(canvas, "pointerdown", 10, 10);
    expect(mask.arc).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    pointer(canvas, "pointerdown", 20, 20, 2); pointer(canvas, "pointerup", 80, 60, 2);
    expect(screen.getByLabelText("Ellipse selection").querySelectorAll("g")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Eraser / Restore" }));
    expect(mask.ellipse).toHaveBeenCalled();
    expect(screen.queryByLabelText("Ellipse selection")).not.toBeInTheDocument();
    pointer(canvas, "pointerdown", 40, 40, 3);
    expect(mask.globalCompositeOperation).toBe("destination-out");
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    pointer(canvas, "pointerdown", 10, 10, 4); pointer(canvas, "pointermove", 50, 50, 4);
    expect(screen.getByLabelText("Ellipse selection").querySelector("g")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByLabelText("Ellipse selection").querySelector("g")).not.toBeInTheDocument();
    expect(mask.clearRect).toHaveBeenLastCalledWith(0, 0, 100, 100);
  });

  it("renders a real composited preview and updates its browser blur filter with strength", () => {
    const filters: string[] = [];
    const mask = context();
    Object.defineProperty(mask, "filter", { configurable: true,
      get: () => filters.at(-1) || "none", set: (value: string) => filters.push(value) });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const original = screen.getByAltText("Shot 1 working preview");
    Object.defineProperty(original, "naturalWidth", { value: 200 });
    Object.defineProperty(original, "naturalHeight", { value: 100 });
    fireEvent.load(original);
    expect(screen.getByLabelText("Live selective blur preview")).toBeInTheDocument();
    expect(styles).toMatch(/\.bundle-teaser-editor__mask-input\s*\{[^}]*opacity:0/);
    expect(filters).toContain("blur(24px)");
    fireEvent.change(screen.getByLabelText("Blur Strength"), { target: { value: "45" } });
    expect(filters).toContain("blur(45px)");
  });

  it("Cancel discards current geometry without calling persistence", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    pointer(canvas, "pointerdown", 10, 10); pointer(canvas, "pointerup", 80, 80);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("recognizes ellipse pixels and submits the combined raster mask through the existing API", async () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,ZWxsaXBzZQ==");
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ ...state, status: "READY", sourceAssetId: 1 }) } as Response);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 120, writable: true });
    Object.defineProperty(canvas, "height", { value: 80, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 120, height: 80 } as DOMRect);
    pointer(canvas, "pointerdown", 10, 10); pointer(canvas, "pointerup", 90, 60);
    fireEvent.click(screen.getByRole("button", { name: "Save Teaser" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const request = fetch.mock.calls[0]![1]!;
    expect(JSON.parse(String(request.body))).toEqual(expect.objectContaining({
      maskData: "data:image/png;base64,ZWxsaXBzZQ==", maskWidth: 120, maskHeight: 80,
    }));
  });

  it("loads an existing raster mask and permits an additional ellipse", () => {
    const mask = context();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(mask as unknown as CanvasRenderingContext2D);
    class MaskImage {
      onload: null | (() => void) = null;
      set src(_value: string) { this.onload?.(); }
    }
    vi.stubGlobal("Image", MaskImage);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={{ ...state, sourceAssetId: 1, teaserAssetId: 9, maskUrl: "/mask" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Teaser" }));
    const original = screen.getByAltText("Shot 1 working preview");
    Object.defineProperty(original, "naturalWidth", { value: 200 });
    Object.defineProperty(original, "naturalHeight", { value: 100 });
    fireEvent.load(original);
    expect(mask.drawImage).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ellipse Blur" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 200, height: 100 } as DOMRect);
    pointer(canvas, "pointerdown", 20, 20); pointer(canvas, "pointerup", 80, 60);
    expect(mask.ellipse).toHaveBeenCalledWith(50, 40, 30, 20, 0, 0, Math.PI * 2);
  });

  it("paints, erases, resets and saves a normalized mask", async () => {
    const onChanged = vi.fn();
    const context = { clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([255, 255, 255, 255]) })),
      globalCompositeOperation: "source-over", fillStyle: "#fff" };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,bWFzaw==");
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({
      ...state, status: "READY", statusLabel: "Promotional Teaser Ready", sourceAssetId: 1,
      teaserAssetId: 100, maskWidth: 1, maskHeight: 1, previewUrl: "/preview",
    }) } as Response);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 100, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100 } as DOMRect);
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 });
    expect(context.fill).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Eraser / Restore" }));
    fireEvent.pointerDown(canvas, { pointerId: 2, clientX: 20, clientY: 20 });
    expect(context.globalCompositeOperation).toBe("destination-out");
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(context.clearRect).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save Teaser" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/bundle-teaser"), expect.objectContaining({ method: "PUT" })));
    expect(await screen.findByAltText("Promotional teaser preview")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "READY", teaserAssetId: 100 }));
  });

  it("blocks an empty blur mask with clear operator guidance", async () => {
    const context = { clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([0, 0, 0, 0]) })),
      globalCompositeOperation: "source-over", fillStyle: "#fff" };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 1, writable: true });
    Object.defineProperty(canvas, "height", { value: 1, writable: true });
    fireEvent.click(screen.getByRole("button", { name: "Save Teaser" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Paint at least one area to blur before saving.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("maps scaled edge pointer coordinates into mask pixels", () => {
    const context = { clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([0, 0, 0, 255]) })),
      globalCompositeOperation: "source-over", fillStyle: "#fff" };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
    render(<BundlePromotionalTeaser deliverableId="set-1" initial={state} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Teaser" }));
    const canvas = screen.getByLabelText("Selective blur mask");
    Object.defineProperty(canvas, "width", { value: 200, writable: true });
    Object.defineProperty(canvas, "height", { value: 100, writable: true });
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 10, top: 20, width: 100, height: 50 } as DOMRect);
    const pointer = new Event("pointerdown", { bubbles: true });
    Object.defineProperties(pointer, {
      pointerId: { value: 1 }, clientX: { value: 109 }, clientY: { value: 69 },
    });
    fireEvent(canvas, pointer);
    expect(context.arc).toHaveBeenCalledWith(198, 98, 20, 0, Math.PI * 2);
  });
});
