/**
 * GradBridge candidate detail: allowed profile fields, the published PDF,
 * shortlist and this recruiter's own notes. Django re-checks on every request
 * that the candidate still has a published resume.
 */

import { error, fail, type Actions } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import {
	candidateApi,
	CandidateApiError,
	pageError,
	type CandidateDetail,
	type CandidateNote
} from '$lib/server/candidates';

function candidateId(raw: string | undefined) {
	const id = Number(raw);
	if (!Number.isInteger(id) || id < 1) error(404, 'Not found');
	return id;
}

const failWith = (err: unknown, fallback: string) =>
	fail(err instanceof CandidateApiError ? err.status : 500, {
		error: err instanceof CandidateApiError ? err.message : fallback
	});

export const load: PageServerLoad = async ({ fetch, params, url }) => {
	const id = candidateId(params.id);
	try {
		const [candidate, notes] = await Promise.all([
			candidateApi<CandidateDetail>(fetch, `${id}/`, {}, url.pathname),
			candidateApi<CandidateNote[]>(fetch, `${id}/notes/`, {}, url.pathname)
		]);
		return { candidate, notes };
	} catch (err) {
		pageError(err);
	}
};

export const actions: Actions = {
	shortlist: async ({ fetch, params, request }) => {
		const id = candidateId(params.id);
		const remove = (await request.formData()).get('remove') === '1';
		try {
			await candidateApi(fetch, `${id}/shortlist/`, { method: remove ? 'DELETE' : 'POST' });
			return { ok: true };
		} catch (err) {
			return failWith(err, 'Could not update the shortlist.');
		}
	},

	addNote: async ({ fetch, params, request }) => {
		const id = candidateId(params.id);
		const body = String((await request.formData()).get('body') ?? '');
		try {
			await candidateApi(fetch, `${id}/notes/`, { method: 'POST', body: JSON.stringify({ body }) });
			return { noteSaved: true };
		} catch (err) {
			return failWith(err, 'Could not save the note.');
		}
	},

	editNote: async ({ fetch, params, request }) => {
		const id = candidateId(params.id);
		const data = await request.formData();
		const noteId = Number(data.get('note_id'));
		try {
			await candidateApi(fetch, `${id}/notes/${noteId}/`, {
				method: 'PATCH',
				body: JSON.stringify({ body: String(data.get('body') ?? '') })
			});
			return { noteSaved: true };
		} catch (err) {
			return failWith(err, 'Could not update the note.');
		}
	},

	deleteNote: async ({ fetch, params, request }) => {
		const id = candidateId(params.id);
		const noteId = Number((await request.formData()).get('note_id'));
		try {
			await candidateApi(fetch, `${id}/notes/${noteId}/`, { method: 'DELETE' });
			return { noteDeleted: true };
		} catch (err) {
			return failWith(err, 'Could not delete the note.');
		}
	}
};
