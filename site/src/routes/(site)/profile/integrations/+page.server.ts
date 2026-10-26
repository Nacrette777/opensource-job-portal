/**
 * Profile → Integrations: link the job seeker's own Reactive Resume account.
 *
 * Everything OAuth-related happens in Django; this page only asks it for the
 * authorize URL (then sends the browser there) and shows the link status.
 * RR redirects back to ./rr/callback, which posts the code to Django.
 */

import { fail, redirect, type Actions } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiGet, apiPost, ApiRequestError } from '$lib/server/api';

export type RRLinkStatus = {
	configured: boolean;
	status: 'not_connected' | 'connected' | 'needs_reconnect';
	rr_email: string;
	rr_name: string;
	linked_at: string | null;
	rr_base_url: string;
};

export type RRDraft = {
	id: string;
	status: 'pending' | 'succeeded' | 'failed';
	external_resume_id: string;
	editor_url: string;
	warnings: string[];
	error_code: string;
	error: string;
	retryable: boolean;
	created_at: string;
};

// Failures that retrying the same request cannot fix (e.g. the draft was deleted in Reactive
// Resume); the next submit must use a fresh request id.
const FINAL_DRAFT_ERRORS = new Set(['rr_draft_deleted', 'rr_request_conflict']);

function errorCode(err: unknown) {
	if (!(err instanceof ApiRequestError) || !err.data || typeof err.data !== 'object') return '';
	const code = (err.data as { code?: unknown }).code;
	return typeof code === 'string' ? code : '';
}

function errorMessage(err: unknown, fallback: string) {
	return err instanceof ApiRequestError ? err.message : fallback;
}

function errorStatus(err: unknown) {
	return err instanceof ApiRequestError ? err.status : 500;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const notice = url.searchParams.get('rr');
	const errorCode = url.searchParams.get('rr_error');

	// A fresh idempotency key per page view: a double click or a resubmitted
	// form reuses it, so it can only ever create one draft.
	const draftRequestId = crypto.randomUUID();

	try {
		const [rr, drafts] = await Promise.all([
			apiGet<RRLinkStatus>(fetch, '/integrations/rr/'),
			apiGet<RRDraft[]>(fetch, '/integrations/rr/drafts/')
		]);
		return { rr, drafts, draftRequestId, notice, errorCode };
	} catch (err) {
		return {
			rr: null,
			drafts: [] as RRDraft[],
			draftRequestId,
			notice,
			errorCode,
			loadError: errorMessage(err, 'Could not load your Reactive Resume connection.')
		};
	}
};

export const actions: Actions = {
	connect: async ({ fetch }) => {
		let authorizationUrl: string;
		try {
			({ authorization_url: authorizationUrl } = await apiPost<{ authorization_url: string }>(
				fetch,
				'/integrations/rr/connect/'
			));
		} catch (err) {
			return fail(errorStatus(err), {
				error: errorMessage(err, 'Could not start connecting Reactive Resume.')
			});
		}
		// Outside the try: redirect() works by throwing.
		redirect(303, authorizationUrl);
	},

	disconnect: async ({ fetch }) => {
		try {
			await apiPost(fetch, '/integrations/rr/disconnect/');
		} catch (err) {
			return fail(errorStatus(err), {
				error: errorMessage(err, 'Could not disconnect Reactive Resume.')
			});
		}
		return { disconnected: true };
	},

	createDraft: async ({ request, fetch }) => {
		const requestId = (await request.formData()).get('request_id');
		if (typeof requestId !== 'string' || !requestId) {
			return fail(400, { error: 'Missing request id. Reload the page and try again.' });
		}
		try {
			const draft = await apiPost<RRDraft>(fetch, '/integrations/rr/drafts/create/', {
				request_id: requestId
			});
			return { draftCreated: true, draft };
		} catch (err) {
			// Hand the same id back so "try again" retries this request. RR may
			// already have created the draft; only the original id finds it
			// instead of creating a duplicate.
			const error = errorMessage(err, 'Could not create the resume draft.');
			if (FINAL_DRAFT_ERRORS.has(errorCode(err))) return fail(errorStatus(err), { error });
			return fail(errorStatus(err), { error, retryRequestId: requestId });
		}
	},

	check: async ({ fetch }) => {
		try {
			const result = await apiPost<{ ok: boolean; resume_count: number }>(
				fetch,
				'/integrations/rr/check/'
			);
			return { checked: true, resumeCount: result.resume_count };
		} catch (err) {
			return fail(errorStatus(err), {
				error: errorMessage(err, 'Could not reach your Reactive Resume account.')
			});
		}
	}
};
