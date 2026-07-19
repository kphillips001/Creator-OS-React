import { useCallback, useEffect, useState } from "react";

import { getPhotoshootContext } from "../../infrastructure/api/photoshootApi";
import type { PhotoshootContext } from "./types";

export function usePhotoshootContext() {
  const [state, setState] = useState<{ context: PhotoshootContext | null; loading: boolean; error: string }>({
    context: null,
    loading: true,
    error: "",
  });

  const refresh = useCallback((signal?: AbortSignal) => {
    setState((current) => ({ ...current, loading: current.context === null, error: "" }));
    return getPhotoshootContext(signal).then((context) => {
      setState({ context, loading: false, error: "" });
      return context;
    }).catch((reason: unknown) => {
      if ((reason as { name?: string }).name !== "AbortError") setState({ context: null, loading: false, error: reason instanceof Error ? reason.message : "Photoshoot Studio failed to load." });
      throw reason;
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [refresh]);

  return { ...state, refresh };
}
