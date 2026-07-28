import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlaceholderPage } from "./PlaceholderPage";

describe("Publishing roadmap placeholder", () => {
  it("explains the historical workspace without implying publishing starts here", () => {
    render(
      <PlaceholderPage
        title="Publishing"
        description="Publication history and distribution across every platform."
      />,
    );

    expect(screen.getByRole("heading", { name: "Publishing" })).toBeInTheDocument();
    expect(screen.getByText("Publication history and distribution across every platform.")).toBeInTheDocument();
    expect(screen.getByText(/centralized history of every piece of content/i)).toBeInTheDocument();
    expect(screen.getByText("Fanvue publication history")).toBeInTheDocument();
    expect(screen.getByText("Links back to the originating Generation or Commercial Offering")).toBeInTheDocument();
    expect(screen.getByText(/intentionally deferred until after Version 1 launch/i)).toBeInTheDocument();
    expect(screen.queryByText(/Publishing is coming soon/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("preserves the standard placeholder for other workspaces", () => {
    render(<PlaceholderPage title="Story Studio" description="Coming Soon" />);
    expect(screen.getByText("Story Studio is coming soon")).toBeInTheDocument();
  });
});
