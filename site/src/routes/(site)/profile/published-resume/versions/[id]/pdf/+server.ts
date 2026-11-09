/**
 * Stream one of the job seeker's own published PDFs from Django.
 *
 * Under /profile, so hooks.server.ts requires a session and adds the bearer
 * token; Django checks the version belongs to this user.
 */

import { error, type RequestHandler } from '@sveltejs/kit';
import { API_BASE_URL } from '$lib/config/env';

export const GET: RequestHandler = async ({ params, fetch }) => {
	if (!/^[0-9a-f-]{36}$/i.test(params.id ?? '')) error(404, 'Not found');

	const upstream = await fetch(
		`${API_BASE_URL}/integrations/publication/versions/${params.id}/pdf/`
	);
	if (!upstream.ok || !upstream.body) {
		// Pass on refusals as they are; only real upstream failures become 502.
		error([401, 403, 404].includes(upstream.status) ? upstream.status : 502, 'PDF unavailable');
	}

	return new Response(upstream.body, {
		status: 200,
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition':
				upstream.headers.get('content-disposition') ?? `attachment; filename="resume-${params.id}.pdf"`,
			'Cache-Control': 'private, no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
