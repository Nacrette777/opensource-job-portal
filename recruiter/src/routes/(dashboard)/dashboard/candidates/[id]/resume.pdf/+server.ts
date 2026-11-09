/**
 * Stream a candidate's currently published resume PDF from Django. Django
 * re-checks that the caller is a recruiter and that the resume is still
 * published, so a withdrawn resume returns 404 even from an old link.
 */

import { error, redirect, type RequestHandler } from '@sveltejs/kit';
import { API_BASE_URL } from '$lib/config/env';

export const GET: RequestHandler = async ({ params, fetch, url }) => {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id < 1) error(404, 'Not found');

	const upstream = await fetch(`${API_BASE_URL}/recruiter/candidates/${id}/resume.pdf`);
	if (upstream.status === 401) redirect(302, `/login?redirect=${encodeURIComponent(url.pathname)}`);
	if (!upstream.ok || !upstream.body) error(upstream.status === 404 ? 404 : upstream.status, 'Resume unavailable');

	return new Response(upstream.body, {
		headers: {
			'Content-Type': 'application/pdf',
			'Content-Disposition': upstream.headers.get('content-disposition') ?? `attachment; filename="candidate-${id}-resume.pdf"`,
			'Cache-Control': 'private, no-store',
			'X-Content-Type-Options': 'nosniff'
		}
	});
};
