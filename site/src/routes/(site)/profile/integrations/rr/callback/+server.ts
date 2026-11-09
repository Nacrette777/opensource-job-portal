/**
 * Reactive Resume redirects the browser here after the consent screen.
 *
 * Under /profile, so hooks.server.ts has already required a session. The code
 * and state are handed straight to Django, which checks the state belongs to
 * this user before exchanging anything; the browser only ever sees a redirect.
 */

import { redirect, type RequestHandler } from '@sveltejs/kit';
import { apiPost, ApiRequestError } from '$lib/server/api';

const INTEGRATIONS = '/profile/integrations/';

export const GET: RequestHandler = async ({ url, fetch }) => {
	const params = url.searchParams;
	let errorCode = '';

	try {
		await apiPost(fetch, '/integrations/rr/callback/', {
			code: params.get('code') ?? '',
			state: params.get('state') ?? '',
			iss: params.get('iss') ?? '',
			error: params.get('error') ?? ''
		});
	} catch (err) {
		const data = err instanceof ApiRequestError ? (err.data as { code?: unknown } | null) : null;
		errorCode = typeof data?.code === 'string' ? data.code : 'callback_failed';
	}

	// Only a known code travels in the URL; the page maps it to a message.
	redirect(
		303,
		errorCode
			? `${INTEGRATIONS}?rr_error=${encodeURIComponent(errorCode)}`
			: `${INTEGRATIONS}?rr=connected`
	);
};
