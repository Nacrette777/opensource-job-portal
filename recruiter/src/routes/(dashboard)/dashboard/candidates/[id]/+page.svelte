<script lang="ts">
	import { ArrowLeft, Download, Star, StarOff, Mail, Briefcase, GraduationCap, FolderOpen, StickyNote, Trash2, Pencil, XCircle, Lock } from '@lucide/svelte';
	import { enhance } from '$app/forms';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let c = $derived(data.candidate);
	let editing = $state<number | null>(null);
	let draft = $state('');
	// Disables Save note while a note is being saved, so a double click cannot save it twice.
	let savingNote = $state(false);

	const formatDate = (value: string | null) => (value ? new Date(value).toLocaleDateString() : '');
	const span = (from: string | null, to: string | null, current = false) =>
		[formatDate(from), current ? 'present' : formatDate(to)].filter(Boolean).join(' – ');
</script>

<svelte:head>
	<title>{c.name} - Candidates - PeelJobs Recruiter</title>
</svelte:head>

<div class="max-w-5xl space-y-6">
	<a href="/dashboard/candidates/" class="inline-flex items-center gap-1 py-2 text-sm text-muted hover:text-black"><ArrowLeft class="w-4 h-4" /> Back to candidates</a>

	{#if form && 'error' in form && form.error}
		<div class="bg-error-light border border-error/30 rounded-lg p-4 flex items-start gap-3" role="alert">
			<XCircle class="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
			<p class="text-sm text-error">{form.error}</p>
		</div>
	{/if}

	<div class="rounded-lg border border-border bg-white p-6">
		<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
			<div>
				<h1 class="text-2xl font-bold text-black">{c.name}</h1>
				<p class="text-muted">{c.job_role || 'No target role'}</p>
				{#if c.email}
					<p class="mt-1 inline-flex items-center gap-1 text-sm text-black"><Mail class="w-4 h-4" /> {c.email}</p>
				{/if}
			</div>
			<div class="flex flex-wrap gap-2">
				<a href="/dashboard/candidates/{c.id}/resume.pdf" class="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover">
					<Download class="w-4 h-4" /> Download published resume
				</a>
				<form method="POST" action="?/shortlist" use:enhance>
					{#if c.shortlisted}<input type="hidden" name="remove" value="1" />{/if}
					<button type="submit" class="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm hover:bg-surface">
						{#if c.shortlisted}<StarOff class="w-4 h-4" /> Remove from shortlist{:else}<Star class="w-4 h-4" /> Add to shortlist{/if}
					</button>
				</form>
			</div>
		</div>
		<p class="mt-3 text-xs text-muted">
			Published resume “{c.resume.title}” · {formatDate(c.resume.published_at)} · {Math.max(1, Math.round(c.resume.pdf_size / 1024))} KB
		</p>
		{#if c.summary}<p class="mt-4 whitespace-pre-line text-sm text-black">{c.summary}</p>{/if}
	</div>

	<div class="grid gap-6 lg:grid-cols-3">
		<div class="space-y-6 lg:col-span-2">
			<section class="rounded-lg border border-border bg-white p-6">
				<h2 class="flex items-center gap-2 font-semibold text-black"><GraduationCap class="w-5 h-5" /> Education</h2>
				<ul class="mt-3 space-y-3">
					{#each c.education as e}
						<li class="text-sm">
							<p class="font-medium text-black">{e.qualification} · {e.specialization}</p>
							<p class="text-muted">{e.institute} · {span(e.from_date, e.to_date, e.current)}{#if e.score} · {e.score}{/if}</p>
						</li>
					{:else}<li class="text-sm text-muted">None listed.</li>{/each}
				</ul>
			</section>
			<section class="rounded-lg border border-border bg-white p-6">
				<h2 class="flex items-center gap-2 font-semibold text-black"><Briefcase class="w-5 h-5" /> Experience</h2>
				<ul class="mt-3 space-y-3">
					{#each c.employment as e}
						<li class="text-sm">
							<p class="font-medium text-black">{e.designation} · {e.company}</p>
							<p class="text-muted">{span(e.from_date, e.to_date, e.current)}</p>
							{#if e.description}<p class="mt-1 whitespace-pre-line text-black">{e.description}</p>{/if}
						</li>
					{:else}<li class="text-sm text-muted">None listed.</li>{/each}
				</ul>
			</section>
			<section class="rounded-lg border border-border bg-white p-6">
				<h2 class="flex items-center gap-2 font-semibold text-black"><FolderOpen class="w-5 h-5" /> Projects</h2>
				<ul class="mt-3 space-y-3">
					{#each c.projects as p}
						<li class="text-sm">
							<p class="font-medium text-black">{p.name}</p>
							<p class="text-muted">{[p.role, p.size ? `team of ${p.size}` : '', span(p.from_date, p.to_date)].filter(Boolean).join(' · ')}</p>
							{#if p.description}<p class="mt-1 whitespace-pre-line text-black">{p.description}</p>{/if}
							{#if p.skills.length}<p class="mt-1 text-xs text-muted">{p.skills.join(', ')}</p>{/if}
						</li>
					{:else}<li class="text-sm text-muted">None listed.</li>{/each}
				</ul>
			</section>
		</div>

		<div class="space-y-6">
			<section class="rounded-lg border border-border bg-white p-6">
				<h2 class="font-semibold text-black">Skills</h2>
				<ul class="mt-3 flex flex-wrap gap-2">
					{#each c.skills as s}
						<li class="rounded-full bg-surface px-3 py-1 text-xs text-black">{s.name}{#if s.level} · {s.level}{/if}</li>
					{:else}<li class="text-sm text-muted">None listed.</li>{/each}
				</ul>
			</section>

			<section class="rounded-lg border border-border bg-white p-6">
				<h2 class="flex items-center gap-2 font-semibold text-black"><StickyNote class="w-5 h-5" /> My notes</h2>
				<p class="mt-1 flex items-center gap-1 text-xs text-muted"><Lock class="w-3 h-3" /> Only you can see these notes.</p>
				<form method="POST" action="?/addNote" use:enhance={() => { savingNote = true; return async ({ update }) => { await update(); savingNote = false; }; }} class="mt-3 space-y-2">
					<textarea name="body" rows="3" maxlength="5000" required aria-label="Private note" placeholder="Add a private note" class="w-full rounded-lg border border-border px-3 py-2 text-sm"></textarea>
					<button type="submit" disabled={savingNote} class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-60">{savingNote ? 'Saving…' : 'Save note'}</button>
				</form>
				<ul class="mt-4 space-y-3">
					{#each data.notes as note (note.id)}
						<li class="rounded-lg bg-surface p-3 text-sm" data-note-id={note.id}>
							{#if editing === note.id}
								<form method="POST" action="?/editNote" use:enhance={() => async ({ update }) => { await update(); editing = null; }} class="space-y-2">
									<input type="hidden" name="note_id" value={note.id} />
									<textarea name="body" rows="3" maxlength="5000" aria-label="Edit note" bind:value={draft} class="w-full rounded-lg border border-border px-3 py-2"></textarea>
									<div class="flex gap-2">
										<button type="submit" class="rounded-lg bg-primary px-3 py-1 text-xs font-medium text-white">Save</button>
										<button type="button" onclick={() => (editing = null)} class="rounded-lg border border-border px-3 py-1 text-xs">Cancel</button>
									</div>
								</form>
							{:else}
								<p class="whitespace-pre-line text-black">{note.body}</p>
								<div class="mt-2 flex items-center justify-between text-xs text-muted">
									<span>{formatDate(note.updated_at)}</span>
									<span class="flex gap-2">
										<button type="button" aria-label="Edit note" class="rounded p-1.5 hover:bg-white" onclick={() => { editing = note.id; draft = note.body; }}><Pencil class="w-4 h-4" /></button>
										<form method="POST" action="?/deleteNote" use:enhance>
											<input type="hidden" name="note_id" value={note.id} />
											<button type="submit" aria-label="Delete note" class="rounded p-1.5 hover:bg-white"><Trash2 class="w-4 h-4" /></button>
										</form>
									</span>
								</div>
							{/if}
						</li>
					{/each}
				</ul>
			</section>
		</div>
	</div>
</div>
