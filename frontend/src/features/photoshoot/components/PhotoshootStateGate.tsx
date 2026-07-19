import { useNavigate } from "react-router-dom";

import type { PhotoshootContext } from "../types";

export function PhotoshootStateGate({ context, loading, error, children }: {
  context: PhotoshootContext | null;
  loading: boolean;
  error: string;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  if (loading) return <div className="photoshoot-state" role="status">Loading Photoshoot Studio…</div>;
  if (error) return <div className="photoshoot-state photoshoot-state--error" role="alert">{error}</div>;
  if (context?.status === "profile_missing") return <div className="photoshoot-state" role="alert">Creator Profile required before using Photoshoot Studio.</div>;
  if (context?.status === "photoshoot_missing") return <div className="photoshoot-state"><p>Choose an image in Generation Library and click 📸 Photoshoot to begin.</p><button className="photoshoot-button photoshoot-button--secondary" onClick={() => navigate("/library/generations")} type="button">Return to Generation Library</button></div>;
  return <>{children}</>;
}
