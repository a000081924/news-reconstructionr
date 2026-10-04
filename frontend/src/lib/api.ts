export type BBox = [number, number, number, number];
export interface Line { bbox: BBox; text: string; score: number }
export interface Block { id: number; order: number; label: string; bbox: BBox; text: string; lines: Line[] }
export interface Page { schema_version: number; engine: string; width: number; height: number; image: string; angle: number; blocks: Block[] }
export interface Engine { id: string; label: string; description: string; interactive: boolean; enabled: boolean; loaded: boolean }
export interface Document { id: string; name: string; page_id: string }
export interface Correction { block_id: number; line_index: number; text: string }
export interface Stage { id: number; stage: string; elapsed_ms?: number; position?: number; message?: string; engine?: string; width?: number; height?: number; blocks?: Block[]; lines?: Line[]; page?: Page }
export interface Job { id: string; page_id: string; engine: string; status: string; events: Stage[] }
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, init);
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`, response.status); }
  return response.status === 204 ? undefined as T : response.json();
}
const json = (method: string, body: unknown) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const query = (engine: string) => `?engine=${encodeURIComponent(engine)}`;
export const api = {
  engines: () => request<Engine[]>('/engines'), documents: () => request<Document[]>('/documents'),
  upload: (file: File) => { const body = new FormData(); body.append('file', file); return request<{document_id: string; page_id: string; cached: boolean}>('/documents', { method: 'POST', body }); },
  page: (id: string, engine: string) => request<Page>(`/pages/${id}${query(engine)}`),
  corrections: (id: string, engine: string) => request<Correction[]>(`/pages/${id}/corrections${query(engine)}`),
  save: (id: string, engine: string, corrections: Correction[]) => request<Page>(`/pages/${id}/corrections`, json('PUT', { engine, corrections })),
  undo: (id: string, engine: string) => request<Page>(`/pages/${id}/corrections${query(engine)}`, { method: 'DELETE' }),
  recognize: (id: string, engine: string) => request<{job_id: string}>(`/pages/${id}/recognize`, json('POST', { engine })),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  image: (id: string) => `/api/pages/${id}/image`,
  export: (id: string, engine: string, format: string) => `/api/pages/${id}/export${query(engine)}&format=${encodeURIComponent(format)}`,
  events: (id: string, after: number, onstage: (stage: Stage) => void, onerror: () => void) => { const source = new EventSource(`/api/jobs/${id}/events?after=${after}`); source.addEventListener('stage', event => onstage(JSON.parse((event as MessageEvent).data))); source.onerror = onerror; return () => source.close(); }
};
