import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectedShotProgress } from "./SelectedShotProgress";

describe("SelectedShotProgress", () => {
  it("shows the failed stage and exposes retry", () => {
    const retry = vi.fn();
    render(<SelectedShotProgress activeStage={2} error="Canonical planning failed." onRetry={retry} providerLabel="Seedream 5.0 Pro" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Canonical planning failed.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
