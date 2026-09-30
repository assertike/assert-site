/* ASSERT CMS — admin behaviour: schema-driven editor serialisation, repeaters,
   image picker, Markdown helpers, confirmations and unsaved-change warnings. */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var uidCounter = 0;
  var base = ((document.querySelector('meta[name="cms-base"]') || {}).content || "/cms/").replace(/\/$/, "");
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // -- serialisation ----------------------------------------------------------------
  function ownFields(container) {
    return $$("[data-key]", container).filter(function (el) {
      return el.parentElement.closest("[data-container]") === container;
    });
  }
  function readField(el) {
    var kind = el.dataset.kind;
    if (kind === "group") return collect(el);
    if (kind === "repeater") {
      var list = $("[data-items]", el);
      return Array.prototype.filter.call(list.children, function (li) { return li.matches(".rep-item"); }).map(collect);
    }
    var input = $("[data-input]", el);
    if (!input) return null;
    if (kind === "bool") return input.checked;
    if (kind === "number") return input.value === "" ? 0 : Number(input.value);
    if (kind === "list") return input.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
    if (kind === "tags") return input.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    return input.value;
  }
  function collect(container) {
    var out = {};
    ownFields(container).forEach(function (el) { out[el.dataset.key] = readField(el); });
    return out;
  }

  // Give cloned repeater items unique ids and fix label/aria references.
  function renumber(root) {
    var map = {};
    $$("[id]", root).forEach(function (el) {
      var fresh = el.id + "-n" + (++uidCounter);
      map[el.id] = fresh;
      el.id = fresh;
    });
    ["for", "aria-describedby", "aria-labelledby", "aria-controls", "data-counter-for"].forEach(function (attr) {
      $$("[" + attr + "]", root).forEach(function (el) {
        el.setAttribute(attr, el.getAttribute(attr).split(" ").map(function (id) { return map[id] || id; }).join(" "));
      });
    });
  }

  // -- live announcements ---------------------------------------------------------------
  var live = document.createElement("div");
  live.className = "visually-hidden";
  live.setAttribute("aria-live", "polite");
  document.addEventListener("DOMContentLoaded", function () { document.body.appendChild(live); });
  function announce(msg) { live.textContent = ""; setTimeout(function () { live.textContent = msg; }, 50); }

  // -- editor -------------------------------------------------------------------------
  function initEditor(form) {
    var dirty = false;
    var dirtyLabel = $("[data-dirty]", form);
    function markDirty() {
      if (!dirty) { dirty = true; if (dirtyLabel) dirtyLabel.textContent = "Unsaved changes"; }
    }
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
    window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
    form.addEventListener("submit", function () {
      $("[data-payload]", form).value = JSON.stringify(collect(form));
      dirty = false;
    });

    form.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn || !form.contains(btn)) return;
      var item = btn.closest(".rep-item");

      if (btn.hasAttribute("data-add")) {
        var rep = btn.closest(".rep");
        var tpl = $(":scope > template[data-template]", rep);
        var frag = tpl.content.cloneNode(true);
        var li = frag.querySelector(".rep-item");
        renumber(li);
        li.classList.add("is-new");
        $(":scope > [data-items]", rep).appendChild(li);
        wire(li);
        var first = $("input:not([type=hidden]), textarea, select", li);
        if (first) first.focus();
        announce("Item added");
        markDirty();
      } else if (btn.hasAttribute("data-remove") && item) {
        var label = ($("[data-rep-title]", item) || {}).textContent || "item";
        if (!confirm("Remove “" + label.trim() + "”?")) return;
        var next = item.nextElementSibling || item.previousElementSibling;
        var addBtn = $(":scope > [data-add]", item.closest(".rep"));
        item.remove();
        (next ? $("[data-remove]", next) : addBtn).focus();
        announce("Item removed");
        markDirty();
      } else if (btn.dataset.move && item) {
        var sib = btn.dataset.move === "up" ? item.previousElementSibling : item.nextElementSibling;
        if (!sib) return;
        if (btn.dataset.move === "up") item.parentNode.insertBefore(item, sib);
        else item.parentNode.insertBefore(sib, item);
        btn.focus();
        announce("Item moved " + btn.dataset.move);
        markDirty();
      }
    });

    // Keep repeater item titles in sync with their first text field.
    form.addEventListener("input", function (e) {
      var item = e.target.closest(".rep-item");
      if (!item) return;
      var first = $(".rep-body > .fi input[type=text], .rep-body > .fi textarea", item);
      if (first === e.target) {
        var t = $("[data-rep-title]", item);
        if (t) t.textContent = e.target.value.slice(0, 60) || "New item";
      }
    });

    // Suggest a slug from the title while the slug is empty / untouched.
    var title = $("[data-title]", form), slug = $("[data-slug]", form);
    if (title && slug) {
      var auto = !slug.value;
      slug.addEventListener("input", function () { auto = !slug.value; });
      title.addEventListener("input", function () {
        if (!auto) return;
        slug.placeholder = title.value.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
          .replace(/[^a-z0-9\s-]/g, "").trim().replace(/[\s-]+/g, "-");
      });
    }
    wire(form);
  }

  function wire(root) {
    // Character counters
    $$("[data-max]", root).forEach(function (input) {
      var counter = $('[data-counter-for="' + input.id + '"]', root) || $('[data-counter-for="' + input.id + '"]');
      if (!counter) return;
      var max = Number(input.dataset.max);
      function update() {
        counter.textContent = input.value.length + " / " + max;
        counter.classList.toggle("is-over", input.value.length > max);
      }
      input.addEventListener("input", update);
      update();
    });
    // Icon previews
    $$("[data-icon-select]", root).forEach(function (sel) {
      sel.addEventListener("change", function () {
        var use = sel.parentElement.querySelector("use");
        use.setAttribute("href", use.getAttribute("href").replace(/#i-.*$/, "#i-" + (sel.value || "spark")));
      });
    });
    // Image pickers
    $$("[data-image-picker]", root).forEach(function (box) {
      $("[data-choose]", box).addEventListener("click", function () { openPicker(box); });
      $("[data-clear]", box).addEventListener("click", function () {
        $("[data-input]", box).value = "";
        $("[data-thumb]", box).innerHTML = '<span class="muted small">No image</span>';
        $("[data-img-label]", box).textContent = "—";
        box.closest("form").dispatchEvent(new Event("change"));
        announce("Image removed");
      });
    });
    // Markdown toolbars
    $$(".md-tools", root).forEach(function (bar) {
      var area = bar.parentElement.querySelector("textarea");
      var out = bar.parentElement.querySelector("[data-md-output]");
      bar.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-md-preview")) {
          var on = b.getAttribute("aria-pressed") !== "true";
          b.setAttribute("aria-pressed", String(on));
          if (!on) { out.hidden = true; area.hidden = false; area.focus(); return; }
          fetch(base + "/preview", {
            method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
            body: JSON.stringify({ text: area.value }), credentials: "same-origin"
          }).then(function (r) { return r.json(); }).then(function (d) {
            out.innerHTML = d.html || "<p><em>Nothing to preview.</em></p>";
            out.hidden = false; area.hidden = true;
          });
          return;
        }
        var tok = b.dataset.md, s = area.selectionStart, en = area.selectionEnd, v = area.value, sel = v.slice(s, en);
        var ins;
        if (tok === "link") ins = "[" + (sel || "link text") + "](https://)";
        else if (tok === "## " || tok === "- ") {
          var lineStart = v.lastIndexOf("\n", s - 1) + 1;
          area.value = v.slice(0, lineStart) + tok + v.slice(lineStart);
          area.focus(); area.selectionStart = area.selectionEnd = en + tok.length;
          area.dispatchEvent(new Event("input", { bubbles: true }));
          return;
        } else ins = tok + (sel || "text") + tok;
        area.setRangeText(ins, s, en, "select");
        area.focus();
        area.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
  }

  // -- image picker dialog ------------------------------------------------------------------
  var mediaCache = null, activeBox = null;
  function openPicker(box) {
    var dlg = $("[data-picker]");
    if (!dlg) return;
    activeBox = box;
    var grid = $("[data-picker-grid]", dlg), search = $("[data-picker-search]", dlg);
    function render(items) {
      var current = $("[data-input]", box).value, q = search.value.toLowerCase();
      grid.innerHTML = "";
      items.filter(function (m) { return !q || m.id.indexOf(q) > -1 || m.alt.toLowerCase().indexOf(q) > -1; })
        .forEach(function (m) {
          var li = document.createElement("li"), b = document.createElement("button"), img = document.createElement("img"), span = document.createElement("span");
          b.type = "button"; b.setAttribute("aria-pressed", String(m.id === current));
          img.src = m.thumb; img.alt = ""; img.loading = "lazy";
          span.textContent = m.id + (m.alt ? " — " + m.alt : " — ⚠ no alt text");
          b.append(img, span); li.appendChild(b); grid.appendChild(li);
          b.addEventListener("click", function () { choose(m); dlg.close(); });
        });
    }
    function load() {
      if (mediaCache) return Promise.resolve(mediaCache);
      return fetch(base + "/media.json", { credentials: "same-origin" }).then(function (r) { return r.json(); })
        .then(function (d) { mediaCache = d; return d; });
    }
    load().then(function (items) {
      render(items);
      search.oninput = function () { render(items); };
      dlg.showModal();
      search.focus();
    });
    dlg.addEventListener("close", function () { if (activeBox) $("[data-choose]", activeBox).focus(); }, { once: true });
  }
  function choose(m) {
    var box = activeBox;
    $("[data-input]", box).value = m.id;
    var thumb = $("[data-thumb]", box);
    thumb.innerHTML = "";
    var img = document.createElement("img"); img.src = m.thumb; img.alt = ""; thumb.appendChild(img);
    var label = $("[data-img-label]", box);
    label.innerHTML = "";
    var code = document.createElement("code"); code.textContent = m.id;
    label.append(code, document.createElement("br"), document.createTextNode(m.alt || "⚠ Missing alt text"));
    box.closest("form").dispatchEvent(new Event("change"));
    announce("Image " + m.id + " selected");
  }

  // -- list reordering (collection tables) ------------------------------------------------------
  function initReorder(form) {
    form.addEventListener("click", function (e) {
      var b = e.target.closest("[data-row-up], [data-row-down]");
      if (!b) return;
      var row = b.closest("tr"), up = b.hasAttribute("data-row-up");
      var sib = up ? row.previousElementSibling : row.nextElementSibling;
      if (!sib) return;
      row.parentNode.insertBefore(up ? row : sib, up ? sib : row);
      b.focus();
      announce("Moved " + (up ? "up" : "down") + ". Remember to save the order.");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    $$("[data-editor]").forEach(initEditor);
    $$("[data-reorder]").forEach(initReorder);
    $$("form[data-confirm]").forEach(function (f) {
      f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
    });
    var af = $("[data-autofocus]");
    if (af) af.focus();
  });
})();
