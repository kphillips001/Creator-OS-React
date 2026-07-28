export function developerFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Creator-OS-Developer", "true");
  return fetch(input, { ...init, headers });
}
