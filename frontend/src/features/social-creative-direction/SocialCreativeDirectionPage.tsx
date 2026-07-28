import { AlertCircle, CheckCircle2, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { socialCreativeDirectionApi } from "../../infrastructure/api/socialCreativeDirectionApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  SocialCreativeDirectionDocument,
  SocialCreativeDirectionUpdate,
} from "./types";
import "./social-creative-direction.css";

const fields: {
  key: keyof SocialCreativeDirectionUpdate;
  title: string;
  rows: number;
}[] = [
  { key: "purpose", title: "Purpose", rows: 5 },
  { key: "wardrobe", title: "Wardrobe", rows: 15 },
  { key: "visual_style", title: "Visual Style", rows: 13 },
  { key: "seasonal_guidance", title: "Seasonal Guidance", rows: 9 },
  { key: "things_to_avoid", title: "Things To Avoid", rows: 13 },
];

function editable(
  document: SocialCreativeDirectionDocument,
): SocialCreativeDirectionUpdate {
  return {
    purpose: document.purpose,
    wardrobe: document.wardrobe,
    visual_style: document.visual_style,
    seasonal_guidance: document.seasonal_guidance,
    things_to_avoid: document.things_to_avoid,
  };
}

export function SocialCreativeDirectionPage() {
  const [document, setDocument] =
    useState<SocialCreativeDirectionDocument | null>(null);
  const [draft, setDraft] =
    useState<SocialCreativeDirectionUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const loaded = await socialCreativeDirectionApi.get();
      setDocument(loaded);
      setDraft(editable(loaded));
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to load Social Creative Direction.");
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
      const saved = await socialCreativeDirectionApi.update(draft);
      setDocument(saved);
      setDraft(editable(saved));
      setMessage("Social Creative Direction saved.");
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Unable to save Social Creative Direction.");
    } finally {
      setSaving(false);
    }
  };

  const dirty = Boolean(
    document && draft &&
    JSON.stringify(editable(document)) !== JSON.stringify(draft)
  );

  return <main className="social-direction-page">
    <PageHeader
      title="Social Creative Direction"
      description="Maintain the canonical creative vision for Ava's public social content."
    />

    <aside className="social-direction-note">
      <AlertCircle size={18} />
      <span>This document defines how Ava should be visually presented on public social platforms.<br />
        It is separate from Personality, Visual Identity, and Prompt Generation.</span>
    </aside>

    {loading && <div className="social-direction-state">Loading Social Creative Direction…</div>}
    {error && <div className="social-direction-alert social-direction-alert--error" role="alert">{error}</div>}
    {message && <div className="social-direction-alert social-direction-alert--success" role="status"><CheckCircle2 size={16} />{message}</div>}

    {!loading && !draft && <button className="social-direction-retry" onClick={() => void load()} type="button">
      <RefreshCw size={16} />Retry
    </button>}

    {draft && document && <form className="social-direction-document" onSubmit={save}>
      <header className="social-direction-document__header">
        <div><span>Creator document</span><strong>Public Social Platforms</strong></div>
        <small>Creator Profile #{document.creator_profile_id}</small>
      </header>

      {fields.map((field, index) => <section className="social-direction-section" key={field.key}>
        <label htmlFor={`social-direction-${field.key}`}>
          <span>Section {index + 1}</span>
          <strong>{field.title}</strong>
        </label>
        <textarea
          id={`social-direction-${field.key}`}
          rows={field.rows}
          value={draft[field.key]}
          onChange={(event) => setDraft((current) => current
            ? { ...current, [field.key]: event.target.value }
            : current)}
        />
      </section>)}

      <footer className="social-direction-actions">
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
