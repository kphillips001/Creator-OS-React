import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhotoshootCurationReview } from "../types";
import { PhotoshootCurationPanel } from "./PhotoshootCurationPanel";

const review: PhotoshootCurationReview = {
  session_id: "session-1", session_title: "Editorial", photoshoot_decision: "PENDING", confirmed: false, curation: {},
  seed_image: { image_id: "seed", asset_id: 1, shot_number: 0, title: "Opening Portrait", description: "Hidden prompt", image_url: "/seed.png", keep: false, is_seed: true },
  shots: [
    { image_id: "two", asset_id: 2, shot_number: 1, title: "Window Turn", description: "Hidden description", image_url: "/two.png", keep: true, is_seed: false },
    { image_id: "three", asset_id: 3, shot_number: 2, title: "Seated Pose", description: "Another hidden description", image_url: "/three.png", keep: true, is_seed: false },
  ],
};

describe("PhotoshootCurationPanel", () => {
  it("renders one chronological horizontal review strip without technical copy", () => {
    render(<PhotoshootCurationPanel busy={false} review={review} onConfirm={vi.fn()} />);
    const strip = screen.getByRole("list", { name: "Photoshoot sequence" });
    expect(strip).toHaveClass("photoshoot-curation__filmstrip");
    expect(strip.children).toHaveLength(3);
    expect(strip.children[0]).toHaveTextContent("Seed Image");
    expect(strip.children[1]).toHaveTextContent("Shot 2");
    expect(strip.children[2]).toHaveTextContent("Shot 3");
    expect(screen.queryByText("Hidden prompt")).not.toBeInTheDocument();
    expect(screen.queryByText("Hidden description")).not.toBeInTheDocument();
  });

  it("transitions No to a separate standalone-image salvage screen", () => {
    render(<PhotoshootCurationPanel busy={false} review={review} onConfirm={vi.fn()} />);
    fireEvent.click(screen.getByRole("radio", { name: "No" }));
    expect(screen.getByRole("heading", { name: "Keep any individual images?" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Photoshoot sequence" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    expect(screen.getAllByRole("checkbox").every((input) => !(input as HTMLInputElement).checked)).toBe(true);
  });

  it("defaults approved shots selected, locks the seed, updates counts, and submits selected IDs only", async () => {
    const onConfirm = vi.fn().mockResolvedValue({
      session_id: "session-1", status: "archived", already_confirmed: false,
      photoshoot_decision: "APPROVED", photoshoot_decided_at: "now",
      selected_image_ids: ["three"], photoshoot_created: true,
      photoshoot_deliverable_id: "set-1", image_asset_generation_ids: [],
    });
    render(<PhotoshootCurationPanel busy={false} review={review} onConfirm={onConfirm} />);

    const seed = screen.getByRole("checkbox", { name: "Include Seed Image in Photoset" });
    const first = screen.getByRole("checkbox", { name: "Include Window Turn in Photoset" });
    const second = screen.getByRole("checkbox", { name: "Include Seated Pose in Photoset" });
    expect(seed).toBeChecked();
    expect(seed).toBeDisabled();
    expect(first).toBeChecked();
    expect(second).toBeChecked();
    expect(screen.getByLabelText("Photoset membership counts")).toHaveTextContent("3Approved3Selected0Remaining Available Inventory");

    fireEvent.click(first);
    expect(screen.getByLabelText("Photoset membership counts")).toHaveTextContent("3Approved2Selected1Remaining Available Inventory");
    fireEvent.click(screen.getByRole("radio", { name: "Yes" }));
    fireEvent.click(first);
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith(["three"], "APPROVED"));
  });
});
