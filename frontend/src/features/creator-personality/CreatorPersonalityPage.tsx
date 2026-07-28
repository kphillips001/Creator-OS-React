import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { creatorPersonalityApi } from "../../infrastructure/api/creatorPersonalityApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CreatorPersonality,
  CreatorPersonalityUpdate,
} from "./types";
import "./creator-personality.css";

type TextField = {
  key: keyof CreatorPersonalityUpdate;
  label: string;
  rows?: number;
};

type SectionDefinition = {
  title: string;
  description: string;
  fields: TextField[];
};

const sections: SectionDefinition[] = [
  {
    title: "Personality",
    description: "Core character, personal history, and defining traits.",
    fields: [
      { key: "archetype", label: "Archetype", rows: 3 },
      { key: "personality_description", label: "Personality Description", rows: 7 },
      { key: "backstory", label: "Backstory", rows: 7 },
    ],
  },
  {
    title: "Lifestyle",
    description: "Everyday context, interests, routines, and preferences.",
    fields: [
      { key: "lifestyle_context", label: "Lifestyle Context", rows: 6 },
      { key: "lifestyle_vibe", label: "Lifestyle Vibe", rows: 5 },
      { key: "daily_routine", label: "Daily Routine", rows: 5 },
      { key: "hobbies", label: "Hobbies", rows: 5 },
      { key: "likes", label: "Likes", rows: 5 },
      { key: "dislikes", label: "Dislikes", rows: 4 },
    ],
  },
  {
    title: "Relationships",
    description: "Preferred connections, affection, and relationship dynamics.",
    fields: [
      { key: "ideal_user_type", label: "Ideal User Type", rows: 5 },
      { key: "affection_style", label: "Affection Style", rows: 4 },
      { key: "jealousy_style", label: "Jealousy Style", rows: 4 },
      { key: "availability_style", label: "Availability Style", rows: 4 },
    ],
  },
  {
    title: "Conversation Style",
    description: "Voice, pacing, flirtation, and conversational behavior.",
    fields: [
      { key: "tone_style", label: "Tone Style", rows: 4 },
      { key: "flirt_style", label: "Flirt Style", rows: 4 },
      { key: "response_style", label: "Response Style", rows: 5 },
      { key: "pacing_style", label: "Pacing Style", rows: 4 },
      { key: "conversation_hooks", label: "Conversation Hooks", rows: 4 },
      { key: "retention_hooks", label: "Retention Hooks", rows: 4 },
    ],
  },
  {
    title: "Attraction & Sexuality",
    description: "Attraction preferences and the creator's authored sexual style.",
    fields: [
      { key: "turn_ons", label: "Turn Ons", rows: 4 },
      { key: "turn_offs", label: "Turn Offs", rows: 4 },
      { key: "sexual_style", label: "Sexual Style", rows: 5 },
      { key: "sexual_likes", label: "Sexual Likes", rows: 5 },
      { key: "sexual_dislikes", label: "Sexual Dislikes", rows: 4 },
      { key: "kinks", label: "Kinks", rows: 5 },
      { key: "fantasy_style", label: "Fantasy Style", rows: 6 },
    ],
  },
  {
    title: "Escalation",
    description: "How chemistry develops and which signals deepen engagement.",
    fields: [
      { key: "escalation_style", label: "Escalation Style", rows: 4 },
      { key: "escalation_triggers", label: "Escalation Triggers", rows: 4 },
      { key: "self_value_style", label: "Self-Value Style", rows: 4 },
    ],
  },
  {
    title: "Boundaries",
    description: "Personal boundaries, sexual boundaries, and hard limits.",
    fields: [
      { key: "boundaries", label: "Boundaries", rows: 5 },
      { key: "sexual_boundaries", label: "Sexual Boundaries", rows: 5 },
      { key: "hard_limits", label: "Hard Limits", rows: 5 },
    ],
  },
  {
    title: "Response Rules",
    description: "The authored rules governing the creator's responses.",
    fields: [
      { key: "response_rules", label: "Response Rules", rows: 10 },
    ],
  },
];

const updateKeys: (keyof CreatorPersonalityUpdate)[] = [
  "persona_name", "age", "gender", "location", "is_active", "archetype",
  "personality_description", "backstory", "lifestyle_context", "lifestyle_vibe",
  "daily_routine", "hobbies", "likes", "dislikes", "ideal_user_type",
  "turn_ons", "turn_offs", "sexual_style", "sexual_likes", "sexual_dislikes",
  "kinks", "fantasy_style", "tone_style", "flirt_style", "tease_intensity",
  "push_pull_style", "mystery_level", "response_style", "pacing_style",
  "question_frequency", "emotional_depth", "affection_style", "jealousy_style",
  "availability_style", "conversation_hooks", "retention_hooks",
  "escalation_style", "escalation_triggers", "self_value_style",
  "persona_intensity", "boundaries", "sexual_boundaries", "hard_limits",
  "response_rules",
];

