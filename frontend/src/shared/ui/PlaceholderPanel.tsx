import { ArrowUpRight, Layers3 } from "lucide-react";

import "./shared-ui.css";

type PlaceholderPanelProps = {
  featureName: string;
};

export function PlaceholderPanel({ featureName }: PlaceholderPanelProps) {
  return (
    <section className="placeholder-panel" aria-labelledby="feature-status">
      <div className="placeholder-panel__icon" aria-hidden="true">
        <Layers3 size={22} strokeWidth={1.7} />
      </div>
      <div className="placeholder-panel__content">
        <p className="placeholder-panel__label">Creative tools</p>
        <h2 id="feature-status">{featureName} is coming soon</h2>
        <p>
          This space is ready for the next part of your creative process.
        </p>
      </div>
      <div className="placeholder-panel__marker" aria-hidden="true">
        <ArrowUpRight size={18} />
      </div>
    </section>
  );
}
