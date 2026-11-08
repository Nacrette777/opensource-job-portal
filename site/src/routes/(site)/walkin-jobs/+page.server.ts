/**
 * /walkin-jobs/ — all walk-in drives
 *
 * Replaces `pjob.views.walkin_jobs`.
 */

import type { PageServerLoad } from './$types';
import { SITE_URL } from '$lib/config/env';
import { buildSeo, fetchLandingJobs, parsePage } from '$lib/server/landing';

export const load: PageServerLoad = async ({ url, fetch }) => {
	const page = parsePage(url.searchParams);
	const data = await fetchLandingJobs(fetch, { job_type: 'walk-in' }, page);

	return {
		...data,
		seo: buildSeo({
			heading: 'Open Days',
			subject: 'open days and on-the-spot interviews across Singapore and Australia',
			totalJobs: data.totalJobs,
			page
		}),
		canonical: `${SITE_URL}/walkin-jobs/`,
		breadcrumb: { label: 'Open Days', href: '/walkin-jobs/' }
	};
};
