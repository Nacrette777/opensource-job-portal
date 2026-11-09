/**
 * Move an element to the end of `document.body` while it is mounted.
 *
 * Use on `position: fixed` overlays (modals) rendered inside animated cards:
 * `.animate-fade-in-up` keeps a transform applied after it finishes, which
 * makes the card the containing block for fixed descendants and clips the
 * modal to the card. Rendering at the body escapes that.
 */
export function portal(node: HTMLElement) {
	document.body.appendChild(node);

	return {
		destroy() {
			node.remove();
		}
	};
}
