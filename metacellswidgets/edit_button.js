// The browser code of the "Edit" button of a shown graph (see ``_EditButton`` in ``forms.py``): a small pencil button
// on top of the graph, at its top left corner. Clicking it replaces the code of its cell, if the cell still has the
// ``expected`` code, by the ``replacement`` code (which edits the graph), and runs the cell. This needs the notebook's
// app, which JupyterLab and Notebook 7 expose only when started with ``expose_app_in_browser=True``; otherwise it says
// how to edit the graph.

function render({ model, el }) {
  // On top of the graph, which is the next element in the button's box.
  el.style.position = "absolute";
  el.style.top = "4px";
  el.style.left = "4px";
  el.style.zIndex = "10";
  requestAnimationFrame(() => {
    if (el.parentElement) {
      el.parentElement.style.position = "relative";
    }
  });

  const button = document.createElement("button");
  button.className = "jupyter-widgets jupyter-button widget-button";
  button.title = "Edit";
  button.style.width = "2.5em";
  button.innerHTML = '<i class="fa fa-pencil"></i>';
  const message = document.createElement("div");
  el.append(button, message);

  button.addEventListener("click", async () => {
    const app = window.jupyterapp;
    if (!app) {
      message.textContent =
        "To edit the graph, add .edit() after its call and run the cell. " +
        "To make this button do it, start JupyterLab with --LabApp.expose_app_in_browser=True " +
        "(Notebook 7: --JupyterNotebookApp.expose_app_in_browser=True).";
      return;
    }
    const panel = app.shell.currentWidget;
    const notebook = panel && panel.content;
    const cell = notebook && notebook.widgets && notebook.widgets.find((each) => each.node.contains(el));
    if (!cell) {
      message.textContent = "Can't find the cell of this graph.";
      return;
    }
    // The kernel's record of the cell's code may differ in the white space at its end.
    if (cell.model.sharedModel.getSource().trimEnd() !== model.get("expected").trimEnd()) {
      message.textContent = "The cell changed since it ran. Run it again to edit the graph.";
      return;
    }
    cell.model.sharedModel.setSource(model.get("replacement"));
    notebook.activeCellIndex = notebook.widgets.indexOf(cell);
    await app.commands.execute("notebook:run-cell");
  });
}

export default { render };
