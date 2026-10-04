<script lang="ts">
 import type { Page } from '../api';
 import { createBlur } from '../render/blur-gl';
 import { drawText, drawable, FONT } from '../render/layout';
 import CompareSlider from './CompareSlider.svelte';
 let { page, image, selected, onselect }: { page: Page | null; image: string; selected: number | null; onselect: (id: number) => void } = $props();
 let viewport = $state<HTMLDivElement>(), glCanvas = $state<HTMLCanvasElement>(), textCanvas = $state<HTMLCanvasElement>();
 let scan = $state.raw<HTMLImageElement | null>(null);
 let zoom = $state(0.1), fit = $state<'page' | 'width' | null>('page'), width = $state(600), height = $state(600);
 let compare = $state(false), position = $state(50), blur = $state(3), outlines = $state(true), warning = $state('');
 let renderer = $state.raw<ReturnType<typeof createBlur> | null>(null);
 let pageWidth = $derived(page?.width || scan?.naturalWidth || 600), pageHeight = $derived(page?.height || scan?.naturalHeight || 800);
 let scale = $derived(fit ? Math.min(1, (width - 32) / pageWidth, fit === 'page' ? (height - 32) / pageHeight : Infinity) : zoom);
 $effect(() => { const src = image; const img = new Image(); let active = true; img.onload = () => { if (active) scan = img; }; img.onerror = () => { if (active) { scan = null; warning = 'Preview is unavailable until the server normalizes this image.'; } }; scan = null; warning = ''; if (src) img.src = src; return () => { active = false; img.onload = img.onerror = null; }; });
 $effect(() => { if (!viewport) return; const observer = new ResizeObserver(([entry]) => { width = entry.contentRect.width; height = entry.contentRect.height; }); observer.observe(viewport); return () => observer.disconnect(); });
 $effect(() => { renderer = null; if (!glCanvas || !scan || !page) return; try { const current = createBlur(glCanvas, scan, page); renderer = current; return () => current.dispose(); } catch (error) { warning = String(error); } });
 $effect(() => { renderer?.render(blur); });
 $effect(() => {
  if (!textCanvas || !page) return;
  const limit = Math.min(1, 4096 / Math.max(page.width, page.height)); textCanvas.width = Math.round(page.width * limit); textCanvas.height = Math.round(page.height * limit);
  const ctx = textCanvas.getContext('2d'); if (!ctx) return; ctx.scale(limit, limit); ctx.textBaseline = 'top'; ctx.fillStyle = '#111';
  for (const block of page.blocks.filter(drawable)) for (const line of block.lines?.length ? block.lines : [block]) for (const glyph of drawText(line.text, line.bbox)) { ctx.font = `${glyph.size}px ${FONT}`; ctx.fillText(glyph.character, glyph.x + (glyph.size - ctx.measureText(glyph.character).width) / 2, glyph.y); }
  for (const block of page.blocks) if (outlines || block.id === selected) { const [x1,y1,x2,y2] = block.bbox; ctx.strokeStyle = block.id === selected ? '#245bd6' : '#c86932'; ctx.lineWidth = Math.max(2, 1 / Math.max(scale, 0.01)); ctx.strokeRect(x1,y1,x2-x1,y2-y1); }
 });
 function select(event: MouseEvent) { if (!page) return; const bounds = event.currentTarget instanceof HTMLElement ? event.currentTarget.getBoundingClientRect() : null; if (!bounds) return; const x = (event.clientX-bounds.left)/scale, y = (event.clientY-bounds.top)/scale; const hit = page.blocks.filter(b => (b.lines?.length ? b.lines : [b]).some(l => x >= l.bbox[0] && x <= l.bbox[2] && y >= l.bbox[1] && y <= l.bbox[3])).sort((a,b) => (a.bbox[2]-a.bbox[0])*(a.bbox[3]-a.bbox[1])-(b.bbox[2]-b.bbox[0])*(b.bbox[3]-b.bbox[1]))[0]; if (hit) onselect(hit.id); }
</script>
<section class="viewer">
 <div class="toolbar"><button class="secondary" aria-pressed={fit === 'page'} onclick={() => fit = 'page'}>Fit page</button><button class="secondary" aria-pressed={fit === 'width'} onclick={() => fit = 'width'}>Fit width</button><label>Zoom<input type="range" min="0.01" max="1" step="0.01" value={scale} oninput={event => { zoom = Number(event.currentTarget.value); fit = null; }} />{Math.round(scale * 100)}%</label><label>Blur<input type="range" min="0" max="8" bind:value={blur} /></label><label><input type="checkbox" bind:checked={outlines} /> Regions</label><label><input type="checkbox" bind:checked={compare} /> Compare</label></div>
 {#if warning}<p role="status">{warning}</p>{/if}
 <div class="viewport" bind:this={viewport}>
 {#if image}<div class="page" role="presentation" onclick={select} style:width={`${Math.max(1, pageWidth * scale)}px`} style:height={`${Math.max(1, pageHeight * scale)}px`}>
 <img class="layer" src={image} alt="Original newspaper scan" />
 <canvas class="layer" bind:this={glCanvas} style:visibility={renderer ? 'visible' : 'hidden'} aria-label="Blurred original scan"></canvas>
 <canvas class="layer" bind:this={textCanvas} aria-label="Reconstructed newspaper text; use the text inspector to select regions"></canvas>
 {#if compare}<img class="layer" src={image} alt="Original comparison" style:clip-path={`inset(0 ${100-position}% 0 0)`} /><CompareSlider bind:value={position} />{/if}
 </div>{:else}<div class="empty"><span>NEWSPAPER ARCHIVE</span><h2>Bring a historic page into focus.</h2><p>Upload a scan to reconstruct its layout and correct recognized text.</p></div>{/if}
 </div>
</section>
