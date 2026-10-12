<script lang="ts">
	import { ArrowLeft, Star, StarOff, Lock } from '@lucide/svelte';
	import { enhance } from '$app/forms';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const formatDate = (value: string) => new Date(value).toLocaleDateString();
</script>

<svelte:head>
	<title>My shortlist - Candidates - PeelJobs Recruiter</title>
</svelte:head>

<div class="max-w-5xl space-y-6">
	<a href="/dashboard/candidates/" class="inline-flex items-center gap-1 text-sm text-muted hover:text-black"><ArrowLeft class="w-4 h-4" /> Back to candidates</a>
	<div>
		<h1 class="text-2xl md:text-3xl font-bold text-black flex items-center gap-2"><Star class="w-8 h-8" /> My shortlist</h1>
		<p class="mt-1 flex items-center gap-1 text-muted"><Lock class="w-4 h-4" /> Private to you — colleagues have their own shortlists.</p>
	</div>

	<ul class="space-y-3">
		{#each data.entries as entry (entry.id)}
			<li class="flex flex-col gap-3 rounded-lg border border-border bg-white p-4 md:flex-row md:items-center md:justify-between" data-candidate-id={entry.id}>
				{#if entry.available}
					<div>
						<a href="/dashboard/candidates/{entry.id}/" class="font-semibold text-black hover:text-primary">{entry.name}</a>
						<p class="text-sm text-muted">{entry.job_role || 'No target role'} · shortlisted {formatDate(entry.shortlisted_at)}{#if entry.note_count} · {entry.note_count} note{entry.note_count === 1 ? '' : 's'}{/if}</p>
					</div>
				{:else}
					<div>
						<p class="font-semibold text-muted">Candidate no longer available</p>
						<p class="text-sm text-muted">They withdrew their published resume. Shortlisted {formatDate(entry.shortlisted_at)}.</p>
					</div>
				{/if}
				<form method="POST" action="?/remove" use:enhance>
					<input type="hidden" name="candidate_id" value={entry.id} />
					<button type="submit" class="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-surface"><StarOff class="w-4 h-4" /> Remove</button>
				</form>
			</li>
		{:else}
			<li class="rounded-lg border border-border bg-white p-8 text-center text-muted">No shortlisted candidates yet.</li>
		{/each}
	</ul>
</div>
