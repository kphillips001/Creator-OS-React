import { describe, expect, it } from "vitest";

import { generationLibraryMediaUrl } from "./generationLibraryMedia";

describe("generationLibraryMediaUrl", () => {
  it("changes media identity when an approved asset version changes without changing its record ID", () => {
    const version1 = generationLibraryMediaUrl({ image_id: "image-421", generation_metadata: { asset_version: 1 } });
    const version2 = generationLibraryMediaUrl({ image_id: "image-421", generation_metadata: { asset_version: 2 } });

    expect(version1).toBe("/api/generation-library/media/image-421?v=1");
    expect(version2).toBe("/api/generation-library/media/image-421?v=2");
    expect(version2).not.toBe(version1);
  });
});
