/**
 * Show the PDF Reactive Resume renders for one of the job seeker's resumes right
 * now, before they publish it. Django fetches it with the job seeker's own RR
 * token and stores nothing.
 *
 * Under /profile, so hooks.server.ts requires a session and adds the bearer token.
 */

import { error, type RequestHandler } from '@sveltejs/kit';
import { API_BASE_URL } from '$lib/config/env';

export const GET: RequestHandler = async ({ params, fetch }) => {
	if (!/^[0-9a-z-]{1,64}$/i.test(params.id ?? '')) error(404, 'Not found');

	const upstream = await fetch(
		`${API_BASE_URL}/integrations/publication/preview/${params.id}/pdf/`
	);
	if (!upstream.ok || !upstream.body) {
		const body = await upstream.json().catch(() => null);
		error([401, 403, 404, 409].includes(upstream.status) ? upstream.status : 502, body?.error ?? 'Preview unavailable');
	}

	return new Response(upstream.body, {
		status: 200,
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition': 'inline; filename="resume-preview.pdf"',
			'Cache-Control': 'private, no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
