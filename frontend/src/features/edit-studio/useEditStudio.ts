import { useEffect, useState } from "react";

import { getEditStudioContext } from "../../infrastructure/api/editStudioApi";
import type { EditStudioContext } from "./types";

type EditStudioState = {
  context: EditStudioContext | null;
  loading: boolean;
  error: string;
};

export function useEditStudio(): EditStudioState {
  const [state, setState] = useState<EditStudioState>({
    context: null,
    loading: true,
    error: "",
  });

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const context = await getEditStudioContext(controller.signal);
        setState({ context, loading: false, error: "" });
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setState({
          context: null,
          loading: false,
          error: reason instanceof Error ? reason.message : "Edit Studio failed to load",
        });
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  return state;
}
