// Flowbridge interface helpers. Loaded as a file (no inline scripts), so the
// Content-Security-Policy can forbid inline JavaScript.
(function () {
  "use strict";

  // Ask before irreversible actions. A form opts in with data-confirm="message".
  // A decision form can give a different message per outcome, e.g. data-confirm-reject.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var outcome = form.querySelector('input[name="outcome"]:checked');
    var message = (outcome && form.getAttribute("data-confirm-" + outcome.value.toLowerCase())) ||
      form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  // Show the "name for a new document" field only when it applies.
  document.querySelectorAll("[data-upload-form]").forEach(function (form) {
    var target = form.querySelector('[name="target"]');
    var nameRow = form.querySelector("[data-name-row]");
    if (!target || !nameRow || target.type === "hidden") return;
    function sync() { nameRow.hidden = target.value !== "new"; }
    target.addEventListener("change", sync);
    sync();
  });
})();
