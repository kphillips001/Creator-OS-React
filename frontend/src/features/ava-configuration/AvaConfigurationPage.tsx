import { useState } from "react";
import { PageHeader } from "../../shared/ui/PageHeader";
import { CreatorPersonalityPage } from "../creator-personality/CreatorPersonalityPage";
import { SocialCreativeDirectionPage } from "../social-creative-direction/SocialCreativeDirectionPage";
import { CreatorLifestylePage } from "../creator-lifestyle/CreatorLifestylePage";
import { CreatorWorldModelPage } from "../creator-world-model/CreatorWorldModelPage";
import "./ava-configuration.css";

const tabs = [
  ["personality", "Identity & Personality", "Who Ava is, how she communicates, and how she naturally relates to people.", "Identity, biography, voice, conversation and relationship style, intimacy, boundaries, and authored response behavior."],
  ["creative", "Creative Direction", "How Ava's public visual content should look and what it should avoid.", "Wardrobe, visual style, seasonal creative guidance, public presentation, and things to avoid."],
  ["lifestyle", "Lifestyle", "Ava's everyday life, interests, activities, work, and personal routines.", "Career, activities, hobbies, weekend escapes, outdoor lifestyle, small-town roots, and personal lifestyle facts."],
  ["world", "World & Continuity", "The places, environments, seasons, privacy boundaries, and continuity of Ava's world.", "Internal home base, public location, environments, seasons, holidays, travel, and privacy-safe geography."],
] as const;
type TabId = typeof tabs[number][0];

export function AvaConfigurationPage() {
  const [selected, setSelected] = useState<TabId>("personality");
  const active = tabs.find(([id]) => id === selected) ?? tabs[0];
  return <main className="ava-configuration-page">
    <PageHeader title="Ava Configuration" description="Manage Ava's identity, creative direction, lifestyle, and world." />
    <nav aria-label="Ava configuration sections" className="ava-configuration-tabs" role="tablist">
      {tabs.map(([id, label]) => <button aria-selected={selected === id} key={id} onClick={() => setSelected(id)} role="tab" type="button">{label}</button>)}
    </nav>
    <section className="ava-configuration-authority">
      <span>Canonical authority</span><h2>{active[1]}</h2><p>{active[2]}</p><small>{active[3]}</small>
    </section>
    <section aria-label={`${active[1]} editor`} className="ava-configuration-editor" role="tabpanel">
      {selected === "personality" && <CreatorPersonalityPage embedded />}
      {selected === "creative" && <SocialCreativeDirectionPage embedded />}
      {selected === "lifestyle" && <CreatorLifestylePage embedded />}
      {selected === "world" && <CreatorWorldModelPage embedded />}
    </section>
  </main>;
}
