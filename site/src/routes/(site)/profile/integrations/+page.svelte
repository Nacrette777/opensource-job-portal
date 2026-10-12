<script lang="ts">
	import {
		Link2,
		CheckCircle2,
		AlertTriangle,
		ExternalLink,
		RefreshCw,
		Unlink,
		FilePlus2
	} from '@lucide/svelte';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	// Codes come from the callback redirect; only known ones get specific text.
	const CALLBACK_ERRORS: Record<string, string> = {
		authorization_denied: 'You did not allow access in Reactive Resume, so nothing was connected.',
		authorization_expired: 'The connection request expired. Please try again.',
		invalid_state: 'That connection response did not match a request from your account. Please try again.',
		invalid_issuer: 'The connection response came from an unexpected server and was ignored.',
		rr_account_already_linked:
			'That Reactive Resume account is already linked to another GradBridge user.',
		token_exchange_failed: 'Reactive Resume did not complete the connection. Please try again.',
		rr_unreachable: 'Reactive Resume could not be reached. Please try again later.'
	};

	let callbackError = $derived(
		data.errorCode
			? (CALLBACK_ERRORS[data.errorCode] ?? 'Connecting Reactive Resume failed. Please try again.')
			: ''
	);
	let rr = $derived(data.rr);

	let creatingDraft = $state(false);

	// After a failed create, keep that request's id so the button retries it.
	let retryRequestId = $derived(
		form && 'retryRequestId' in form && typeof form.retryRequestId === 'string'
			? form.retryRequestId
			: ''
	);
	let retrying = $derived(Boolean(retryRequestId));
	let draftRequestId = $derived(retryRequestId || data.draftRequestId);

	function formatDate(value: string) {
		return new Date(value).toLocaleString();
	}
</script>

<svelte:head>
	<title>Integrations - Profile - PeelJobs</title>
	<meta name="description" content="Connect your Reactive Resume account" />
</svelte:head>

<!-- Header -->
<div class="mb-6 animate-fade-in-up" style="opacity: 0;">
	<div class="flex items-center gap-3">
		<div class="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
			<Link2 size={20} class="text-primary-600" />
		</div>
		<div>
			<h2 class="text-xl lg:text-2xl font-bold text-gray-900">Integrations</h2>
			<p class="text-sm text-gray-600">Connect your Reactive Resume account</p>
		</div>
	</div>
</div>

