<script lang="ts">
 import type { Stage } from '../api';
 let { stages, reconnecting }: { stages: Stage[]; reconnecting: boolean } = $props();
 let latest = $derived(stages.at(-1));
</script>
<section class="progress" aria-label="Recognition progress" aria-live="polite">
 {#if latest}<strong>{latest.stage === 'queued' ? `Queued · position ${latest.position}` : latest.stage === 'loading' ? `Loading the ${latest.engine} models…` : latest.stage === 'done' ? 'Reconstruction ready' : latest.stage === 'error' ? 'Recognition failed' : `Recognition · ${latest.stage}`}</strong>
 <span>{latest.elapsed_ms === undefined ? '' : `${(latest.elapsed_ms / 1000).toFixed(1)} s`}</span>
 {#if latest.message}<p>{latest.message}</p>{/if}
 <ol>{#each stages.filter(s => ['layout', 'lines', 'done'].includes(s.stage)) as stage (stage.id)}<li>{stage.stage === 'layout' ? `${stage.blocks?.length ?? 0} layout regions` : stage.stage === 'lines' ? `${stage.lines?.length ?? 0} recognized lines` : 'Page saved'}</li>{/each}</ol>
 {:else}<span>Upload a scan or select a saved document.</span>{/if}
 {#if reconnecting}<p>Connection interrupted. Reconnecting automatically…</p>{/if}
</section>
