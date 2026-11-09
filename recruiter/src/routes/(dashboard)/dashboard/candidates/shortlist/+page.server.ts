/** GradBridge: this recruiter's private shortlist. */

import { fail, type Actions } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { candidateApi, CandidateApiError, pageError, type CandidateListItem } from '$lib/server/candidates';

type Entry =
	| (CandidateListItem & { available: true; shortlisted_at: string })
	| { id: number; available: false; shortlisted_at: string };

export const load: PageServerLoad = async ({ fetch, url }) => {
	const data = await candidateApi<{ count: number; results: Entry[] }>(fetch, 'shortlist/', {}, url.pathname).catch(
		pageError
	);
	return { entries: data.results };
};

export const actions: Actions = {
	remove: async ({ fetch, request }) => {
		const id = Number((await request.formData()).get('candidate_id'));
		if (!Number.isInteger(id) || id < 1) return fail(400, { error: 'Missing candidate' });
		try {
			await candidateApi(fetch, `${id}/shortlist/`, { method: 'DELETE' });
			return { ok: true };
		} catch (err) {
			return fail(err instanceof CandidateApiError ? err.status : 500, { error: 'Could not update the shortlist.' });
		}
	}
};
