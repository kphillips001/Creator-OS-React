import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("application bootstrap background", () => {
  it("paints the canonical dark background before React and CSS load", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
    expect(html).toContain('<meta name="theme-color" content="#0c0e11" />');
    expect(html).toContain("html, body, #root { min-height: 100%; background: #0c0e11; }");
    expect(html.indexOf("background: #0c0e11")).toBeLessThan(html.indexOf('/src/main.tsx'));
  });
});
