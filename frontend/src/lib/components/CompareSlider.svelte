<script lang="ts">
 let { value = $bindable(50) }: { value?: number } = $props();
 // Rendered inside .page, so the parent's box is the 0-100% track.
 let handle = $state<HTMLDivElement>();
 const clamp = (percent: number) => Math.min(100, Math.max(0, Math.round(percent)));
 function track(event: PointerEvent) {
  const bounds = handle?.parentElement?.getBoundingClientRect();
  if (bounds?.width) value = clamp(((event.clientX - bounds.left) / bounds.width) * 100);
 }
 function grab(event: PointerEvent) {
  // Keep the drag off the scan underneath: no image drag, no region selection.
  event.preventDefault();
  event.stopPropagation();
  handle?.focus();
  handle?.setPointerCapture(event.pointerId);
  track(event);
 }
 function nudge(event: KeyboardEvent) {
  const step = event.shiftKey ? 10 : 1;
  const target: Record<string, number> = {
   ArrowLeft: value - step, ArrowDown: value - step,
   ArrowRight: value + step, ArrowUp: value + step,
   Home: 0, End: 100,
  };
  if (!(event.key in target)) return;
  event.preventDefault();
  value = clamp(target[event.key]);
 }
</script>
<div
 bind:this={handle}
 class="divider"
 style:left={`${value}%`}
 role="slider"
 tabindex="0"
 aria-label="Amount of original scan visible"
 aria-valuemin="0"
 aria-valuemax="100"
 aria-valuenow={value}
 aria-valuetext={`${value}% original scan`}
 onpointerdown={grab}
 onpointermove={event => { if (handle?.hasPointerCapture(event.pointerId)) track(event); }}
 onpointerup={event => handle?.releasePointerCapture(event.pointerId)}
 onkeydown={nudge}
 onclick={event => event.stopPropagation()}
><span class="grip" aria-hidden="true"></span></div>
