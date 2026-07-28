import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { creatorWorldModelApi } from "../../infrastructure/api/creatorWorldModelApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CreatorWorldModelDocument,
  CreatorWorldModelUpdate,
} from "./types";
import "./creator-world-model.css";

const fields: {
  key: keyof CreatorWorldModelUpdate;
  title: string;
  rows: number;
}[] = [
  { key: "internal_home_base", title: "Internal Home Base", rows: 8 },
  { key: "public_location_description", title: "Public Location Description", rows: 15 },
  { key: "home_and_indoor_environments", title: "Home and Indoor Environments", rows: 25 },
  { key: "coastal_environments", title: "Coastal Environments", rows: 21 },
  { key: "mountains_lakes_and_small_town_escapes", title: "Mountains, Lakes, and Small-Town Escapes", rows: 23 },
  { key: "climate_and_seasonal_behavior", title: "Climate and Seasonal Behavior", rows: 15 },
  { key: "seasonal_activities", title: "Seasonal Activities", rows: 45 },
  { key: "holiday_rhythm", title: "Holiday Rhythm", rows: 18 },
  { key: "travel_and_variety_guidance", title: "Travel and Variety Guidance", rows: 23 },
];

function editable(
  document: CreatorWorldModelDocument,
): CreatorWorldModelUpdate {
  return {
    internal_home_base: document.internal_home_base,
    public_location_description: document.public_location_description,
    home_and_indoor_environments: document.home_and_indoor_environments,
    coastal_environments: document.coastal_environments,
    mountains_lakes_and_small_town_escapes:
      document.mountains_lakes_and_small_town_escapes,
    climate_and_seasonal_behavior: document.climate_and_seasonal_behavior,
    seasonal_activities: document.seasonal_activities,
    holiday_rhythm: document.holiday_rhythm,
    travel_and_variety_guidance: document.travel_and_variety_guidance,
  };
}

export function CreatorWorldModelPage() {
  const [document, setDocument] =
    useState<CreatorWorldModelDocument | null>(null);
  const [draft, setDraft] = useState<CreatorWorldModelUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const loaded = await creatorWorldModelApi.get();
      setDocument(loaded);
      setDraft(editable(loaded));
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to load World Model.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft || saving) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const saved = await creatorWorldModelApi.update(draft);
      setDocument(saved);
      setDraft(editable(saved));
      setMessage("World Model saved.");
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to save World Model.");
    } finally {
      setSaving(false);
    }
  };

  const dirty = Boolean(
    document && draft &&
    JSON.stringify(editable(document)) !== JSON.stringify(draft)
  );

  return <main className="world-model-page">
    <PageHeader
      title="World Model"
      description="Maintain the canonical description of Ava’s believable world."
    />

    <aside className="world-model-note">
      <AlertCircle size={18} />
      <span>This document defines Ava’s indoor and outdoor world, location privacy, travel range, and seasonal continuity.<br /><br />
        It is separate from Personality, Lifestyle, Social Creative Direction, Visual Identity, and Prompt Generation.</span>
    </aside>

    {loading && <div className="world-model-state">Loading World Model…</div>}
    {error && <div className="world-model-alert world-model-alert--error" role="alert">{error}</div>}
    {message && <div className="world-model-alert world-model-alert--success" role="status"><CheckCircle2 size={16} />{message}</div>}

    {!loading && !draft && <button className="world-model-retry" onClick={() => void load()} type="button">
      <RefreshCw size={16} />Retry
    </button>}

    {draft && document && <form className="world-model-document" onSubmit={save}>
      <header className="world-model-document__header">
        <div><span>Creator document</span><strong>Environments and Seasonal Context</strong></div>
        <small>Creator Profile #{document.creator_profile_id}</small>
      </header>

      {fields.map((field, index) => <section className="world-model-section" key={field.key}>
        <label htmlFor={`world-model-${field.key}`}>
          <span>Section {index + 1}</span>
          <strong>{field.title}</strong>
        </label>
        <textarea
          id={`world-model-${field.key}`}
          rows={field.rows}
          value={draft[field.key]}
          onChange={(event) => setDraft((current) => current
            ? { ...current, [field.key]: event.target.value }
            : current)}
        />
      </section>)}

      <footer className="world-model-actions">
        <span>{dirty
          ? "Unsaved changes"
          : document.updated_at
            ? `Last saved ${new Date(document.updated_at).toLocaleString()}`
            : "Default document—not saved yet"}</span>
        <button disabled={!dirty || saving} type="submit">
          <Save size={16} />{saving ? "Saving…" : "Save Document"}
        </button>
      </footer>
    </form>}
  </main>;
}
