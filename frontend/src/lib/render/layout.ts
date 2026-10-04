import type { BBox, Block } from '../api';
export const FONT = '"Microsoft JhengHei", "MingLiU", "Noto Sans TC", serif';
const SKIP = new Set(['image', 'figure', 'chart', 'table', 'formula', 'seal']);
export const editable = (block: Block) => !SKIP.has(block.label);
export const drawable = (block: Block) => Boolean(block.text?.trim()) && editable(block);
export function fitRuns(n: number, w: number, h: number, vertical: boolean) {
  if (n <= 0 || !Number.isFinite(w + h) || w <= 0 || h <= 0) return { size: 0, per: 1 };
  const along = vertical ? h : w, across = vertical ? w : h;
  const perAt = (s: number) => Math.floor(along / s + 1e-9);
  const fits = (s: number) => { const per = perAt(s); return per >= 1 && Math.ceil(n / per) * s <= across + 1e-9; };
  let lo = 1, hi = Math.max(along, across);
  if (!fits(lo)) return { size: 0, per: 1 };
  if (fits(hi)) lo = hi;
  else for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid; }
  return { size: lo, per: Math.max(1, perAt(lo)) };
}
export interface Glyph { character: string; x: number; y: number; size: number }
/** Pure em-cell commands. Renderer centers narrow glyphs using actual font metrics. */
export function drawText(text: string, box: BBox): Glyph[] {
  const [x1, y1, x2, y2] = box, w = x2 - x1, h = y2 - y1, vertical = h >= w;
  const segments = text.split(/\n+/).map(s => s.trim()).filter(Boolean);
  if (!segments.length || w <= 0 || h <= 0) return [];
  let runs: string[][], size: number;
  if (segments.length > 1) {
    const longest = Math.max(...segments.map(s => Array.from(s).length));
    size = Math.min((vertical ? w : h) / segments.length, (vertical ? h : w) / longest);
    runs = segments.map(s => Array.from(s));
  } else {
    const chars = Array.from(segments[0]), fit = fitRuns(chars.length, w, h, vertical);
    size = fit.size; runs = [];
    for (let i = 0; i < chars.length; i += fit.per) runs.push(chars.slice(i, i + fit.per));
  }
  if (size < 3) return [];
  return runs.flatMap((run, r) => run.map((character, i) => ({ character, size, x: vertical ? x2 - (r + 1) * size : x1 + i * size, y: vertical ? y1 + i * size : y1 + r * size })));
}
