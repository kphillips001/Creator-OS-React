const PRESSED_ATTRIBUTE = "data-creator-pressed";

export function installButtonPressFeedback(documentRoot: Document = document) {
  let pressed: HTMLButtonElement | null = null;

  const release = () => {
    const button = pressed;
    pressed = null;
    if (!button) return;
    requestAnimationFrame(() => {
      if (pressed !== button) button.removeAttribute(PRESSED_ATTRIBUTE);
    });
  };
  const press = (event: PointerEvent) => {
    if (event.button !== 0) return;
    const button = (event.target as Element | null)?.closest("button");
    if (!(button instanceof HTMLButtonElement) || button.disabled) return;
    release();
    pressed = button;
    button.setAttribute(PRESSED_ATTRIBUTE, "true");
  };

  documentRoot.addEventListener("pointerdown", press, true);
  documentRoot.addEventListener("pointerup", release, true);
  documentRoot.addEventListener("pointercancel", release, true);
  window.addEventListener("blur", release);
  return () => {
    release();
    documentRoot.removeEventListener("pointerdown", press, true);
    documentRoot.removeEventListener("pointerup", release, true);
    documentRoot.removeEventListener("pointercancel", release, true);
    window.removeEventListener("blur", release);
  };
}
