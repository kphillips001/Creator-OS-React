import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { creatorLifestyleApi } from "../../infrastructure/api/creatorLifestyleApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CreatorLifestyleDocument,
  CreatorLifestyleUpdate,
} from "./types";
import "./creator-lifestyle.css";

const fields: {
  key: keyof CreatorLifestyleUpdate;
  title: string;
  rows: number;
}[] = [
  { key: "career", title: "Career", rows: 6 },
  { key: "lifestyle_overview", title: "Lifestyle Overview", rows: 7 },
  { key: "favorite_activities", title: "Favorite Activities", rows: 15 },
  { key: "weekend_escapes", title: "Weekend Escapes", rows: 7 },
  { key: "small_town_roots", title: "Small-Town Roots", rows: 7 },
  { key: "outdoor_lifestyle", title: "Outdoor Lifestyle", rows: 7 },
  { key: "personal_style", title: "Personal Style", rows: 7 },
];

function editable(document: CreatorLifestyleDocument): CreatorLifestyleUpdate {
  return {
    career: document.career,
    lifestyle_overview: document.lifestyle_overview,
    favorite_activities: document.favorite_activities,
    weekend_escapes: document.weekend_escapes,
    small_town_roots: document.small_town_roots,
    outdoor_lifestyle: document.outdoor_lifestyle,
    personal_style: document.personal_style,
  };
}

export function CreatorLifestylePage() {
  const [document, setDocument] =
    useState<CreatorLifestyleDocument | null>(null);
  const [draft, setDraft] = useState<CreatorLifestyleUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const loaded = await creatorLifestyleApi.get();
      setDocument(loaded);
      setDraft(editable(loaded));
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to load Lifestyle.");
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
      const saved = await creatorLifestyleApi.update(draft);
      setDocument(saved);
      setDraft(editable(saved));
      setMessage("Lifestyle saved.");
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to save Lifestyle.");
    } finally {
      setSaving(false);
    }
  };

  const dirty = Boolean(
    document && draft &&
    JSON.stringify(editable(document)) !== JSON.stringify(draft)
  );

  return <main className="lifestyle-page">
    <PageHeader
      title="Lifestyle"
      description="Maintain the canonical description of how Ava naturally lives."
    />

    <aside className="lifestyle-note">
      <AlertCircle size={18} />
      <span>This document defines how Ava naturally lives.<br /><br />
        It is used to inspire authentic moments from her life.<br /><br />
        It is separate from Personality, Social Creative Direction, World knowledge, and Prompt Generation.</span>
    </aside>

    {loading && <div className="lifestyle-state">Loading Lifestyle…</div>}
    {error && <div className="lifestyle-alert lifestyle-alert--error" role="alert">{error}</div>}
    {message && <div className="lifestyle-alert lifestyle-alert--success" role="status"><CheckCircle2 size={16} />{message}</div>}

    {!loading && !draft && <button className="lifestyle-retry" onClick={() => void load()} type="button">
      <RefreshCw size={16} />Retry
    </button>}

    {draft && document && <form className="lifestyle-document" onSubmit={save}>
      <header className="lifestyle-document__header">
        <div><span>Creator document</span><strong>Everyday Life</strong></div>
        <small>Creator Profile #{document.creator_profile_id}</small>
      </header>

      {fields.map((field, index) => <section className="lifestyle-section" key={field.key}>
        <label htmlFor={`lifestyle-${field.key}`}>
          <span>Section {index + 1}</span>
          <strong>{field.title}</strong>
        </label>
        <textarea
          id={`lifestyle-${field.key}`}
          rows={field.rows}
          value={draft[field.key]}
          onChange={(event) => setDraft((current) => current
            ? { ...current, [field.key]: event.target.value }
            : current)}
        />
      </section>)}

      <footer className="lifestyle-actions">
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