function editableProfile(profile: CreatorPersonality): CreatorPersonalityUpdate {
  return Object.fromEntries(
    updateKeys.map((key) => [key, profile[key]]),
  ) as CreatorPersonalityUpdate;
}

export function CreatorPersonalityPage() {
  const [profile, setProfile] = useState<CreatorPersonality | null>(null);
  const [draft, setDraft] = useState<CreatorPersonalityUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const loaded = await creatorPersonalityApi.get();
      setProfile(loaded);
      setDraft(editableProfile(loaded));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Creator Personality.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setValue = <Key extends keyof CreatorPersonalityUpdate>(
    key: Key,
    value: CreatorPersonalityUpdate[Key],
  ) => setDraft((current) => current ? { ...current, [key]: value } : current);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft || saving) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await creatorPersonalityApi.update(draft);
      setProfile(updated);
      setDraft(editableProfile(updated));
      setMessage("Creator personality saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save Creator Personality.");
    } finally {
      setSaving(false);
    }
  };

  const dirty = Boolean(
    profile && draft &&
    JSON.stringify(editableProfile(profile)) !== JSON.stringify(draft)
  );

  return <main className="creator-personality-page">
    <PageHeader
      title="Personality"
      description="Review and edit the canonical creator personality stored for the active creator account."
    />

    <aside className="creator-personality-note">
      <AlertCircle size={18} />
      <span><strong>Canonical creator personality.</strong> This defines who the creator is.<br />
        Visual identity, creative direction, and generation behavior are managed separately.</span>
    </aside>

    {loading && <div className="creator-personality-state">Loading canonical personality…</div>}
    {error && <div className="creator-personality-alert creator-personality-alert--error" role="alert">{error}</div>}
    {message && <div className="creator-personality-alert creator-personality-alert--success" role="status"><CheckCircle2 size={16} />{message}</div>}

    {!loading && !draft && <button className="creator-personality-retry" onClick={() => void load()} type="button">
      <RefreshCw size={16} />Retry
    </button>}

    {draft && profile && <form onSubmit={save}>
      <section className="personality-section">
        <header><div><h2>Identity</h2><p>Account-scoped creator identity and profile status.</p></div>
          <span>Profile #{profile.id}</span></header>
        <div className="personality-grid personality-grid--identity">
          <Field label="Persona Name"><input required value={draft.persona_name} onChange={(event) => setValue("persona_name", event.target.value)} /></Field>
          <Field label="Age"><input min={18} required type="number" value={draft.age} onChange={(event) => setValue("age", Number(event.target.value))} /></Field>
          <Field label="Gender"><input required value={draft.gender} onChange={(event) => setValue("gender", event.target.value)} /></Field>
          <Field label="Location"><input required value={draft.location} onChange={(event) => setValue("location", event.target.value)} /></Field>
          <Field label="Profile Status"><label className="personality-toggle"><input checked={draft.is_active} onChange={(event) => setValue("is_active", event.target.checked)} type="checkbox" /><span>{draft.is_active ? "Active" : "Inactive"}</span></label></Field>
        </div>
      </section>

      {sections.map((section) => <section className="personality-section" key={section.title}>
        <header><div><h2>{section.title}</h2><p>{section.description}</p></div></header>
        <div className="personality-grid">
          {section.fields.map((field) => <Field label={field.label} key={field.key}>
            <textarea
              rows={field.rows ?? 4}
              value={String(draft[field.key])}
              onChange={(event) => setValue(field.key, event.target.value as never)}
            />
          </Field>)}
          {section.title === "Conversation Style" && <>
            <Field label="Tease Intensity"><input min={0} max={10} type="number" value={draft.tease_intensity} onChange={(event) => setValue("tease_intensity", Number(event.target.value))} /></Field>
            <Field label="Push/Pull Style"><input value={draft.push_pull_style} onChange={(event) => setValue("push_pull_style", event.target.value)} /></Field>
            <Field label="Mystery Level"><input value={draft.mystery_level} onChange={(event) => setValue("mystery_level", event.target.value)} /></Field>
            <Field label="Question Frequency"><input value={draft.question_frequency} onChange={(event) => setValue("question_frequency", event.target.value)} /></Field>
            <Field label="Emotional Depth"><input value={draft.emotional_depth} onChange={(event) => setValue("emotional_depth", event.target.value)} /></Field>
          </>}
          {section.title === "Escalation" && <Field label="Persona Intensity"><input min={0} max={10} type="number" value={draft.persona_intensity} onChange={(event) => setValue("persona_intensity", Number(event.target.value))} /></Field>}
        </div>
      </section>)}

      <footer className="creator-personality-actions">
        <span>{dirty ? "Unsaved changes" : `Last saved ${new Date(profile.updated_at).toLocaleString()}`}</span>
        <button disabled={!dirty || saving} type="submit"><Save size={16} />{saving ? "Saving…" : "Save Personality"}</button>
      </footer>
    </form>}
  </main>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="personality-field"><span>{label}</span>{children}</label>;
}
