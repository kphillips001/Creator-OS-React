import { useEffect, useState, type FormEvent } from "react";
import { developerFetch } from "../../infrastructure/api/developerFetch";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./recommendation-diagnostics.css";

type Item = {
  outcomeId: string; timestamp: string; buyer: string; offeringId: string;
  outcome: string; engineVersion: string | null; activeIntentOverride: boolean;
  candidateCount: number | null; eligibleCount: number | null;
  rejectedCount: number | null; selectedScore: number | null;
  selectedTitle: string | null; explanation: string | null;
  trace: { recommendationTrace?: Candidate[] };
  evidence: Record<string, unknown>;
  purchaseIntent?: { status: string | null; attribution: string | null };
  currentLearningProfile?: {
    preferences: Record<string, unknown>; outcomeCounts: Record<string, number>;
    confidence: number; evidenceCount: number; snapshotType: string;
    updatedAt: string | null;
  } | null;
};
type Candidate = {
  rank: number; offeringId: string; title: string; finalScore: number;
  selected: boolean; reason: string;
  components: Array<{
    key: string; rawValue: number | boolean | null;
    weightedContribution: number; explanation: string;
    evidence: Record<string, unknown>;
  }>;
};
type Response = {
  items: Item[]; total: number;
  statistics: {
    outcomes: number; purchases: number; ignoredExpired: number;
    profiles: number; latest: string | null;
  };
};

