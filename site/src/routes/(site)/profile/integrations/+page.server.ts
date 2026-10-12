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

function errorMessage(err: unknown, fallback: string) {
	return err instanceof ApiRequestError ? err.message : fallback;
}

function errorStatus(err: unknown) {
	return err instanceof ApiRequestError ? err.status : 500;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const notice = url.searchParams.get('rr');
	const errorCode = url.searchParams.get('rr_error');

	try {
		return { rr: await apiGet<RRLinkStatus>(fetch, '/integrations/rr/'), notice, errorCode };
	} catch (err) {
		return {
			rr: null,
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
