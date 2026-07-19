import { useEffect, useState } from "react";

import { getContentStudioContext } from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";

type ContextState = {
  context: ContentStudioContext | null;
  error: string;
  loading: boolean;
};

export function useContentStudioContext(): ContextState {
  const [state, setState] = useState<ContextState>({
    context: null,
    error: "",
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    getContentStudioContext(controller.signal)
      .then((context) => setState({ context, error: "", loading: false }))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setState({
          context: null,
          error: reason instanceof Error ? reason.message : "Content Studio context read failed",
          loading: false,
        });
      });
    return () => controller.abort();
  }, []);

  return state;
}
