import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import { StoryStudioPage } from "./StoryStudioPage";

describe("StoryStudioPage", () => {
  it("stays implemented while hidden from normal sidebar navigation", () => {
    expect(navigationGroups.flatMap((group) => group.items).some((item) => item.label === "Story Studio")).toBe(false);
  });

  it("renders the Coming Soon placeholder copy", () => {
    render(<StoryStudioPage />);
    expect(screen.getByRole("heading", { name: "Story Studio" })).toBeInTheDocument();
    expect(screen.getAllByText("Coming Soon")).toHaveLength(2);
    expect(screen.getByText("Story Studio is currently under development.")).toBeInTheDocument();
    expect(screen.getByText("Soon you'll be able to organize photos, videos, captions, and scenes into complete story sequences for publishing.")).toBeInTheDocument();
  });
});
