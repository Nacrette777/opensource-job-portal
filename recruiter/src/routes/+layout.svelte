<script lang="ts">
	import '../app.css';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	// The favicon is set in app.html (GradBridge mark).
	let { children } = $props();
</script>

{@render children?.()}
<ConfirmDialog />