{#if data.notice === 'connected' && rr?.status === 'connected'}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-success-600/30 bg-success-50 p-4 text-sm text-success-600" role="status">
		<CheckCircle2 size={18} class="mt-0.5 shrink-0" />
		<span>Reactive Resume is connected.</span>
	</div>
{/if}

{#if callbackError}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-error-600/30 bg-error-50 p-4 text-sm text-error-600" role="alert">
		<AlertTriangle size={18} class="mt-0.5 shrink-0" />
		<span>{callbackError}</span>
	</div>
{/if}

{#if form?.error}
	<div class="mb-4 flex items-start gap-3 rounded-xl border border-error-600/30 bg-error-50 p-4 text-sm text-error-600" role="alert">
		<AlertTriangle size={18} class="mt-0.5 shrink-0" />
		<span>{form.error}</span>
	</div>
{/if}

<div
	class="bg-white rounded-2xl elevation-1 border border-gray-100 p-6 lg:p-8 animate-fade-in-up"
	style="opacity: 0; animation-delay: 100ms;"
>
	<h3 class="text-lg font-semibold text-gray-900">Reactive Resume</h3>
	<p class="mt-1 text-sm text-gray-600 max-w-2xl">
		Connect your own Reactive Resume account so GradBridge can create resume drafts there for
		you. You sign in to Reactive Resume and approve access yourself; you can disconnect at any
		time.
	</p>

	{#if data.loadError}
		<p class="mt-6 text-sm text-error-600">{data.loadError}</p>
	{:else if rr && !rr.configured}
		<p class="mt-6 text-sm text-gray-600">
			The Reactive Resume integration is not available on this server yet.
		</p>
	{:else if rr}
		<div class="mt-6 rounded-xl border border-gray-100 bg-gray-50 p-4">
			{#if rr.status === 'connected'}
				<p class="flex items-center gap-2 text-sm font-medium text-success-600">
					<CheckCircle2 size={16} /> Connected
				</p>
				<p class="mt-1 text-sm text-gray-700">
					{rr.rr_name ? `${rr.rr_name} · ` : ''}{rr.rr_email}
				</p>
				{#if rr.linked_at}
					<p class="mt-1 text-xs text-gray-500">
						Since {new Date(rr.linked_at).toLocaleString()}
					</p>
				{/if}
			{:else if rr.status === 'needs_reconnect'}
				<p class="flex items-center gap-2 text-sm font-medium text-warning-600">
					<AlertTriangle size={16} /> Needs reconnecting
				</p>
				<p class="mt-1 text-sm text-gray-700">
					Reactive Resume no longer accepts the previous authorization.
				</p>
			{:else}
				<p class="text-sm font-medium text-gray-700">Not connected</p>
			{/if}
		</div>

		{#if form?.checked}
			<p class="mt-4 text-sm text-success-600" role="status">
				Connection works — your Reactive Resume account has {form.resumeCount}
				{form.resumeCount === 1 ? 'resume' : 'resumes'}.
			</p>
		{/if}

		<div class="mt-6 flex flex-wrap gap-3">
			{#if rr.status === 'connected'}
				<form method="POST" action="?/check">
					<button
						type="submit"
						class="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
					>
						<RefreshCw size={16} /> Check connection
					</button>
				</form>
				<a
					href={rr.rr_base_url}
					target="_blank"
					rel="noopener noreferrer"
					class="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
				>
					<ExternalLink size={16} /> Open Reactive Resume
				</a>
				<form method="POST" action="?/disconnect">
					<button
						type="submit"
						class="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-error-600/30 text-sm font-medium text-error-600 hover:bg-error-50 transition-colors"
					>
						<Unlink size={16} /> Disconnect
					</button>
				</form>
			{:else}
				<!-- Plain POST: the action redirects the browser to Reactive Resume. -->
				<form method="POST" action="?/connect">
					<button
						type="submit"
						class="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-full font-medium hover:bg-primary-700 transition-colors elevation-1 text-sm"
					>
						<Link2 size={16} />
						{rr.status === 'needs_reconnect' ? 'Reconnect Reactive Resume' : 'Connect Reactive Resume'}
					</button>
				</form>
			{/if}
		</div>
	{/if}
</div>

{#if rr?.configured && rr.status === 'connected'}
	<div
		class="mt-6 bg-white rounded-2xl elevation-1 border border-gray-100 p-6 lg:p-8 animate-fade-in-up"
		style="opacity: 0; animation-delay: 150ms;"
	>
		<h3 class="text-lg font-semibold text-gray-900">Resume drafts</h3>
		<p class="mt-1 text-sm text-gray-600 max-w-2xl">
			Create a new draft in your Reactive Resume account from the profile you have saved here.
			Each draft is separate: later profile changes do not update drafts you already created or
			edited.
		</p>

		{#if form?.draftCreated && form.draft}
			<div class="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-success-600/30 bg-success-50 p-4 text-sm text-success-600" role="status">
				<CheckCircle2 size={18} class="shrink-0" />
				<span>Draft created.</span>
				<a href={form.draft.editor_url} target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 font-medium underline">
					Open it in Reactive Resume <ExternalLink size={14} />
				</a>
			</div>
			{#if form.draft.warnings.length}
				<ul class="mt-2 list-disc pl-6 text-xs text-gray-600">
					{#each form.draft.warnings as warning}
						<li>{warning}</li>
					{/each}
				</ul>
			{/if}
		{/if}

		<!-- The hidden request id is the idempotency key: resubmitting this form returns the same draft.
		     After a failure it stays the failed request's id, so trying again cannot create a duplicate. -->
		<form method="POST" action="?/createDraft" class="mt-6" onsubmit={() => (creatingDraft = true)}>
			<input type="hidden" name="request_id" value={draftRequestId} />
			<button
				type="submit"
				disabled={creatingDraft}
				class="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-full font-medium hover:bg-primary-700 transition-colors elevation-1 text-sm disabled:opacity-60"
			>
				{#if retrying}
					<RefreshCw size={16} />
					{creatingDraft ? 'Retrying…' : 'Retry this request'}
				{:else}
					<FilePlus2 size={16} />
					{creatingDraft ? 'Creating draft…' : 'Create resume draft'}
				{/if}
			</button>
		</form>
		{#if retrying}
			<p class="mt-2 text-xs text-gray-500">
				Retrying reuses the same request, so if Reactive Resume already created the draft you get
				that draft back instead of a duplicate.
			</p>
		{/if}

		{#if data.drafts?.length}
			<ul class="mt-6 divide-y divide-gray-100 rounded-xl border border-gray-100">
				{#each data.drafts as draft (draft.id)}
					<li class="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
						<span class="text-gray-700">{formatDate(draft.created_at)}</span>
						{#if draft.status === 'succeeded'}
							<a href={draft.editor_url} target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 font-medium text-primary-600 hover:underline">
								Open draft <ExternalLink size={14} />
							</a>
						{:else}
							<span class="flex flex-wrap items-center gap-3">
								{#if draft.status === 'failed'}
									<span class="text-error-600">Failed: {draft.error}</span>
								{:else}
									<span class="text-gray-500">In progress</span>
								{/if}
								<!-- Same request id: returns the draft if RR already made it. -->
								<form method="POST" action="?/createDraft">
									<input type="hidden" name="request_id" value={draft.id} />
									<button
										type="submit"
										class="inline-flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
									>
										<RefreshCw size={12} /> Retry
									</button>
								</form>
							</span>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}
