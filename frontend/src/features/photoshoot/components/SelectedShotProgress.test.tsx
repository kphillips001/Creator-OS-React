import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectedShotProgress } from "./SelectedShotProgress";

describe("SelectedShotProgress", () => {
  it("shows the failed stage and exposes retry", () => {
    const retry = vi.fn();
    render(<SelectedShotProgress activeStage={2} error="Canonical planning failed." onRetry={retry} providerLabel="Seedream 5.0 Pro" />);
    expect(screen.getByRole("status")).toHaveTextContent("Canonical planning failed.");
    expect(screen.getAllByText("Canonical planning failed.")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("offers local finalization recovery instead of ordinary generation retry", () => {
    const retry = vi.fn();
    const finalize = vi.fn();
    render(<SelectedShotProgress activeStage={4} error="" finalizationRequired onRetry={retry} onRetryFinalization={finalize} providerLabel="Seedream 5.0 Pro" />);
    expect(screen.getAllByText("Image generated — finalization required")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Finalization" }));
    expect(finalize).toHaveBeenCalledOnce();
    expect(retry).not.toHaveBeenCalled();
  });

  it("offers preparation recovery without competing retry actions", () => {
    const retry = vi.fn();
    const prepare = vi.fn();
    render(<SelectedShotProgress activeStage={3} error="" preparationRecoveryRequired onRetry={retry} onRetryPreparation={prepare} providerLabel="Seedream 5.0 Pro" />);
    expect(screen.getAllByText("Generation preparation needs recovery")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry Finalization" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Preparation" }));
    expect(prepare).toHaveBeenCalledOnce();
    expect(retry).not.toHaveBeenCalled();
  });
});
