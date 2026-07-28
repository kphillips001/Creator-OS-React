import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import { StoryStudioPage } from "./StoryStudioPage";

describe("StoryStudioPage", () => {
  it("appears in the requested Content Creation order", () => {
    const content = navigationGroups.find((group) => group.label === "Content Creation");
    expect(content?.items.map((item) => item.label)).toEqual([
      "Generation Library", "Available Inventory", "Photoshoot Gallery", "Content Studio",
      "Edit Studio", "Photoshoot Studio", "Story Studio", "Video Studio",
      "Reference Library", "Asset Library",
    ]);
    expect(content?.items.find((item) => item.label === "Story Studio")?.path).toBe("/content/story");
  });

  it("renders the Coming Soon placeholder copy", () => {
    render(<StoryStudioPage />);
    expect(screen.getByRole("heading", { name: "Story Studio" })).toBeInTheDocument();
    expect(screen.getAllByText("Coming Soon")).toHaveLength(2);
    expect(screen.getByText("Story Studio is currently under development.")).toBeInTheDocument();
    expect(screen.getByText("Soon you'll be able to organize photos, videos, captions, and scenes into complete story sequences for publishing.")).toBeInTheDocument();
  });
});
