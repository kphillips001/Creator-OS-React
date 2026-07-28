import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { OfferingSelection, OfferingSelectionList } from "./types";
import "./offering-selector.css";

const empty: OfferingSelectionList = {
  items: [], total: 0, page: 1, pageSize: 20, totalPages: 1,
};
const label = (value: string | null | undefined) => value
  ? value.replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—";

export function CommercialOfferingSelectorPage() {
  const [data, setData] = useState(empty);
  const [selected, setSelected] = useState<OfferingSelection | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page), page_size: "20",
    });
    if (search) params.set("search", search);
    setLoading(true);
    developerFetch(`/api/v1/developer/offering-selector?${params}`, {
      cache: "no-store", signal: controller.signal,
    }).then(async (response) => {
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail || "Unable to load offering selections.");
      }
      return body as OfferingSelectionList;
    }).then((body) => {
      setData(body); setError("");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "Unable to load selector.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [page, search]);

  const submit = (event: FormEvent) => {
    event.preventDefault(); setPage(1); setSearch(query.trim());
  };

  return <section className="offering-selector">
    <PageHeader title="Commercial Offering Selector"
      description="Developer Tool — Read-only deterministic offering eligibility and selection." />
    <form className="offering-selector__search" onSubmit={submit}>
      <Search size={16} />
      <input aria-label="Search Commercial Offering Selector" value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search buyer UUID, handle, or display name" />
      <button type="submit">Search</button>
    </form>
    {loading && <div className="offering-selector__state">Evaluating offerings…</div>}
    {error && <div role="alert" className="offering-selector__state offering-selector__state--error">
      <AlertTriangle size={18} />{error}
    </div>}
    {!loading && !error && data.items.length === 0 &&
      <div className="offering-selector__state">No customer profiles found.</div>}
    {!loading && !error && data.items.length > 0 &&
      <div className="offering-selector__workspace">
        <div className="offering-selector__table"><table>
          <thead><tr><th>Buyer</th><th>Selected Offering</th>
            <th>Publication</th><th>Channel</th><th>Selection Reason</th>
            <th>Rejected</th></tr></thead>
          <tbody>{data.items.map((item) => <tr
            key={`${item.buyer.externalFanvueBuyerUuid}:${item.buyer.telegramUserId}`}
            onClick={() => setSelected(item)} aria-selected={selected === item}>
            <td><button type="button"
              aria-label={`View selector ${item.buyer.externalFanvueBuyerUuid}`}
              onClick={() => setSelected(item)}>
              {item.buyer.handle || item.buyer.displayName ||
                item.buyer.externalFanvueBuyerUuid || "Unknown buyer"}
            </button></td>
            <td>{item.selectedOffering?.title ||
              item.selectedOffering?.offeringId || "None"}</td>
            <td>{item.selectedOffering?.publicationProvider || "—"}</td>
            <td>{label(item.selectedOffering?.primarySalesChannel)}</td>
            <td>{label(item.selectionReason)}</td>
            <td>{item.evaluations.filter((value) => !value.eligible).length}</td>
          </tr>)}</tbody>
        </table></div>
        <aside className="offering-selector__detail"
          aria-label="Offering selector diagnostics">
          {selected ? <SelectorDetail value={selected} /> :
            <div className="offering-selector__empty">No selection selected.</div>}
        </aside>
      </div>}
    <nav className="offering-selector__pagination"
      aria-label="Commercial Offering Selector pagination">
      <button disabled={page <= 1}
        onClick={() => setPage((value) => value - 1)}>Previous</button>
      <span>Page {data.page} of {data.totalPages}</span>
      <button disabled={page >= data.totalPages}
        onClick={() => setPage((value) => value + 1)}>Next</button>
    </nav>
  </section>;
}

function SelectorDetail({ value }: { value: OfferingSelection }) {
  const eligible = value.evaluations.filter((item) => item.eligible).length;
  const rejected = value.evaluations.length - eligible;
  return <>
    <header><small>Selected Offering</small>
      <h2>{value.selectedOffering?.title || "No eligible offering"}</h2>
      <p>{label(value.selectionReason)}</p></header>
    <dl>
      <div><dt>Offering</dt><dd>{value.selectedOffering?.offeringId || "—"}</dd></div>
      <div><dt>Publication</dt><dd>{value.selectedOffering?.publicationId || "—"}</dd></div>
      <div><dt>Provider</dt><dd>{value.selectedOffering?.publicationProvider || "—"}</dd></div>
      <div><dt>Channel</dt><dd>{label(value.selectedOffering?.primarySalesChannel)}</dd></div>
      <div><dt>Eligible</dt><dd>{eligible}</dd></div>
      <div><dt>Rejected</dt><dd>{rejected}</dd></div>
    </dl>
    <h3>Eligibility Matrix</h3>
    <div className="offering-selector__matrix">{value.evaluations.map((item) =>
      <article key={item.offeringId} data-eligible={item.eligible}>
        <strong>{item.title || item.offeringId}</strong>
        <span>{item.eligible ? "Eligible" : "Rejected"}</span>
        <small>{item.exclusionReasons.map(label).join(", ") || "All checks passed"}</small>
      </article>)}
    </div>
    <h3>Filtering Summary</h3>
    <p>{value.exclusionReasons.map(label).join(", ") || "No exclusions."}</p>
    <details><summary>Expandable diagnostics</summary>
      <pre>{JSON.stringify(value.selectorMetadata, null, 2)}</pre>
    </details>
  </>;
}
