import type { Envelope, OperationResponse } from "@/types";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface Scope {
  context?: string;
  namespace?: string;
}

export async function getOperation<T>(
  path: string,
  scope: Scope,
  extra: Record<string, string | number | boolean | undefined> = {},
): Promise<OperationResponse<T>> {
  return request<OperationResponse<T>>(
    `${path}${qs({ context: scope.context, namespace: scope.namespace, ...extra })}`,
  );
}

export async function getEnvelope<T>(
  path: string,
  scope: Scope = {},
  extra: Record<string, string | number | boolean | undefined> = {},
): Promise<Envelope<T>> {
  return request<Envelope<T>>(`${path}${qs({ ...scope, ...extra })}`);
}

export async function postJson<T>(path: string, body: unknown): Promise<Envelope<T>> {
  return request<Envelope<T>>(path, { method: "POST", body: JSON.stringify(body) });
}

export async function del<T>(path: string): Promise<Envelope<T>> {
  return request<Envelope<T>>(path, { method: "DELETE" });
}

export function exportUrl(domain: string, scope: Scope, fmt: string): string {
  return `/api/v1/exports/${domain}${qs({ ...scope, fmt })}`;
}
