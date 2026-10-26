<script lang="ts">
	import { FileCheck2, Download, Send, Eye, EyeOff, AlertTriangle, CheckCircle2, Link2 } from '@lucide/svelte';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let busy = $state('');
	let pub = $derived(data.publication);
	let current = $derived(pub?.current ?? null);

	const formatDate = (value: string | null | undefined) =>
		value ? new Date(value).toLocaleString() : '';
	const formatSize = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`;
	const pdfHref = (id: string) => `/profile/published-resume/versions/${id}/pdf/`;
	const previewHref = (id: string) => `/profile/published-resume/preview/${id}/pdf/`;

	const PUBLISH_CONFIRM =
		'Recruiters will be able to download this PDF exactly as it is, including any phone number, email or address in it. Publish it?';
	const WITHDRAW_CONFIRM =
		'Withdraw your resume? Recruiters will no longer find it. Copies they have already downloaded cannot be recalled.';
</script>

<svelte:head>
	<title>Published resume - Profile - PeelJobs</title>
	<meta name="description" content="Choose which resume recruiters can see" />
</svelte:head>

<div class="mb-6 animate-fade-in-up" style="opacity: 0;">
	<div class="flex items-center gap-3">
		<div class="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
			<FileCheck2 size={20} class="text-primary-600" />
		</div>
		<div>
			<h2 class="text-xl lg:text-2xl font-bold text-gray-900">Published resume</h2>
			<p class="text-sm text-gray-600">Choose which resume recruiters can see</p>
		</div>
	</div>
</div>

{#if form && 'error' in form && form.error}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-error-600/30 bg-error-50 p-4 text-sm text-error-600" role="alert">
		<AlertTriangle size={18} class="mt-0.5 shrink-0" />
		<span>{form.error}</span>
	</div>
{:else if form && 'published' in form}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-success-600/30 bg-success-50 p-4 text-sm text-success-600" role="status">
		<CheckCircle2 size={18} class="mt-0.5 shrink-0" />
		<span>Published. Recruiters now see this version.</span>
	</div>
{:else if form && 'withdrawn' in form}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-success-600/30 bg-success-50 p-4 text-sm text-success-600" role="status">
		<CheckCircle2 size={18} class="mt-0.5 shrink-0" />
		<span>Withdrawn. Recruiters can no longer find or download your resume.</span>
	</div>
{/if}

{#if data.loadError}
	<p class="text-sm text-error-600">{data.loadError}</p>
{:else}
	<!-- Current publication -->
	<div class="bg-white rounded-2xl elevation-1 border border-gray-100 p-6 lg:p-8 animate-fade-in-up" style="opacity: 0; animation-delay: 100ms;">
		<h3 class="text-lg font-semibold text-gray-900">What recruiters see</h3>
		{#if current}
			<div class="mt-4 rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm">
				<p class="font-medium text-gray-900">{current.title || 'Untitled resume'}</p>
				<p class="mt-1 text-gray-600">
					Published {formatDate(pub?.published_at)} · resume as saved {formatDate(current.rr_updated_at)} ·
					PDF {formatSize(current.pdf_size)}
				</p>
			</div>
			<div class="mt-4 flex flex-wrap gap-3">
				<a href={pdfHref(current.id)} class="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50">
					<Download size={16} /> Download published PDF
				</a>
				<form method="POST" action="?/withdraw" onsubmit={(e) => { if (!confirm(WITHDRAW_CONFIRM)) e.preventDefault(); else busy = 'withdraw'; }}>
					<button type="submit" disabled={busy !== ''} class="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-error-600/30 text-sm font-medium text-error-600 hover:bg-error-50 disabled:opacity-60">
						<EyeOff size={16} /> {busy === 'withdraw' ? 'Withdrawing…' : 'Withdraw'}
					</button>
				</form>
			</div>
			<p class="mt-3 text-xs text-gray-500">
				Editing this resume in Reactive Resume does not change what recruiters see until you publish
				again. Withdrawing stops recruiters finding or downloading it from then on; copies they have
				already downloaded cannot be recalled.
			</p>
		{:else}
			<p class="mt-2 text-sm text-gray-600">
				Nothing is published. Recruiters cannot find you in candidate search until you publish a resume.
			</p>
		{/if}
	</div>

	<!-- Choose a resume to publish -->
	<div class="mt-6 bg-white rounded-2xl elevation-1 border border-gray-100 p-6 lg:p-8 animate-fade-in-up" style="opacity: 0; animation-delay: 150ms;">
		<h3 class="text-lg font-semibold text-gray-900">Publish a resume</h3>
		{#if data.rr?.status !== 'connected'}
			<p class="mt-2 text-sm text-gray-600">
				Connect your Reactive Resume account first.
			</p>
			<a href="/profile/integrations/" class="mt-4 inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-full font-medium hover:bg-primary-700 text-sm">
				<Link2 size={16} /> Go to Integrations
			</a>
		{:else if data.resumesError}
			<p class="mt-2 text-sm text-error-600">{data.resumesError}</p>
		{:else if data.resumes.length === 0}
			<p class="mt-2 text-sm text-gray-600">
				Your Reactive Resume account has no resumes yet. Create a draft from Integrations first.
			</p>
		{:else}
			<p class="mt-1 text-sm text-gray-600">
				Publishing saves a copy of the resume as it is now (data and PDF). Later edits stay private
				until you publish again.
			</p>
			<div class="mt-4 flex items-start gap-3 rounded-xl border border-warning-500/20 bg-warning-light p-4 text-sm text-warning-600" role="note">
				<AlertTriangle size={18} class="mt-0.5 shrink-0" />
				<span>
					Recruiters can download the PDF exactly as it is, including any phone number, email or
					address written in it. Recruiter pages hide your phone number and address, but the PDF is
					never changed. Preview it first, and remove anything you do not want to share in Reactive
					Resume before publishing.
				</span>
			</div>
			<ul class="mt-4 divide-y divide-gray-100 rounded-xl border border-gray-100">
				{#each data.resumes as resume (resume.id)}
					<li class="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
						<span>
							<span class="font-medium text-gray-900">{resume.name || 'Untitled resume'}</span>
							<span class="block text-xs text-gray-500">Last saved {formatDate(resume.updated_at)}{#if current?.external_resume_id === resume.id} · currently published{/if}</span>
						</span>
						<span class="flex flex-wrap items-center gap-2">
							<a href={previewHref(resume.id)} target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50">
								<Eye size={14} /> Preview PDF
							</a>
							<form method="POST" action="?/publish" onsubmit={(e) => { if (!confirm(PUBLISH_CONFIRM)) e.preventDefault(); else busy = resume.id; }}>
								<input type="hidden" name="external_resume_id" value={resume.id} />
								<button type="submit" disabled={busy !== ''} class="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-full text-xs font-medium hover:bg-primary-700 disabled:opacity-60">
									<Send size={14} /> {busy === resume.id ? 'Publishing…' : current?.external_resume_id === resume.id ? 'Publish again' : 'Publish'}
								</button>
							</form>
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	{#if pub?.history.length}
		<div class="mt-6 bg-white rounded-2xl elevation-1 border border-gray-100 p-6 lg:p-8 animate-fade-in-up" style="opacity: 0; animation-delay: 200ms;">
			<h3 class="text-lg font-semibold text-gray-900">Published versions</h3>
			<ul class="mt-4 divide-y divide-gray-100 rounded-xl border border-gray-100">
				{#each pub.history as version (version.id)}
					<li class="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
						<span class="text-gray-700">
							{version.title || 'Untitled resume'} · {formatDate(version.created_at)}
							{#if version.is_current}<span class="ml-2 rounded-full bg-success-50 px-2 py-0.5 text-xs text-success-600">current</span>{/if}
						</span>
						<a href={pdfHref(version.id)} class="inline-flex items-center gap-1 py-2 text-primary-600 hover:underline">
							<Download size={14} /> PDF
						</a>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
{/if}
