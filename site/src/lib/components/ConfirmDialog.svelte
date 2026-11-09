<script lang="ts">
	import { confirmState } from '$lib/confirm.svelte';

	let confirmButton: HTMLButtonElement | undefined = $state();

	function close(confirmed: boolean) {
		const request = confirmState.current;
		confirmState.current = null;
		request?.resolve(confirmed);
	}

	$effect(() => {
		if (confirmState.current) confirmButton?.focus();
	});
</script>

{#if confirmState.current}
	<div
		class="fixed inset-0 z-[100] flex items-center justify-center bg-gray-900/60 p-4"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) close(false);
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') close(false);
		}}
	>
		<div
			class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
			role="alertdialog"
			aria-modal="true"
			aria-labelledby="confirm-dialog-title"
			aria-describedby="confirm-dialog-message"
		>
			<h2 id="confirm-dialog-title" class="text-lg font-semibold text-gray-900">Please confirm</h2>
			<p id="confirm-dialog-message" class="mt-2 text-sm leading-relaxed text-gray-600">
				{confirmState.current.message}
			</p>
			<div class="mt-6 flex flex-wrap justify-end gap-3">
				<button
					type="button"
					class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
					onclick={() => close(false)}
				>
					Cancel
				</button>
				<button
					bind:this={confirmButton}
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-medium text-white {confirmState.current.danger
						? 'bg-red-600 hover:bg-red-700'
						: 'bg-blue-700 hover:bg-blue-800'}"
					onclick={() => close(true)}
				>
					{confirmState.current.confirmLabel}
				</button>
			</div>
		</div>
	</div>
{/if}
