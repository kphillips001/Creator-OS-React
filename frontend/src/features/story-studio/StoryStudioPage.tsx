import { BookOpen, Sparkles } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import "./story-studio.css";

export function StoryStudioPage() {
  return (
    <section>
      <PageHeader title="Story Studio" description="Coming Soon" />
      <section className="placeholder-panel" aria-labelledby="story-studio-status">
        <div className="placeholder-panel__icon" aria-hidden="true"><BookOpen size={22} strokeWidth={1.7} /></div>
        <div className="placeholder-panel__content story-studio__content">
          <span className="status-badge"><span className="status-badge__dot" />Coming Soon</span>
          <h2 id="story-studio-status">Story Studio is currently under development.</h2>
          <p>Soon you'll be able to organize photos, videos, captions, and scenes into complete story sequences for publishing.</p>
        </div>
        <div className="placeholder-panel__marker" aria-hidden="true"><Sparkles size={18} /></div>
      </section>
    </section>
  );
}
