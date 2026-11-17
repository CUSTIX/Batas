/* Batas: small progressive enhancements. The site works without this file. */
(function () {
  "use strict";
  // Show that a question is being answered (an AI answer can take a few seconds).
  document.querySelectorAll("form[data-ask]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("[data-submit]");
      if (!button) return;
      setTimeout(function () {
        button.setAttribute("aria-busy", "true");
        button.textContent = "Looking it up…";
      }, 0);
    });
  });
})();
