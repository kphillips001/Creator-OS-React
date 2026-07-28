import { PageHeader } from "../../shared/ui/PageHeader";
import { PlaceholderPanel } from "../../shared/ui/PlaceholderPanel";
import { Check, History } from "lucide-react";

export type PlaceholderPageDefinition = {
  title: string;
  description: string;
};

export function PlaceholderPage({
  title,
  description,
}: PlaceholderPageDefinition) {
  if (title === "Publishing") {
    return <PublishingRoadmap description={description} />;
  }
  return (
    <>
      <PageHeader title={title} description={description} />
      <PlaceholderPanel featureName={title} />
    </>
  );
}

const futureCapabilities = [
  "Fanvue publication history",
  "Telegram Wall publication history",
  "X publication history",
  "Instagram publication history",
  "Reddit publication history",
  "Threads publication history",
  "Publication timeline",
  "Search and filtering",
  "Publication status",
  "Original captions",
  "Published media preview",
  "Links back to the originating Generation or Commercial Offering",
  "Publication analytics",
  "Performance metrics",
  "Audit history",
] as const;

function PublishingRoadmap({ description }: { description: string }) {
  return (
    <section className="publishing-roadmap">
      <PageHeader title="Publishing" description={description} />
      <p className="publishing-roadmap__introduction">
        This workspace will become the centralized history of every piece of
        content published from Creator_OS.
      </p>
      <p className="publishing-roadmap__introduction">
        Rather than publishing from here, Creator_OS records publications made
        throughout the platform and makes them searchable, reviewable, and
        measurable.
      </p>
      <section
        className="placeholder-panel publishing-roadmap__card"
        aria-labelledby="publishing-roadmap-title"
      >
        <div className="placeholder-panel__icon" aria-hidden="true">
          <History size={22} strokeWidth={1.7} />
        </div>
        <div className="placeholder-panel__content">
          <p className="placeholder-panel__label">Future Publishing Workspace</p>
          <h2 id="publishing-roadmap-title">
            A complete record of external distribution
          </h2>
          <p>This workspace will eventually include:</p>
          <ul className="publishing-roadmap__capabilities">
            {futureCapabilities.map((capability) => (
              <li key={capability}>
                <Check aria-hidden="true" size={16} />
                <span>{capability}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <aside className="publishing-roadmap__note" aria-label="Publishing roadmap note">
        <strong>Publishing is intentionally deferred until after Version 1 launch.</strong>
        <span>
          Current publishing workflows remain available through Generation
          Library and Commerce.
        </span>
      </aside>
    </section>
  );
}
