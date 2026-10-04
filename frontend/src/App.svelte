<script lang="ts">
 import { onMount } from 'svelte';
 import { api, ApiError, type Page, type Document, type Engine, type Correction, type Stage } from './lib/api';
 import { editable } from './lib/render/layout';
 import Uploader from './lib/components/Uploader.svelte';
 import ProgressPanel from './lib/components/ProgressPanel.svelte';
 import PageCanvas from './lib/components/PageCanvas.svelte';
 import TextInspector from './lib/components/TextInspector.svelte';
 let documents = $state.raw<Document[]>([]), engines = $state.raw<Engine[]>([]), page = $state.raw<Page | null>(null), edits = $state.raw<Correction[]>([]);
 let pageId = $state(''), engine = $state(''), jobId = $state(''), image = $state(''), selected = $state<number | null>(null);
 let stages = $state.raw<Stage[]>([]), busy = $state(false), running = $state(false), saving = $state(false), error = $state(''), status = $state(''), reconnecting = $state(false);
 let closeStream: (() => void) | undefined, localPreview = '', version = 0;
 let regions = $derived((page?.blocks ?? []).filter(editable).sort((a,b) => a.order-b.order));
 function remember() { try { localStorage.setItem('newsrec-session', JSON.stringify({pageId, engine, jobId, selected})); } catch { /* Private browsing can disallow storage. */ } }
 function releasePreview() { if (localPreview) URL.revokeObjectURL(localPreview); localPreview = ''; }
 function fail(reason: unknown) { error = reason instanceof Error ? reason.message : String(reason); }
 async function loadPage() { const revision = ++version, id = pageId, name = engine; page = null; edits = []; status = ''; if (!id || !name) return; try { const [result, corrections] = await Promise.all([api.page(id,name), api.corrections(id,name)]); if (revision === version) { page = result; edits = corrections; status = 'Saved page loaded'; } } catch (reason) { if (revision !== version) return; if (reason instanceof ApiError && reason.status === 404) status = 'No recognition for this engine yet. Select Recognize to begin.'; else fail(reason); } }
 async function choose(id: string) { closeStream?.(); closeStream = undefined; running = false; jobId = ''; stages = []; selected = null; pageId = id; releasePreview(); image = id ? api.image(id) : ''; remember(); await loadPage(); }
 function applyStage(stage: Stage) {
  if (stages.some(s => s.id === stage.id)) return;
  stages = [...stages, stage]; reconnecting = false;
  if (stage.stage === 'layout' && stage.width && stage.height) page = { schema_version: 1, engine, image, angle: 0, width: stage.width, height: stage.height, blocks: (stage.blocks ?? []).map((b,i) => ({...b, id:b.id ?? i, order:b.order ?? i, text:b.text ?? '', lines:b.lines ?? []})) };
  if (stage.stage === 'lines' && page) {
   const real = page.blocks.filter(b => b.id !== -1), lines = [...(page.blocks.find(b => b.id === -1)?.lines ?? []), ...(stage.lines ?? [])];
   page = {...page, blocks: [...real, {id:-1, order:real.length, label:'recognized_lines', bbox:[0,0,page.width,page.height], text:lines.map(l=>l.text).join('\n'), lines}]};
  }
  if (stage.stage === 'done') { if (stage.page) page = stage.page; running = false; jobId = ''; closeStream?.(); closeStream = undefined; remember(); void loadPage(); }
  if (stage.stage === 'error') { running = false; jobId = ''; closeStream?.(); closeStream = undefined; remember(); error = stage.message ?? 'Recognition failed'; }
 }
 async function connect(id: string) { closeStream?.(); jobId = id; running = true; remember(); const snapshot = await api.job(id).catch(reason => { running = false; status = 'Reload to reconnect to the saved job.'; throw reason; }); if (jobId !== id) return; stages = []; snapshot.events.forEach(applyStage); if (snapshot.status === 'done' || snapshot.status === 'error') { running = false; return; } closeStream = api.events(id, stages.at(-1)?.id ?? 0, applyStage, () => reconnecting = true); }
 async function recognize() { error = ''; busy = true; try { const result = await api.recognize(pageId,engine); edits = []; stages = []; await connect(result.job_id); } catch (reason) { fail(reason); } finally { busy = false; } }
 async function upload(file: File) { error = ''; busy = true; closeStream?.(); releasePreview(); page = null; pageId = ''; jobId = ''; edits = []; remember(); stages = []; selected = null; localPreview = URL.createObjectURL(file); image = localPreview; try { const result = await api.upload(file); pageId = result.page_id; jobId = ''; remember(); documents = await api.documents(); image = api.image(pageId); releasePreview(); if (result.cached) { await loadPage(); status = 'This scan was recognized before; its saved result and corrections were reused.'; } else status = 'Scan uploaded. Select Recognize to begin.'; } catch (reason) { fail(reason); } finally { busy = false; } }
 async function save(changes: Correction[]) { saving = true; error = ''; const replacement = [...edits.filter(e => !changes.some(c => c.block_id === e.block_id && c.line_index === e.line_index)), ...changes]; try { page = await api.save(pageId,engine,replacement); edits = replacement; status = 'Correction saved'; } catch (reason) { fail(reason); throw reason; } finally { saving = false; } }
 async function undo() { saving = true; error = ''; try { page = await api.undo(pageId,engine); edits = []; status = 'Original recognized text restored'; } catch (reason) { fail(reason); } finally { saving = false; } }
 onMount(() => { void (async () => { try { [engines,documents] = await Promise.all([api.engines(),api.documents()]); let saved: {pageId?:string; engine?:string; jobId?:string; selected?:number} = {}; try { saved = JSON.parse(localStorage.getItem('newsrec-session') || '{}'); } catch { /* Ignore damaged local preferences. */ } engine = engines.find(e=>e.id===saved.engine && e.enabled)?.id ?? engines.find(e=>e.enabled)?.id ?? engines[0]?.id ?? ''; pageId = documents.find(d=>d.page_id===saved.pageId)?.page_id ?? ''; selected = saved.selected ?? null; image = pageId ? api.image(pageId) : ''; await loadPage(); if (saved.jobId && pageId === saved.pageId) await connect(saved.jobId); } catch (reason) { running = false; fail(reason); } })(); return () => { closeStream?.(); releasePreview(); version++; }; });
