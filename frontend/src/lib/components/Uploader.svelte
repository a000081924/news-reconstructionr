<script lang="ts">
  let { busy, onupload }: { busy: boolean; onupload: (file: File) => void } = $props();
  let dragging = $state(false);
  // Files only: dragging selected text into a correction textarea must keep its default.
  const carriesFile = (event: DragEvent) => event.dataTransfer?.types.includes('Files') ?? false;
  function drop(event: DragEvent) { event.preventDefault(); dragging = false; const file = event.dataTransfer?.files[0]; if (file && !busy) onupload(file); }
</script>
<!-- A scan dropped beside the target would otherwise navigate the tab to it, losing the session. -->
<svelte:window ondragover={event => { if (carriesFile(event)) event.preventDefault(); }} ondrop={event => { if (carriesFile(event)) event.preventDefault(); }} />
<label class={['upload', { dragging }]} ondragover={event => { if (carriesFile(event)) { event.preventDefault(); dragging = !busy; } }} ondragleave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) dragging = false; }} ondrop={drop}>Upload newspaper scan<input type="file" accept="image/png,image/jpeg,image/webp,image/tiff,.tif,.tiff" disabled={busy} onchange={event => { const file = event.currentTarget.files?.[0]; if (file) onupload(file); event.currentTarget.value = ''; }} /></label>
<small>Drop a scan here or choose a file. PNG, JPEG, WebP or TIFF · up to 50 MiB</small>
