/* ASSERT — progressive enhancement. The site works fully without this file. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.remove("no-js");
  root.classList.add("js");

  // Theme: dark by default; a visitor's explicit choice is remembered.
  var THEME_KEY = "assert-theme";
  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var meta = document.querySelector("meta[data-theme-color]");
    if (meta) meta.setAttribute("content", theme === "light" ? "#F5F6F8" : "#07080B");
  }
  applyTheme(storedTheme() === "light" ? "light" : "dark");

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var themeBtn = document.querySelector("[data-theme-toggle]");
    if (themeBtn) {
      var sync = function () { themeBtn.setAttribute("aria-pressed", String(root.getAttribute("data-theme") === "light")); };
      sync();
      themeBtn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        applyTheme(next);
        try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private mode: not persisted */ }
        sync();
      });
    }

    var toggle = document.querySelector("[data-nav-toggle]");
    var nav = document.querySelector("[data-nav]");
    var mq = window.matchMedia("(max-width: 1120px)");

    function setNav(open, returnFocus) {
      if (!toggle || !nav) return;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.querySelector(".nav-toggle-label").textContent = open ? "Close" : "Menu";
      nav.classList.toggle("is-open", open);
      document.body.classList.toggle("nav-open", open);
      if (open) {
        var first = nav.querySelector("a, button");
        if (first) first.focus();
      } else if (returnFocus) {
        toggle.focus();
      }
    }

    if (toggle && nav) {
      toggle.addEventListener("click", function () {
        setNav(toggle.getAttribute("aria-expanded") !== "true");
      });
      mq.addEventListener("change", function () { setNav(false); });
    }

    // Submenus: disclosure buttons, closable with Escape and by clicking outside.
    var subToggles = Array.prototype.slice.call(document.querySelectorAll("[data-sub-toggle]"));
    function closeSubs(except) {
      subToggles.forEach(function (btn) {
        if (btn === except) return;
        btn.setAttribute("aria-expanded", "false");
        var menu = document.getElementById(btn.getAttribute("aria-controls"));
        if (menu) menu.classList.remove("is-open");
      });
    }
    subToggles.forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = btn.getAttribute("aria-expanded") !== "true";
        closeSubs(btn);
        btn.setAttribute("aria-expanded", String(open));
        document.getElementById(btn.getAttribute("aria-controls")).classList.toggle("is-open", open);
      });
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".has-sub")) closeSubs();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      var openSub = subToggles.filter(function (b) { return b.getAttribute("aria-expanded") === "true"; })[0];
      if (openSub) { closeSubs(); openSub.focus(); return; }
      if (nav && nav.classList.contains("is-open")) setNav(false, true);
    });
    // Close a submenu when keyboard focus leaves it.
    document.querySelectorAll(".has-sub").forEach(function (item) {
      item.addEventListener("focusout", function (e) {
        if (!item.contains(e.relatedTarget)) closeSubs();
      });
    });

    // Reveal-on-scroll (skipped when reduced motion is preferred).
    var reveals = document.querySelectorAll(".reveal");
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!("IntersectionObserver" in window) || reduce) {
      reveals.forEach(function (el) { el.classList.add("is-visible"); });
    } else {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            io.unobserve(entry.target);
          }
        });
      }, { rootMargin: "0px 0px -8% 0px" });
      reveals.forEach(function (el, i) {
        el.style.transitionDelay = (i % 4) * 80 + "ms";
        io.observe(el);
      });
    }

    // Move focus to form feedback so screen-reader and keyboard users hear it.
    var status = document.querySelector("[data-focus-on-load='true']");
    if (status) status.focus();
  });
})();
