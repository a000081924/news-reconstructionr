<script lang="ts">
 import type { Block, Correction } from '../api';
 let { blocks, selected, onselect, onsave, onundo, saving, hasEdits, canEdit }: { blocks: Block[]; selected: number | null; onselect: (id: number) => void; onsave: (edits: Correction[]) => Promise<void>; onundo: () => void; saving: boolean; hasEdits: boolean; canEdit: boolean } = $props();
 let block = $derived(blocks.find(b => b.id === selected));
 let drafts = $state<Record<string, string>>({});
 let fields = $derived(block ? (block.lines?.length ? block.lines.map((line, index) => ({ index, text: line.text })) : [{ index: -1, text: block.text }]) : []);
 const key = (id: number, index: number) => `${id}:${index}`;
 async function save() {
  if (!block) return;
  const blockId = block.id;
  const changes = fields.map(f => ({ block_id: blockId, line_index: f.index, text: drafts[key(blockId, f.index)] ?? f.text }));
  try {
   await onsave(changes);
   const remaining = {...drafts};
   for (const change of changes) delete remaining[key(blockId, change.line_index)];
   drafts = remaining;
  } catch { /* Keep the draft for retry; parent displays the error. */ }
 }

</script>
<aside class="inspector">
 <h2>Text inspector</h2>
 <label>Region<select disabled={saving} value={selected ?? ''} onchange={event => onselect(Number(event.currentTarget.value))}><option value="" disabled>Choose a region</option>{#each blocks as region (region.id)}<option value={region.id}>Region {region.order ?? region.id} · {region.label.replaceAll('_', ' ')}</option>{/each}</select></label>
 {#if block}
 <form onsubmit={event => { event.preventDefault(); void save(); }}>
 <p>{block.label.replaceAll('_', ' ')} · {fields.length} {fields.length === 1 ? 'line' : 'lines'}</p>
 {#each fields as field (field.index)}
 <label> {field.index < 0 ? 'Recognized text' : `Line ${field.index + 1}`}<textarea lang="zh-Hant" spellcheck="false" rows="3" disabled={!canEdit || saving} value={drafts[key(block.id, field.index)] ?? field.text} oninput={event => { drafts[key(block!.id, field.index)] = event.currentTarget.value; }}></textarea></label>
 {/each}
 <button disabled={saving || !canEdit} type="submit">{saving ? 'Saving…' : 'Save correction'}</button>
 </form>
 {:else}<p>Select a region on the page or from the list to inspect its text.</p>{/if}
 <button class="secondary" disabled={saving || !hasEdits || !canEdit} onclick={() => { drafts = {}; onundo(); }}>Undo all page edits</button>
 <small>Saved corrections persist after reload and are included in exports.</small>
</aside>
