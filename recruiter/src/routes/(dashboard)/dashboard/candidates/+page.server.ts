/**
 * GradBridge candidate search: job seekers who have published a resume.
 * Filters live in the URL (GET form), so results can be bookmarked and the
 * back button works.
 */

import { fail, type Actions } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import {
	candidateApi,
	CandidateApiError,
	pageError,
	type CandidateFilters,
	type CandidateListItem
} from '$lib/server/candidates';

type SearchResponse = { count: number; next: string | null; previous: string | null; results: CandidateListItem[] };

const PASS_THROUGH = ['q', 'qualification', 'degree', 'graduation_year', 'page'];

export const load: PageServerLoad = async ({ fetch, url }) => {
	const params = new URLSearchParams();
	for (const key of PASS_THROUGH) {
		const value = url.searchParams.get(key);
		if (value) params.set(key, value);
	}
	const skills = url.searchParams.getAll('skill').filter(Boolean);
	if (skills.length) params.set('skills', skills.join(','));

	// A 403 here (not a recruiter) becomes a proper error page, not a 500.
	const filters = await candidateApi<CandidateFilters>(fetch, 'filters/').catch(pageError);
	try {
		const results = await candidateApi<SearchResponse>(fetch, `?${params.toString()}`);
		return { filters, results, selected: { skills, q: url.searchParams.get('q') ?? '' }, searchError: '' };
	} catch (err) {
		return {
			filters,
			results: { count: 0, next: null, previous: null, results: [] } as SearchResponse,
			selected: { skills, q: url.searchParams.get('q') ?? '' },
			searchError: err instanceof CandidateApiError ? err.message : 'Search failed.'
		};
	}
};

export const actions: Actions = {
	shortlist: async ({ request, fetch }) => {
		const data = await request.formData();
		const id = Number(data.get('candidate_id'));
		const remove = data.get('remove') === '1';
		if (!Number.isInteger(id) || id < 1) return fail(400, { error: 'Missing candidate' });
		try {
			await candidateApi(fetch, `${id}/shortlist/`, { method: remove ? 'DELETE' : 'POST' });
			return { ok: true };
		} catch (err) {
			return fail(err instanceof CandidateApiError ? err.status : 500, {
				error: err instanceof CandidateApiError ? err.message : 'Could not update the shortlist.'
			});
		}
	}
};
