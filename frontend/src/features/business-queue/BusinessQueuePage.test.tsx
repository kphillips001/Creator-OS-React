import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BusinessQueuePage,
  formatCountdown,
  QueueCountdown,
} from "./BusinessQueuePage";
const NOW = new Date("2026-09-15T15:00:00Z");
const job = (id = "job-1", seconds = 1934) => ({
  jobId: id,
  state: "SCHEDULED",
  accountName: "AvaBlackthorne",
  primaryPublishedAt: "2026-09-15T14:35:17Z",
  captionPreview: `Primary ${id}`,
  ctaText: "Chat with me",
  ctaUrl: "https://avablackthorne.com/me?p=opaque",
  sampledDelaySeconds: 2880,
  scheduledAt: new Date(NOW.getTime() + seconds * 1000).toISOString(),
  createdAt: "2026-09-15T14:35:17Z",
  attemptCount: 0,
});
const response = (body: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("CTA queue countdown formatting", () => {
  it.each([
    [1934000, "32:14"],
    [4328000, "1:12:08"],
    [42000, "00:42"],
    [0, "00:00"],
    [-1000, "00:00"],
  ])("formats %i milliseconds", (milliseconds, expected) =>
    expect(formatCountdown(milliseconds)).toBe(expected),
  );
  it("uses the absolute due time, recomputes from the clock, and does not drift after throttling", () => {
    const due = new Date(NOW.getTime() + 1934_000).toISOString();
    render(<QueueCountdown scheduledAt={due} onDue={vi.fn()} />);
    expect(screen.getByText("Posting in 32:14")).toHaveAccessibleName(
      "CTA scheduled to post in 32 minutes 14 seconds",
    );
    act(() => {
      vi.setSystemTime(new Date(NOW.getTime() + 94_000));
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("Posting in 30:39")).toBeInTheDocument();
  });
  it("shows a nonnegative due state, refreshes once, and cleans up its interval", () => {
    const refresh = vi.fn(),
      clear = vi.spyOn(window, "clearInterval"),
      due = new Date(NOW.getTime() + 1000).toISOString();
    const view = render(<QueueCountdown scheduledAt={due} onDue={refresh} />);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("Posting…")).toBeInTheDocument();
    expect(screen.queryByText(/-/)).not.toBeInTheDocument();
    expect(refresh).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(5000));
    expect(refresh).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(clear).toHaveBeenCalled();
  });
  it("supports independent countdowns", () => {
    render(
      <>
        <QueueCountdown
          scheduledAt={job("one", 42).scheduledAt}
          onDue={vi.fn()}
        />
        <QueueCountdown
          scheduledAt={job("two", 4328).scheduledAt}
          onDue={vi.fn()}
        />
      </>,
    );
    expect(screen.getByText("Posting in 00:42")).toBeInTheDocument();
    expect(screen.getByText("Posting in 1:12:08")).toBeInTheDocument();
  });
});

describe("BusinessQueuePage countdown lifecycle", () => {
  it("places the live countdown after the persisted delay without per-second API polling", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => response({ upcoming: [job()], history: [] }));
    render(<BusinessQueuePage />);
    const schedule = await screen.findByText(/Originally scheduled:/);
    expect(schedule).toHaveTextContent(/Delay: 48 min · Posting in 32:14/);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("performs one bounded refresh at zero and restarts from a later authoritative time", async () => {
    const later = {
      ...job(),
      scheduledAt: new Date(NOW.getTime() + 61_000).toISOString(),
    };
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() =>
        response({ upcoming: [job("job-1", 1)], history: [] }),
      )
      .mockImplementation(() => response({ upcoming: [later], history: [] }));
    render(<BusinessQueuePage />);
    await screen.findByText("Posting in 00:01");
    await act(async () => vi.advanceTimersByTime(1000));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Posting in 01:00")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(5000));
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("removes the countdown when authoritative refresh reports posted", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() =>
        response({ upcoming: [job("job-1", 1)], history: [] }),
      )
      .mockImplementation(() =>
        response({ upcoming: [], history: [{ ...job(), state: "POSTED" }] }),
      );
    render(<BusinessQueuePage />);
    await screen.findByText("Posting in 00:01");
    await act(async () => vi.advanceTimersByTime(1000));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText("No upcoming X CTA jobs.")).toBeInTheDocument();
    expect(screen.queryByText(/Posting/)).not.toBeInTheDocument();
  });
  it("hides stale countdown during Post Now and renders refreshed state", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let release: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() =>
        response({ upcoming: [job()], history: [] }),
      )
      .mockImplementationOnce(() => pending)
      .mockImplementation(() =>
        response({ upcoming: [], history: [{ ...job(), state: "POSTED" }] }),
      );
    render(<BusinessQueuePage />);
    await screen.findByText("Posting in 32:14");
    fireEvent.click(screen.getByRole("button", { name: "Post Now" }));
    expect(screen.queryByText(/Posting in/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    await act(async () =>
      release(
        new Response(JSON.stringify({ ...job(), state: "POSTED" }), {
          status: 200,
        }),
      ),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(screen.getByText("No upcoming X CTA jobs.")).toBeInTheDocument();
  });
  it("removes a cancelled item and its timer after the existing mutation", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() =>
        response({ upcoming: [job()], history: [] }),
      )
      .mockImplementationOnce(() => response({ ...job(), state: "CANCELLED" }))
      .mockImplementation(() =>
        response({ upcoming: [], history: [{ ...job(), state: "CANCELLED" }] }),
      );
    render(<BusinessQueuePage />);
    await screen.findByText("Posting in 32:14");
    fireEvent.click(screen.getByRole("button", { name: "Cancel CTA" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(screen.queryByText(/Posting in/)).not.toBeInTheDocument();
  });
  it("keeps independent item timestamps and existing Upcoming/History behavior", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      response({ upcoming: [job("one", 42), job("two", 4328)], history: [] }),
    );
    render(<BusinessQueuePage />);
    await screen.findByText("Primary one");
    expect(screen.getByText("Posting in 00:42")).toBeInTheDocument();
    expect(screen.getByText("Posting in 1:12:08")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(screen.getByText("No history X CTA jobs.")).toBeInTheDocument();
    expect(screen.queryByText(/Posting in/)).not.toBeInTheDocument();
  });
  it("uses wrapping schedule/card layout hooks suitable for constrained zoom", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      response({ upcoming: [job()], history: [] }),
    );
    render(<BusinessQueuePage />);
    const schedule = await screen.findByText(/Originally scheduled:/);
    expect(schedule).toHaveClass("queue-schedule");
    expect(within(schedule).getByText(/Posting in/)).toHaveClass(
      "queue-countdown",
    );
  });
});
