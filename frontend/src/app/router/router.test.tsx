import { matchRoutes } from "react-router-dom";
import { isValidElement } from "react";
import { describe, expect, it } from "vitest";
import { DeveloperNotesPage } from "../../features/developer-notes/DeveloperNotesPage";
import { PlaceholderPage } from "../../features/placeholder/PlaceholderPage";
import { router } from "./router";
import { RegenerationStudioPage } from "../../features/regeneration-studio/RegenerationStudioPage";
import { RegeneratedContentPage } from "../../features/regenerated-content/RegeneratedContentPage";

describe("application route precedence", () => {
  it("resolves Developer Notes to its implemented page rather than a generated placeholder", () => {
    const matches = matchRoutes(router.routes, "/administration/developer-notes");
    const element = matches?.at(-1)?.route.element;
    expect(isValidElement(element)).toBe(true);
    if (!isValidElement(element)) throw new Error("Developer Notes route has no React element.");
    expect(element?.type).toBe(DeveloperNotesPage);
    expect(element?.type).not.toBe(PlaceholderPage);
  });
});

describe("Regeneration Studio route", () => {
  it("resolves to the implemented workspace", () => {
    const element = matchRoutes(router.routes, "/studio/regeneration")?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(RegenerationStudioPage);
  });
  it("resolves the regenerated archive destination", () => {
    const element = matchRoutes(router.routes, "/system/archive/regenerated")?.at(-1)?.route.element;
    expect(isValidElement(element) && element.type).toBe(RegeneratedContentPage);
  });
});
