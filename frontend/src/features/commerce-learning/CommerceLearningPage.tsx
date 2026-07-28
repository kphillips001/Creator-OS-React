import { useEffect, useState } from "react";
import { developerFetch } from "../../infrastructure/api/developerFetch";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./commerce-learning.css";

type Profile = {
  learningProfileId: string; buyerUuid: string; confidence: number;
  evidenceCount: number; preferences: Record<string, Record<string, {
    score: number; confidence: number; observations: number;
  }>>; outcomeCounts: Record<string, number>; preferredOfferingType: string | null;
  averagePriceMinor: number | null; updatedAt: string;
};
type Detail = Profile & { recentOutcomes: Array<{
  outcomeId: string; offeringId: string; outcomeType: string;
  observedAt: string; evidence: Record<string, unknown>;
}> };

export function CommerceLearningPage() {
  const [items, setItems] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    void developerFetch("/api/v1/developer/commerce-learning", { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json() as { items?: Profile[]; detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load Commerce learning.");
        setItems(body.items || []);
      }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load Commerce learning."));
  }, []);
  const choose = (buyer: string) => {
    void developerFetch(`/api/v1/developer/commerce-learning/${buyer}`, { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json() as Detail & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load learning profile.");
        setSelected(body);
      }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load learning profile."));
  };
  return <section className="commerce-learning">
    <PageHeader title="Commerce Learning" description="Developer Tool — Read-only observed recommendation preferences and outcomes." />
    {error && <p role="alert">{error}</p>}
    <div className="commerce-learning__workspace">
      <div>{items.length === 0 ? <p>No observed Commerce learning profiles.</p> :
        <table><thead><tr><th>Buyer</th><th>Confidence</th><th>Evidence</th><th>Preferred Type</th><th>Updated</th></tr></thead>
          <tbody>{items.map((item) => <tr key={item.learningProfileId}>
            <td><button type="button" onClick={() => choose(item.buyerUuid)}>{item.buyerUuid}</button></td>
            <td>{Math.round(item.confidence * 100)}%</td><td>{item.evidenceCount}</td>
            <td>{item.preferredOfferingType || "—"}</td><td>{new Date(item.updatedAt).toLocaleString()}</td>
          </tr>)}</tbody></table>}</div>
      <aside>{!selected ? <p>No learning profile selected.</p> : <LearningDetail value={selected} />}</aside>
    </div>
  </section>;
}

function LearningDetail({ value }: { value: Detail }) {
  const preferences = Object.entries(value.preferences).flatMap(([category, entries]) =>
    Object.entries(entries).map(([name, evidence]) => ({ category, name, ...evidence })))
    .sort((left, right) => right.score - left.score);
  return <><h2>Observed Preferences</h2>
    <p>Confidence {Math.round(value.confidence * 100)}% · {value.evidenceCount} observed events</p>
    <dl>{preferences.map((item) => <div key={`${item.category}:${item.name}`}>
      <dt>{item.category} · {item.name}</dt><dd>{Math.round(item.score * 100)}% ({item.observations} observations)</dd>
    </div>)}</dl>
    <h2>Learning Sources</h2><pre>{JSON.stringify(value.outcomeCounts, null, 2)}</pre>
    <h2>Recent Outcomes</h2><ol>{value.recentOutcomes.map((item) =>
      <li key={item.outcomeId}><strong>{item.outcomeType}</strong> · {item.offeringId} · {new Date(item.observedAt).toLocaleString()}</li>)}</ol>
  </>;
}
