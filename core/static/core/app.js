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

  // Browse: filter articles by number or title as you type.
  var input = document.querySelector("[data-filter]");
  if (input) {
    document.querySelector("[data-filter-box]").hidden = false;
    var sources = Array.prototype.slice.call(document.querySelectorAll("[data-src]"));
    var none = document.querySelector("[data-no-match]");
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      sources.forEach(function (src) {
        var hits = 0;
        src.querySelectorAll("[data-item]").forEach(function (li) {
          var match = !q || li.textContent.toLowerCase().indexOf(q) !== -1;
          li.hidden = !match;
          if (match) hits += 1;
        });
        src.hidden = hits === 0;
        if (q && hits) src.open = true;
        shown += hits;
      });
      none.hidden = shown !== 0;
    });
  }
})();
