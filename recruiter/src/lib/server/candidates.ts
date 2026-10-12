/**
 * Server-side calls to the GradBridge candidate API (Django /recruiter/candidates/).
 * `fetch` must be the request-scoped one: hooks.server.ts adds the JWT.
 */

import { error, redirect } from '@sveltejs/kit';
import { API_BASE_URL } from '$lib/config/env';

type Fetch = typeof fetch;

export class CandidateApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
	}
}

export async function candidateApi<T>(
	fetchFn: Fetch,
	path: string,
	init: RequestInit = {},
	currentPath = '/dashboard/candidates/'
): Promise<T> {
	const headers = new Headers(init.headers);
	if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
	const response = await fetchFn(`${API_BASE_URL}/recruiter/candidates/${path}`, { ...init, headers });

	if (response.status === 401) redirect(302, `/login?redirect=${encodeURIComponent(currentPath)}`);
	if (response.status === 204) return undefined as T;

	const body = await response.json().catch(() => null);
	if (!response.ok) {
		const message =
			(body && (body.error || body.detail || Object.values(body).flat().join(' '))) ||
			`Request failed (${response.status})`;
		throw new CandidateApiError(String(message), response.status);
	}
	return body as T;
}

/** Turn a 404/403 from Django into the matching page error. */
export function pageError(err: unknown): never {
	if (err instanceof CandidateApiError) {
		if (err.status === 404) error(404, 'This candidate is not available.');
		if (err.status === 403) error(403, 'Only recruiters can view candidates.');
		error(err.status, err.message);
	}
	throw err;
}

export type CandidateListItem = {
	id: number;
	name: string;
	job_role: string;
	summary: string;
	skills: string[];
	latest_education: { qualification: string; specialization: string; institute: string } | null;
	graduation_year: number | null;
	published_at: string;
	shortlisted: boolean;
	note_count: number;
};

export type CandidateFilters = {
	skills: { id: number; name: string }[];
	qualifications: { id: number; name: string }[];
	degrees: { id: number; name: string; qualification_id: number }[];
	graduation_years: number[];
};

export type CandidateNote = { id: number; body: string; created_at: string; updated_at: string };

export type CandidateDetail = {
	id: number;
	name: string;
	job_role: string;
	summary: string;
	email: string | null;
	skills: { id: number; name: string; level: string; years: number | null }[];
	education: {
		qualification: string;
		specialization: string;
		institute: string;
		from_date: string | null;
		to_date: string | null;
		current: boolean;
		score: string;
	}[];
	graduation_year: number | null;
	employment: {
		company: string;
		designation: string;
		from_date: string | null;
		to_date: string | null;
		current: boolean;
		description: string;
	}[];
	projects: {
		name: string;
		description: string;
		role: string | null;
		size: number | null;
		from_date: string | null;
		to_date: string | null;
		skills: string[];
	}[];
	resume: { title: string; published_at: string; pdf_size: number };
	shortlisted: boolean;
};
