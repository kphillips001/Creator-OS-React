import type { ContentStudioContext } from "../types/contentStudioContext";

type ActiveReferenceSectionProps = {
  context: ContentStudioContext | null;
  error: string;
  loading: boolean;
};

export function ActiveReferenceSection({ context, error, loading }: ActiveReferenceSectionProps) {
  if (loading || (!error && context?.status === "ready")) return null;

  if (error) {
    return <p className="active-reference__message active-reference__message--error" role="alert">{error}</p>;
  }
  if (context?.status === "profile_missing") {
    return (
      <p className="active-reference__message active-reference__message--warning">
        Creator Profile required before selecting a Reference Image.
      </p>
    );
  }
  if (context?.status === "reference_missing") {
    return (
      <p className="active-reference__message active-reference__message--info">
        No active Reference Image selected for this Creator Profile.
      </p>
    );
  }
  return null;
}
