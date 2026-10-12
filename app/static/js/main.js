// Invoice Extractor — progressive enhancement only (plan §9).
// Sprint E1: detail-page status polling. When a panel carries
// data-status-poll, fetch the JSON status endpoint every N seconds and
// reload the page once the invoice leaves `uploaded`/`processing`. Every
// feature must still work without JavaScript: the badge is rendered
// server-side and the user can simply refresh manually.
(function () {
  "use strict";

  var panel = document.querySelector("[data-status-poll]");
  if (!panel) return;

  var url = panel.getAttribute("data-status-poll");
  var seconds = parseFloat(panel.getAttribute("data-poll-seconds")) || 2;

  function poll() {
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) return;
        if (data.status !== "uploaded" && data.status !== "processing") {
          window.location.reload();
          return;
        }
        window.setTimeout(poll, seconds * 1000);
      })
      .catch(function () {
        // Network hiccup — try again after the interval.
        window.setTimeout(poll, seconds * 1000);
      });
  }

  window.setTimeout(poll, seconds * 1000);
})();
