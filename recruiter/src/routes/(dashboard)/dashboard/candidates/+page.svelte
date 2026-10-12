<script lang="ts">
	import { UserSearch, Star, StarOff, GraduationCap, Search, StickyNote, ChevronLeft, ChevronRight, XCircle } from '@lucide/svelte';
	import { enhance } from '$app/forms';
	import { page } from '$app/stores';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let selectedSkills = $derived(new Set(data.selected.skills));
	let currentPage = $derived(Number($page.url.searchParams.get('page') || '1'));

	function pageHref(n: number) {
		const params = new URLSearchParams($page.url.searchParams);
		params.set('page', String(n));
		return `?${params.toString()}`;
	}
	const formatDate = (value: string) => new Date(value).toLocaleDateString();
</script>

<svelte:head>
	<title>Candidates - PeelJobs Recruiter</title>
</svelte:head>

<div class="max-w-7xl space-y-6">
	<div class="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
		<div>
			<h1 class="text-2xl md:text-3xl font-bold text-black flex items-center gap-2">
				<UserSearch class="w-8 h-8" />
				Candidates
			</h1>
			<p class="text-muted mt-1">Graduates who have published a resume. Withdrawn resumes disappear immediately.</p>
		</div>
		<a href="/dashboard/candidates/shortlist/" class="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium text-black hover:bg-surface">
			<Star class="w-4 h-4" /> My shortlist
		</a>
	</div>

	{#if form?.error || data.searchError}
		<div class="bg-error-light border border-error/30 rounded-lg p-4 flex items-start gap-3" role="alert">
			<XCircle class="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
			<p class="text-sm text-error">{form?.error || data.searchError}</p>
		</div>
	{/if}

	<form method="GET" class="rounded-lg border border-border bg-white p-4 space-y-4">
		<div class="grid gap-4 md:grid-cols-4">
			<label class="md:col-span-4 block text-sm">
				<span class="font-medium text-black">Keyword</span>
				<div class="relative mt-1">
					<Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
					<input name="q" value={data.selected.q} placeholder="Name, target role, summary, skill or project" class="w-full rounded-lg border border-border py-2 pl-9 pr-3" />
				</div>
			</label>
			<label class="block text-sm">
				<span class="font-medium text-black">Qualification</span>
				<select name="qualification" class="mt-1 w-full rounded-lg border border-border px-3 py-2">
					<option value="">Any</option>
					{#each data.filters.qualifications as q}
						<option value={q.id} selected={$page.url.searchParams.get('qualification') === String(q.id)}>{q.name}</option>
					{/each}
				</select>
			</label>
			<label class="block text-sm md:col-span-2">
				<span class="font-medium text-black">Degree</span>
				<select name="degree" class="mt-1 w-full rounded-lg border border-border px-3 py-2">
					<option value="">Any</option>
					{#each data.filters.degrees as d}
						<option value={d.id} selected={$page.url.searchParams.get('degree') === String(d.id)}>{d.name}</option>
					{/each}
				</select>
			</label>
			<label class="block text-sm">
				<span class="font-medium text-black">Graduation year</span>
				<select name="graduation_year" class="mt-1 w-full rounded-lg border border-border px-3 py-2">
					<option value="">Any</option>
					{#each data.filters.graduation_years as y}
						<option value={y} selected={$page.url.searchParams.get('graduation_year') === String(y)}>{y}</option>
					{/each}
				</select>
			</label>
		</div>
		{#if data.filters.skills.length}
			<fieldset>
				<legend class="text-sm font-medium text-black">Skills <span class="font-normal text-muted">(candidates must have all selected skills)</span></legend>
				<div class="mt-2 flex flex-wrap gap-2">
					{#each data.filters.skills as s}
						<label class="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm">
							<input type="checkbox" name="skill" value={s.id} checked={selectedSkills.has(String(s.id))} />
							{s.name}
						</label>
					{/each}
				</div>
			</fieldset>
		{/if}
		<p class="text-xs text-muted">Qualification, degree and graduation year must all match the same education entry.</p>
		<div class="flex gap-3">
			<button type="submit" class="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-hover">Search</button>
			<a href="/dashboard/candidates/" class="rounded-lg border border-border px-5 py-2 text-sm font-medium text-black hover:bg-surface">Clear</a>
		</div>
	</form>

	<p class="text-sm text-muted" data-testid="result-count">{data.results.count} candidate{data.results.count === 1 ? '' : 's'}</p>

	<ul class="space-y-3">
		{#each data.results.results as c (c.id)}
			<li class="rounded-lg border border-border bg-white p-4" data-candidate-id={c.id}>
				<div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
					<div class="min-w-0">
						<a href="/dashboard/candidates/{c.id}/" class="text-lg font-semibold text-black hover:text-primary">{c.name}</a>
						<p class="text-sm text-muted">{c.job_role || 'No target role'}</p>
						{#if c.latest_education}
							<p class="mt-1 flex items-center gap-1 text-sm text-black">
								<GraduationCap class="w-4 h-4" />
								{c.latest_education.qualification} · {c.latest_education.specialization} · {c.latest_education.institute}{#if c.graduation_year} · {c.graduation_year}{/if}
							</p>
						{/if}
						{#if c.summary}<p class="mt-2 text-sm text-black line-clamp-2">{c.summary}</p>{/if}
						<div class="mt-2 flex flex-wrap gap-1">
							{#each c.skills as skill}
								<span class="rounded-full bg-surface px-2 py-0.5 text-xs text-black">{skill}</span>
							{/each}
						</div>
					</div>
					<div class="flex shrink-0 items-center gap-2">
						{#if c.note_count}
							<span class="inline-flex items-center gap-1 text-xs text-muted"><StickyNote class="w-3 h-3" /> {c.note_count}</span>
						{/if}
						<span class="text-xs text-muted">Published {formatDate(c.published_at)}</span>
						<form method="POST" action="?/shortlist" use:enhance>
							<input type="hidden" name="candidate_id" value={c.id} />
							{#if c.shortlisted}<input type="hidden" name="remove" value="1" />{/if}
							<button type="submit" class="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-surface" aria-label={c.shortlisted ? 'Remove from shortlist' : 'Add to shortlist'}>
								{#if c.shortlisted}<StarOff class="w-4 h-4" /> Shortlisted{:else}<Star class="w-4 h-4" /> Shortlist{/if}
							</button>
						</form>
					</div>
				</div>
			</li>
		{:else}
			<li class="rounded-lg border border-border bg-white p-8 text-center text-muted">No candidates match these filters.</li>
		{/each}
	</ul>

	{#if data.results.previous || data.results.next}
		<div class="flex items-center justify-between">
			{#if data.results.previous}
				<a href={pageHref(currentPage - 1)} class="inline-flex items-center gap-1 text-sm text-primary"><ChevronLeft class="w-4 h-4" /> Previous</a>
			{:else}<span></span>{/if}
			{#if data.results.next}
				<a href={pageHref(currentPage + 1)} class="inline-flex items-center gap-1 text-sm text-primary">Next <ChevronRight class="w-4 h-4" /></a>
			{/if}
		</div>
	{/if}
</div>
