/**
 * /government-jobs/ — all government postings
 *
 * Replaces `pjob.views.government_jobs`.
 */

import type { PageServerLoad } from './$types';
import { SITE_URL } from '$lib/config/env';
import { buildSeo, fetchLandingJobs, parsePage } from '$lib/server/landing';

export const load: PageServerLoad = async ({ url, fetch }) => {
	const page = parsePage(url.searchParams);
	const data = await fetchLandingJobs(fetch, { job_type: 'government' }, page);

	return {
		...data,
		seo: buildSeo({
			heading: 'Public Sector Jobs',
			subject: 'public sector job openings across Singapore and Australia',
			totalJobs: data.totalJobs,
			page
		}),
		canonical: `${SITE_URL}/government-jobs/`,
		breadcrumb: { label: 'Public Sector', href: '/government-jobs/' }
	};
};
