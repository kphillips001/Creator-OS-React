import { useRef, useState } from "react";

import { createPromptPreview } from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { RecreateRuntimeState } from "../types/recreateRuntime";
import {
  GenerationWorkflowSections,
  type GenerationWorkflowHandle,
} from "./GenerationWorkflowSections";
import { RecreateWithAvaSection } from "./RecreateWithAvaSection";

export function RecreateWithAvaWorkflowSection({
  context,
  creativeMode,
  provider,
}: {
  context: ContentStudioContext;
  creativeMode: string;
  provider: string;
}) {
  const generationRef = useRef<GenerationWorkflowHandle>(null);
  const inFlightRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [activated, setActivated] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [runtime, setRuntime] = useState<RecreateRuntimeState | null>(null);
  const blocked = context.status === "reference_missing" || !creativeMode || !provider;

  const generate = async (source: string, enhanced: string, diagnosticTraceId: string) => {
    if (inFlightRef.current || blocked || pending) return;
    inFlightRef.current = true;
    setActivated(true);
    setPending(true);
    setError("");
    try {
      const promptInput = [
        `[ORIGINAL USER TAGS — mandatory: ${source.trim().replaceAll("\n", ", ")}]`,
        `[ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: ${enhanced.trim().replaceAll("\n", ", ")}]`,
      ].join(" ");
      let preview;
      try {
        preview = await createPromptPreview(
          creativeMode,
          promptInput,
          1,
          undefined,
          "social",
          undefined,
          { origin: "recreate_with_ava", diagnosticTraceId },
        );
      } catch {
        throw new Error("Failed while creating canonical prompt.");
      }
      const result = await generationRef.current?.generateWithResult({
        creativeMode,
        origin: "recreate_with_ava",
        promptBatch: preview.prompts,
        promptCount: 1,
        promptSource: promptInput,
        promptSourceLabel: "Enhanced Tags",
        provider,
        diagnosticTraceId,
      });
      if (!result) {
        throw new Error("Generation submission was blocked because the generation runtime was unavailable.");
      }
      if (result.status !== "completed") throw new Error(result.reason);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Recreate With Ava failed";
      setError(message);
      throw new Error(message);
    } finally {
      inFlightRef.current = false;
      setPending(false);
    }
  };

  return (
    <details
      className="creative-studio recreate-with-ava-accordion"
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary>
        <span>🔄 Recreate With Ava</span>
        <small>Upload an inspiration image and recreate the concept with Ava.</small>
      </summary>
      <section aria-label="Recreate With Ava" className="creative-studio__content recreate-with-ava-accordion__content">
        <RecreateWithAvaSection
          disabled={blocked || pending}
          onGenerate={generate}
          onRuntimeChange={(state) => {
            setRuntime(state);
            setActivated(true);
          }}
          onRuntimeReset={() => {
            setRuntime(null);
            setActivated(false);
            setError("");
            generationRef.current?.reset();
          }}
        />
        <div className={activated
          ? "workflow-live-preview workflow-live-preview--creative"
          : "workflow-controller"}>
          {activated && <h3>Recreate With Ava Status</h3>}
          {pending && <p className="creative-director-tools__status">Creating Images...</p>}
          {error && <p className="generation-live__error" role="alert">{error}</p>}
          {activated && <h3>Recreate With Ava Live Preview</h3>}
          <GenerationWorkflowSections
            context={context}
            disabled={blocked}
            onRunStart={() => setActivated(true)}
            onReconnect={() => {
              setActivated(true);
              setOpen(true);
            }}
            onStartNewGeneration={() => {
              setActivated(false);
              setPending(false);
              setError("");
              setRuntime(null);
            }}
            reconnectOrigins={["recreate_with_ava"]}
            recreateRuntime={runtime}
            onRecreateRuntimeChange={setRuntime}
            request={{
              creativeMode,
              origin: "recreate_with_ava",
              promptBatch: [],
              promptCount: 1,
              promptSource: "",
              promptSourceLabel: "Enhanced Tags",
              provider,
            }}
            ref={generationRef}
            workflow="manual"
          />
        </div>
      </section>
    </details>
  );
}
