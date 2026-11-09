/**
 * Page-level confirmation dialog, used instead of window.confirm(): the native
 * dialog cannot be styled, and some embedded browsers dismiss it on their own,
 * which silently cancels the action. Render <ConfirmDialog /> once in the root
 * layout, then await confirmAction(...) or use confirmSubmit(...) on a form.
 */

interface ConfirmOptions {
	/** Text of the confirming button. */
	confirmLabel?: string;
	/** Style the confirming button as destructive. */
	danger?: boolean;
}

interface ConfirmRequest extends Required<ConfirmOptions> {
	message: string;
	resolve: (confirmed: boolean) => void;
}

export const confirmState = $state<{ current: ConfirmRequest | null }>({ current: null });

export function confirmAction(message: string, options: ConfirmOptions = {}): Promise<boolean> {
	return new Promise((resolve) => {
		confirmState.current?.resolve(false);
		confirmState.current = {
			message,
			confirmLabel: options.confirmLabel ?? 'Confirm',
			danger: options.danger ?? false,
			resolve
		};
	});
}

/**
 * onsubmit handler for a plain form: ask first, then submit the same form again
 * with the same submit button. `onConfirm` runs just before that submission.
 */
export function confirmSubmit(message: string, options: ConfirmOptions & { onConfirm?: () => void } = {}) {
	return async (event: SubmitEvent) => {
		const form = event.currentTarget as HTMLFormElement;
		if (form.dataset.confirmed === 'yes') {
			delete form.dataset.confirmed;
			return;
		}
		event.preventDefault();
		const submitter = event.submitter;
		if (await confirmAction(message, options)) {
			options.onConfirm?.();
			form.dataset.confirmed = 'yes';
			form.requestSubmit(
				submitter instanceof HTMLButtonElement || submitter instanceof HTMLInputElement ? submitter : undefined
			);
		}
	};
}
