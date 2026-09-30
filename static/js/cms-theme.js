/* ASSERT CMS — theme preference. Loaded synchronously in <head> so the saved
   theme applies before first paint. Dark is the default. */
(function () {
  "use strict";
  var KEY = "assert-cms-theme", root = document.documentElement;
  root.classList.remove("no-js");
  function stored() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "light" ? "#F4F6FA" : "#07080B");
  }
  apply(stored() === "light" ? "light" : "dark");
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      var label = btn.querySelector("[data-theme-label]");
      function sync() {
        var light = root.getAttribute("data-theme") === "light";
        btn.setAttribute("aria-pressed", String(light));
        if (label) label.textContent = "Light theme";
      }
      sync();
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        apply(next);
        try { localStorage.setItem(KEY, next); } catch (e) { /* not persisted in private mode */ }
        document.querySelectorAll("[data-theme-toggle]").forEach(function (b) { b.setAttribute("aria-pressed", String(next === "light")); });
      });
    });
  });
})();
