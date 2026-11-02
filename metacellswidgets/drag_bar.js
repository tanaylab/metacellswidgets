// The browser code of the editor's drag bars (see ``_DragBar`` in ``forms.py``): a bar under the figure, or to its
// right, which sends the size (in pixels) the figure's height (or width) is dragged to, when the mouse is released. The
// drag starts from the size the kernel last gave it. The element is the widget's own, whose size and margins its
// layout sets, so this sets only its color and its pointer. It is never selected as text, nor dragged as content (the
// browser's drag and drop would take over the pointer). While it is dragged, the pointer is its resize pointer
// everywhere, not that of whatever is under it.

function render({ model, el }) {
  const isWidth = model.get("dimension") === "width";
  const cursor = isWidth ? "ew-resize" : "ns-resize";
  el.style.background = "#bbb";
  el.style.cursor = cursor;
  el.addEventListener("selectstart", (event) => event.preventDefault());
  el.addEventListener("dragstart", (event) => event.preventDefault());
  el.addEventListener("pointerdown", (down) => {
    el.setPointerCapture(down.pointerId);
    const start = model.get("start");
    const from = isWidth ? down.clientX : down.clientY;
    const draggingCursor = document.createElement("style");
    draggingCursor.textContent = `* { cursor: ${cursor} !important; }`;
    document.head.appendChild(draggingCursor);
    const up = (event) => {
      el.releasePointerCapture(event.pointerId);
      const to = isWidth ? event.clientX : event.clientY;
      model.set("dragged", Math.max(model.get("smallest"), Math.round(start + to - from)));
      model.save_changes();
    };
    // Also follows a cancelled drag, which has no ``pointerup``.
    const lost = () => {
      draggingCursor.remove();
      el.removeEventListener("pointerup", up);
      el.removeEventListener("lostpointercapture", lost);
    };
    el.addEventListener("pointerup", up);
    el.addEventListener("lostpointercapture", lost);
  });
}

export default { render };
