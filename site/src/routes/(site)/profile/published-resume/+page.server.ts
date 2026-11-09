/**
 * Profile → Published resume: choose which Reactive Resume resume recruiters see.
 *
 * Publishing snapshots the resume (JSON + PDF) in Django; recruiters only ever
 * get the version published here, and withdrawing removes their access.
 */

import { fail, type Actions } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiGet, apiPost, ApiRequestError } from '$lib/server/api';
import type { RRLinkStatus } from '../integrations/+page.server';

export type ResumeVersion = {
	id: string;
	title: string;
	external_resume_id: string;
	rr_updated_at: string;
	pdf_size: number;
	pdf_sha256: string;
	created_at: string;
	is_current: boolean;
};

export type Publication = {
	published: boolean;
	published_at: string | null;
	withdrawn_at: string | null;
	current: ResumeVersion | null;
	history: ResumeVersion[];
};

export type RRResume = { id: string; name: string; updated_at: string };

const message = (err: unknown, fallback: string) =>
	err instanceof ApiRequestError ? err.message : fallback;
const statusOf = (err: unknown) => (err instanceof ApiRequestError ? err.status : 500);

export const load: PageServerLoad = async ({ fetch }) => {
	let rr: RRLinkStatus | null = null;
	let publication: Publication | null = null;
	let resumes: RRResume[] = [];
	let resumesError = '';
	let loadError = '';

	try {
		[rr, publication] = await Promise.all([
			apiGet<RRLinkStatus>(fetch, '/integrations/rr/'),
			apiGet<Publication>(fetch, '/integrations/publication/')
		]);
	} catch (err) {
		loadError = message(err, 'Could not load your published resume.');
	}

	if (rr?.status === 'connected') {
		try {
			resumes = await apiGet<RRResume[]>(fetch, '/integrations/rr/resumes/');
		} catch (err) {
			resumesError = message(err, 'Could not list your Reactive Resume resumes.');
		}
	}

	return { rr, publication, resumes, resumesError, loadError };
};

export const actions: Actions = {
	publish: async ({ request, fetch }) => {
		const id = (await request.formData()).get('external_resume_id');
		if (typeof id !== 'string' || !id) return fail(400, { error: 'Choose a resume to publish.' });
		try {
			await apiPost(fetch, '/integrations/publication/publish/', { external_resume_id: id });
			return { published: true };
		} catch (err) {
			return fail(statusOf(err), { error: message(err, 'Publishing failed. Nothing was changed.') });
		}
	},

	withdraw: async ({ fetch }) => {
		try {
			await apiPost(fetch, '/integrations/publication/withdraw/');
			return { withdrawn: true };
		} catch (err) {
			return fail(statusOf(err), { error: message(err, 'Could not withdraw the resume.') });
		}
	}
};
