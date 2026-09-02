import { Navigate, matchRoutes } from "react-router-dom";
import { isValidElement } from "react";
import { describe, expect, it } from "vitest";
import { DeveloperNotesPage } from "../../features/developer-notes/DeveloperNotesPage";
import { PlaceholderPage } from "../../features/placeholder/PlaceholderPage";
import { router } from "./router";
import { RegenerationStudioPage } from "../../features/regeneration-studio/RegenerationStudioPage";
import { RegeneratedContentPage } from "../../features/regenerated-content/RegeneratedContentPage";
import { XCompetitorIntelligencePage } from "../../features/x-competitor-intelligence/XCompetitorIntelligencePage";
import { AiTrainingPage } from "../../features/ai-training/AiTrainingPage";
import { AiTrainingControlsPage } from "../../features/ai-training-controls/AiTrainingControlsPage";
import { IgCompetitorIntelligencePage } from "../../features/ig-competitor-intelligence/IgCompetitorIntelligencePage";

describe("application route precedence", () => {
  it("resolves Developer Notes to its implemented page rather than a generated placeholder", () => {
    const matches = matchRoutes(
      router.routes,
      "/administration/developer-notes",
    );
    const element = matches?.at(-1)?.route.element;
    expect(isValidElement(element)).toBe(true);
    if (!isValidElement(element))
      throw new Error("Developer Notes route has no React element.");
    expect(element?.type).toBe(DeveloperNotesPage);
    expect(element?.type).not.toBe(PlaceholderPage);
  });
});

describe("X Scraper route", () => {
  it("redirects the retired standalone route to X Competitor Intelligence", () => {
    const element = matchRoutes(router.routes, "/tools/x-scraper")?.at(-1)
      ?.route.element;
    expect(isValidElement(element) && element.type).toBe(Navigate);
    expect(isValidElement(element) && element.props).toMatchObject({
      to: "/tools/x-intelligence",
      replace: true,
    });
  });
});

describe("AI Training route", () => {
  it("resolves the live controls page from the AI group", () => {
    const element = matchRoutes(router.routes, "/agents/ai-training")?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(AiTrainingControlsPage);
  });

  it("resolves directly to the implemented page", () => {
    const element = matchRoutes(router.routes, "/tools/ai-training")?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(AiTrainingPage);
  });
});

describe("X Competitor Intelligence route", () => {
  it("resolves directly to the implemented page", () => {
    const element = matchRoutes(router.routes, "/tools/x-intelligence")?.at(-1)
      ?.route.element;
    expect(isValidElement(element) && element.type).toBe(
      XCompetitorIntelligencePage,
    );
  });
});

describe("IG Competitor Intelligence route", () => {
  it("resolves directly to the implemented page", () => {
    const element = matchRoutes(router.routes, "/tools/ig-intelligence")?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(IgCompetitorIntelligencePage);
  });
});

describe("Regeneration Studio route", () => {
  it("resolves to the implemented workspace", () => {
    const element = matchRoutes(router.routes, "/studio/regeneration")?.at(-1)
      ?.route.element;
    expect(isValidElement(element) && element.type).toBe(
      RegenerationStudioPage,
    );
  });
  it("resolves the regenerated archive destination", () => {
    const element = matchRoutes(
      router.routes,
      "/system/archive/regenerated",
    )?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(
      RegeneratedContentPage,
    );
  });
});

describe("Bundle Studio route", () => {
  it("redirects the retired route to Generation Library", () => {
    const element = matchRoutes(router.routes, "/studio/bundles")?.at(-1)?.route
      .element;
    expect(isValidElement(element)).toBe(true);
    if (!isValidElement(element))
      throw new Error("Retired Bundle Studio route has no redirect.");
    expect(element.type).toBeDefined();
    expect(element.props).toMatchObject({
      to: "/library/generations",
      replace: true,
    });
  });
});
