// The browser code of the editor's width watcher (see ``_WidthWatcher`` in ``forms.py``): an invisible element as wide
// as its box, which sends its width (in pixels) to the kernel whenever it changes.

function render({ model, el }) {
  el.style.width = "100%";
  el.style.height = "0";
  const observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      model.set("width", Math.round(entry.contentRect.width));
      model.save_changes();
    }
  });
  observer.observe(el);
  return () => observer.disconnect();
}

export default { render };
