import { useCallback, useEffect, useRef, useState } from "react";
import "./business-queue.css";
type Job = {
  jobId: string;
  state: string;
  accountName: string;
  primaryPublishedAt: string;
  thumbnailReference?: string;
  captionPreview: string;
  ctaText: string;
  ctaUrl: string;
  sampledDelaySeconds: number;
  scheduledAt: string;
  createdAt: string;
  attemptCount: number;
  resultingXReplyId?: string;
  sentAt?: string;
  failureReason?: string;
};
type Data = { upcoming: Job[]; history: Job[] };
export function formatCountdown(milliseconds: number) {
  const total = Math.max(0, Math.ceil(milliseconds / 1000)),
    hours = Math.floor(total / 3600),
    minutes = Math.floor((total % 3600) / 60),
    seconds = total % 60,
    clock = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours ? `${hours}:${clock}` : clock;
}
function accessibleDuration(milliseconds: number) {
  const total = Math.max(0, Math.ceil(milliseconds / 1000)),
    hours = Math.floor(total / 3600),
    minutes = Math.floor((total % 3600) / 60),
    seconds = total % 60;
  return [
    hours && `${hours} ${hours === 1 ? "hour" : "hours"}`,
    minutes && `${minutes} ${minutes === 1 ? "minute" : "minutes"}`,
    `${seconds} ${seconds === 1 ? "second" : "seconds"}`,
  ]
    .filter(Boolean)
    .join(" ");
}
export function QueueCountdown({
  scheduledAt,
  onDue,
}: {
  scheduledAt: string;
  onDue: () => void;
}) {
  const dueAt = new Date(scheduledAt).getTime(),
    [remaining, setRemaining] = useState(() => Math.max(0, dueAt - Date.now())),
    notifiedFor = useRef<string | null>(null);
  useEffect(() => {
    const update = () => setRemaining(Math.max(0, dueAt - Date.now()));
    update();
    const interval = window.setInterval(update, 1000);
    return () => window.clearInterval(interval);
  }, [dueAt]);
  useEffect(() => {
    if (remaining > 0) {
      if (notifiedFor.current !== scheduledAt) notifiedFor.current = null;
      return;
    }
    if (notifiedFor.current === scheduledAt) return;
    notifiedFor.current = scheduledAt;
    onDue();
  }, [onDue, remaining, scheduledAt]);
  if (remaining <= 0)
    return (
      <span
        aria-label="CTA is due for authoritative posting status"
        className="queue-countdown"
      >
        Posting…
      </span>
    );
  return (
    <span
      aria-label={`CTA scheduled to post in ${accessibleDuration(remaining)}`}
      className="queue-countdown"
    >
      Posting in {formatCountdown(remaining)}
    </span>
  );
}
export function BusinessQueuePage() {
  const [data, setData] = useState<Data>({ upcoming: [], history: [] }),
    [tab, setTab] = useState<"upcoming" | "history">("upcoming"),
    [error, setError] = useState(""),
    [acting, setActing] = useState<Set<string>>(() => new Set());
  const load = useCallback(
    () =>
      fetch("/api/v1/business/queue/x-cta", { cache: "no-store" })
        .then(async (r) => {
          const b = await r.json();
          if (!r.ok) throw new Error(b.detail || "Unable to load queue.");
          setData(b);
        })
        .catch((e) => setError(String(e))),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const act = async (job: Job, action: string) => {
    if (action === "post-now" && !confirm("Post this CTA reply now?")) return;
    setActing((current) => new Set(current).add(job.jobId));
    try {
      const r = await fetch(
        `/api/v1/business/queue/x-cta/${job.jobId}/${action}`,
        { method: "POST" },
      );
      if (!r.ok) {
        const b = await r.json();
        setError(b.detail || "Action failed.");
        return;
      }
      await load();
    } finally {
      setActing((current) => {
        const next = new Set(current);
        next.delete(job.jobId);
        return next;
      });
    }
  };
  const jobs = data[tab];
  return (
    <main className="business-queue">
      <header>
        <small>Business</small>
        <h1>Queue</h1>
        <p>Durable follow-up publishing work.</p>
      </header>
      <section>
        <h2>
          X CTA Queue <small>{data.upcoming.length} Upcoming</small>
        </h2>
        <nav aria-label="X CTA Queue views">
          <button
            aria-pressed={tab === "upcoming"}
            onClick={() => setTab("upcoming")}
          >
            Upcoming
          </button>
          <button
            aria-pressed={tab === "history"}
            onClick={() => setTab("history")}
          >
            History
          </button>
        </nav>
        {error && <p role="alert">{error}</p>}
        {!jobs.length ? (
          <p className="queue-empty">No {tab} X CTA jobs.</p>
        ) : (
          <div className="queue-grid">
            {jobs.map((job) => {
              const busy = acting.has(job.jobId);
              return (
                <article key={job.jobId}>
                  <div className="queue-thumb">
                    {job.thumbnailReference ? (
                      <img
                        alt="Scheduled X post"
                        src={job.thumbnailReference}
                      />
                    ) : (
                      <span>X</span>
                    )}
                  </div>
                  <div>
                    <span
                      className={`queue-state queue-state--${job.state.toLowerCase()}`}
                    >
                      {job.state.replaceAll("_", " ")}
                    </span>
                    <h3>{job.accountName}</h3>
                    <p>{job.captionPreview}</p>
                    <small>
                      Published:{" "}
                      {new Date(job.primaryPublishedAt).toLocaleString()}
                    </small>
                    <br />
                    <small className="queue-schedule">
                      Originally scheduled:{" "}
                      {new Date(job.scheduledAt).toLocaleString()}{" "}
                      <span aria-hidden="true">·</span> Delay:{" "}
                      {Math.round(job.sampledDelaySeconds / 60)} min{" "}
                      {tab === "upcoming" &&
                        job.state === "SCHEDULED" &&
                        !busy && (
                          <>
                            <span aria-hidden="true">·</span>{" "}
                            <QueueCountdown
                              key={job.scheduledAt}
                              scheduledAt={job.scheduledAt}
                              onDue={load}
                            />
                          </>
                        )}
                    </small>
                    <p className="queue-cta">
                      {job.ctaText}
                      <br />
                      <a href={job.ctaUrl}>{job.ctaUrl}</a>
                    </p>
                    {job.resultingXReplyId && (
                      <small>CTA reply: {job.resultingXReplyId}</small>
                    )}
                    {job.failureReason && (
                      <p role="status">{job.failureReason}</p>
                    )}
                  </div>
                  {tab === "upcoming" && job.state === "SCHEDULED" && (
                    <div className="queue-actions">
                      <button
                        disabled={busy}
                        onClick={() => void act(job, "post-now")}
                      >
                        {busy ? "Working…" : "Post Now"}
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => void act(job, "cancel")}
                      >
                        Cancel CTA
                      </button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
