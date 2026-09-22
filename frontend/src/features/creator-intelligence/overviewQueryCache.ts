type Entry = { value: unknown; storedAt: number };

const values = new Map<string, Entry>();
const inFlight = new Map<string, Promise<unknown>>();

export function peekOverviewQuery<T>(key: string, maxAgeMs: number): T | null {
  const entry = values.get(key);
  if (!entry || Date.now() - entry.storedAt > maxAgeMs) return null;
  return entry.value as T;
}

export function overviewQuery<T>(
  key: string,
  loader: () => Promise<T>,
): Promise<T> {
  const current = inFlight.get(key);
  if (current) return current as Promise<T>;
  const request = loader().then((value) => {
    values.set(key, { value, storedAt: Date.now() });
    return value;
  }).finally(() => {
    if (inFlight.get(key) === request) inFlight.delete(key);
  });
  inFlight.set(key, request);
  return request;
}

export function clearOverviewQueryCache() {
  values.clear();
  inFlight.clear();
}
