/**
 * Salary formatting for GradBridge (Australia and Singapore).
 * Amounts are whole dollars in the job's own currency; the API stores AUD or SGD.
 */

import type { SalaryCurrency } from '$lib/types';

export const SALARY_CURRENCIES: { value: SalaryCurrency; label: string }[] = [
	{ value: 'AUD', label: 'AUD (Australian dollar)' },
	{ value: 'SGD', label: 'SGD (Singapore dollar)' }
];

export function currencySymbol(currency?: string | null): string {
	return currency === 'SGD' ? 'S$' : 'A$';
}

/** 85000 -> "85k", 92500 -> "92.5k", 800 -> "800" */
export function thousands(amount: number): string {
	if (amount < 1000) return String(amount);
	const value = amount / 1000;
	return Number.isInteger(value) ? `${value}k` : `${value.toFixed(1)}k`;
}

export function formatSalary(
	min: number,
	max: number,
	type: string,
	currency?: string | null
): string {
	if (!min && !max) return 'Not disclosed';
	const symbol = currencySymbol(currency);
	const minStr = min ? `${symbol}${thousands(min)}` : '';
	const maxStr = max ? `${symbol}${thousands(max)}` : '';
	const range = minStr && maxStr ? `${minStr} - ${maxStr}` : minStr || maxStr;
	return `${range} per ${type === 'Month' ? 'month' : 'year'}`;
}
