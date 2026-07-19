import { useEffect, useState } from "react";

import { getContentStudioConfiguration } from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioConfiguration } from "../types/contentStudioConfiguration";

type ConfigurationState = {
  configuration: ContentStudioConfiguration | null;
  error: string;
  loading: boolean;
};

export function useContentStudioConfiguration(): ConfigurationState {
  const [state, setState] = useState<ConfigurationState>({
    configuration: null,
    error: "",
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    getContentStudioConfiguration(controller.signal)
      .then((configuration) => setState({ configuration, error: "", loading: false }))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setState({
          configuration: null,
          error: reason instanceof Error ? reason.message : "Content Studio configuration read failed",
          loading: false,
        });
      });
    return () => controller.abort();
  }, []);

  return state;
}