export function RecommendationDiagnosticsPage() {
  const [data, setData] = useState<Response | null>(null);
  const [selected, setSelected] = useState<Item | null>(null);
  const [outcome, setOutcome] = useState("");
  const [engine, setEngine] = useState("");
  const [filters, setFilters] = useState({ outcome: "", engine: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);
  useEffect(() => {
    const refresh = () => setRefreshVersion((value) => value + 1);
    window.addEventListener("creator-os:diagnostics-invalidated", refresh);
    return () => window.removeEventListener("creator-os:diagnostics-invalidated", refresh);
  }, []);
  useEffect(() => {
    const params = new URLSearchParams({ page: "1", page_size: "50" });
    if (filters.outcome) params.set("outcome", filters.outcome);
    if (filters.engine) params.set("engine_version", filters.engine);
    setLoading(true); setError("");
    void developerFetch(`/api/v1/developer/recommendations?${params}`, {
      cache: "no-store",
    }).then(async (response) => {
      const body = await response.json() as Response & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load recommendation diagnostics.");
      setData(body);
    }).catch((reason: unknown) => setError(
      reason instanceof Error ? reason.message : "Unable to load recommendation diagnostics.",
    )).finally(() => setLoading(false));
  }, [filters, refreshVersion]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFilters({ outcome, engine });
  };
  const openDetail = (item: Item) => {
    setError("");
    void developerFetch(
      `/api/v1/developer/recommendations/${item.outcomeId}`,
      { cache: "no-store" },
    ).then(async (response) => {
      const body = await response.json() as Item & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load recommendation detail.");
      setSelected(body);
    }).catch((reason: unknown) => setError(
      reason instanceof Error ? reason.message : "Unable to load recommendation detail.",
    ));
  };
  return <section className="recommendation-diagnostics">
    <PageHeader title="Recommendation Diagnostics" description="Developer Tool — Read-only recommendation decisions, outcomes, and exact ranking traces." />
    <form className="recommendation-diagnostics__filters" onSubmit={submit}>
      <label>Outcome<select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
        <option value="">All outcomes</option>
        {["PRESENTED", "OPENED", "PURCHASED", "IGNORED", "EXPIRED", "DECLINED", "ABANDONED", "REFUNDED", "WOULD_HAVE_SOLD"].map((value) =>
          <option key={value}>{value}</option>)}
      </select></label>
      <label>Engine version<input value={engine} onChange={(event) => setEngine(event.target.value)} /></label>
      <button type="submit">Apply filters</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {data && <div className="recommendation-diagnostics__summary">
      <article><strong>{data.statistics.outcomes}</strong><span>Outcomes recorded</span></article>
      <article><strong>{data.statistics.profiles}</strong><span>Learning profiles</span></article>
      <article><strong>{data.statistics.purchases}</strong><span>Purchases</span></article>
      <article><strong>{data.statistics.ignoredExpired}</strong><span>Ignored / expired</span></article>
    </div>}
    <div className="recommendation-diagnostics__workspace">
      <section>{loading ? <p>Loading recommendation diagnostics…</p> :
        !data?.items.length ? <p>No recommendation outcomes match these filters.</p> :
          <table><thead><tr><th>Time</th><th>Buyer</th><th>Selected offering</th><th>Score</th><th>Outcome</th><th /></tr></thead>
            <tbody>{data.items.map((item) => <tr key={item.outcomeId}>
              <td>{new Date(item.timestamp).toLocaleString()}</td><td>{item.buyer}</td>
              <td>{item.selectedTitle || item.offeringId}</td><td>{item.selectedScore?.toFixed(3) || "—"}</td>
              <td>{item.outcome}</td><td><button type="button" onClick={() => openDetail(item)}>Open details</button></td>
            </tr>)}</tbody></table>}</section>
      <aside>{selected ? <RecommendationDetail item={selected} /> : <p>No recommendation selected.</p>}</aside>
    </div>
  </section>;
}

function RecommendationDetail({ item }: { item: Item }) {
  const candidates = item.trace.recommendationTrace || [];
  const selected = candidates.find((candidate) => candidate.selected);
  return <><h2>Decision overview</h2>
    <dl><div><dt>Engine</dt><dd>{item.engineVersion || "Not captured"}</dd></div>
      <div><dt>Active intent override</dt><dd>{item.activeIntentOverride ? "Yes" : "No"}</dd></div>
      <div><dt>Eligible / rejected</dt><dd>{item.eligibleCount ?? "—"} / {item.rejectedCount ?? "—"}</dd></div>
      <div><dt>Outcome</dt><dd>{item.outcome}</dd></div></dl>
    {item.outcome === "WOULD_HAVE_SOLD" && <div className="recommendation-diagnostics__suppression"><strong>Suppressed · Relationship Mode</strong><span>Would Have Sold</span><span>No Purchase Intent Created</span></div>}
    <p>{item.explanation || "No explanation captured."}</p>
    <h2>Candidate ranking</h2>
    {candidates.length === 0 ? <p>No candidate trace was captured for this outcome.</p> :
      <ol>{candidates.map((candidate) => <li key={candidate.offeringId}>
        <strong>#{candidate.rank} {candidate.title}</strong> — {candidate.finalScore.toFixed(3)}
        {candidate.selected && <span> Selected</span>}<p>{candidate.reason}</p>
      </li>)}</ol>}
    {selected && <><h2>Score breakdown</h2><table><tbody>{selected.components.map((component) =>
      <tr key={component.key}><th>{component.key.replaceAll("_", " ")}</th>
        <td>{typeof component.rawValue === "number" ? component.rawValue.toFixed(3) : String(component.rawValue)}</td>
        <td>{component.weightedContribution.toFixed(3)}</td><td>{component.explanation}</td></tr>)}</tbody></table></>}
    <h2>Observed outcome evidence</h2><pre>{JSON.stringify(item.evidence, null, 2)}</pre>
    <h2>Purchase Intent</h2><p>{item.purchaseIntent?.status || "Not linked"} · {item.purchaseIntent?.attribution || "No attribution"}</p>
    <h2>Current learning profile</h2>
    {!item.currentLearningProfile ? <p>No observed commerce-learning history yet.</p> :
      <><p>This is the current profile, updated {item.currentLearningProfile.updatedAt ? new Date(item.currentLearningProfile.updatedAt).toLocaleString() : "at an unknown time"}; it is not the recommendation-time snapshot.</p>
        <pre>{JSON.stringify(item.currentLearningProfile, null, 2)}</pre></>}
  </>;
}