</script>
<header><div><p class="eyebrow">ARCHIVE / RECONSTRUCTION</p><h1>The newspaper workbench</h1><p>Preserve the page. Make its words readable.</p></div><div class="upload-box"><Uploader busy={busy || running || saving} onupload={upload} /></div></header>
<main>
 <section class="selection" aria-label="Document controls"><label>Document<select disabled={busy || running || saving} value={pageId} onchange={event => void choose(event.currentTarget.value)}><option value="">Choose a saved document</option>{#each documents as document (document.id)}<option value={document.page_id}>{document.name}</option>{/each}</select></label><label>Recognition engine<select disabled={busy || running || saving} value={engine} onchange={event => { engine = event.currentTarget.value; selected = null; remember(); void loadPage(); }}>{#each engines as model (model.id)}<option value={model.id}>{model.label}{model.enabled ? (model.loaded ? '' : ' - loads on first use') : ' - offline'}</option>{/each}</select></label><button disabled={!pageId || busy || running || saving || !engines.find(e=>e.id===engine)?.enabled} onclick={recognize}>{running ? 'Recognizing...' : 'Recognize'}</button></section>
 <p class="engine-note">{engines.find(e=>e.id===engine)?.description ?? 'Connecting to the recognition server...'}{#if engines.find(e=>e.id===engine)?.enabled === false}{' '}This engine cannot run here, so Recognize stays unavailable while it is selected.{:else if page}{' '}Undo saved edits before running recognition again.{/if}</p>
 {#if error}<p class="error" role="alert">{error}</p>{/if}<p class="status" role="status">{status}</p>
 <ProgressPanel {stages} {reconnecting} />
 <div class="workspace"><PageCanvas {page} {image} {selected} onselect={id => {selected=id; remember();}} />{#key `${pageId}:${engine}`}<TextInspector blocks={regions} {selected} onselect={id => {selected=id; remember();}} onsave={save} onundo={undo} {saving} hasEdits={edits.length > 0} canEdit={!running && !busy} />{/key}</div>
 {#if page && !running}<footer><span>{page.width.toLocaleString()} x {page.height.toLocaleString()} px / {page.blocks.length} regions</span><nav aria-label="Export corrected page">Export: {#each ['html','alto','page-xml'] as format (format)}<a href={api.export(pageId,engine,format)} download>{format.toUpperCase()}</a>{/each}</nav></footer>{/if}
</main>
