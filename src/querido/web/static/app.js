/* qdo web — shared JavaScript (sort, filter, copy, export) */

// Re-initialize on HTMX content swaps
document.addEventListener("htmx:afterSettle", function(evt) {
  initDataTable(evt.detail.target);
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", function() {
  initDataTable(document);
  initKeyboardShortcuts();
});

function initDataTable(root) {
  const tables = root.querySelectorAll ? root.querySelectorAll("table[data-sortable]") : [];
  tables.forEach(function(table) {
    if (table.dataset.initialized) return;
    table.dataset.initialized = "true";

    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    const ths = Array.from(thead.querySelectorAll("th"));
    let sortCol = -1, sortDir = 0;

    ths.forEach(function(th, idx) {
      th.addEventListener("click", function() {
        if (sortCol === idx) { sortDir = (sortDir + 1) % 3; }
        else { sortCol = idx; sortDir = 1; }
        ths.forEach(function(h) { h.classList.remove("sort-asc", "sort-desc"); });
        if (sortDir === 1) th.classList.add("sort-asc");
        else if (sortDir === 2) th.classList.add("sort-desc");

        var rows = Array.from(tbody.querySelectorAll("tr"));
        if (sortDir === 0) {
          rows.sort(function(a, b) { return a.dataset.idx - b.dataset.idx; });
        } else {
          rows.sort(function(a, b) {
            var av = a.children[sortCol] ? a.children[sortCol].textContent : "";
            var bv = b.children[sortCol] ? b.children[sortCol].textContent : "";
            var an = parseFloat(av.replace(/,/g, "")), bn = parseFloat(bv.replace(/,/g, ""));
            var cmp;
            if (!isNaN(an) && !isNaN(bn)) { cmp = an - bn; }
            else { cmp = av.localeCompare(bv, undefined, {numeric: true, sensitivity: "base"}); }
            return sortDir === 2 ? -cmp : cmp;
          });
        }
        rows.forEach(function(r) { tbody.appendChild(r); });
        updateRowCount(table);
      });
    });
  });

  // Filter inputs
  var filters = root.querySelectorAll ? root.querySelectorAll("[data-filter-table]") : [];
  filters.forEach(function(input) {
    if (input.dataset.filterInit) return;
    input.dataset.filterInit = "true";
    input.addEventListener("input", function() {
      var tableId = input.dataset.filterTable;
      var table = document.getElementById(tableId);
      if (!table) return;
      var q = input.value.toLowerCase();
      var tbody = table.querySelector("tbody");
      if (!tbody) return;
      tbody.querySelectorAll("tr").forEach(function(tr) {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
      updateRowCount(table);
    });
  });
}

function updateRowCount(table) {
  var countEl = document.querySelector("[data-count-for='" + table.id + "']");
  if (!countEl) return;
  var tbody = table.querySelector("tbody");
  var total = tbody.querySelectorAll("tr").length;
  var visible = tbody.querySelectorAll("tr:not([style*='display: none'])").length;
  countEl.textContent = visible === total ? total + " rows" : visible + " of " + total + " rows";
}

function copyTable(tableId) {
  var table = document.getElementById(tableId);
  if (!table) return;
  var thead = table.querySelector("thead");
  var tbody = table.querySelector("tbody");
  var headers = Array.from(thead.querySelectorAll("th")).map(function(th) { return th.textContent.trim(); });
  var rows = Array.from(tbody.querySelectorAll("tr:not([style*='display: none'])"));
  var lines = [headers.join("\t")];
  rows.forEach(function(r) {
    lines.push(Array.from(r.children).map(function(td) { return td.textContent; }).join("\t"));
  });
  navigator.clipboard.writeText(lines.join("\n")).then(function() { showToast("Copied to clipboard"); });
}

function exportCSV(tableId) {
  var table = document.getElementById(tableId);
  if (!table) return;
  var thead = table.querySelector("thead");
  var tbody = table.querySelector("tbody");
  var headers = Array.from(thead.querySelectorAll("th")).map(function(th) { return th.textContent.trim(); });
  var rows = Array.from(tbody.querySelectorAll("tr:not([style*='display: none'])"));
  function escapeCSV(v) {
    var s = String(v);
    if (s.indexOf(",") !== -1 || s.indexOf('"') !== -1 || s.indexOf("\n") !== -1)
      return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }
  var lines = [headers.map(escapeCSV).join(",")];
  rows.forEach(function(r) {
    lines.push(Array.from(r.children).map(function(td) { return escapeCSV(td.textContent); }).join(","));
  });
  var blob = new Blob([lines.join("\n")], {type: "text/csv"});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (document.title || "export") + ".csv";
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("CSV downloaded");
}

function showToast(msg) {
  var t = document.querySelector(".toast");
  if (!t) {
    t = document.createElement("div");
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(function() { t.classList.remove("show"); }, 2000);
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", function(e) {
    // Ignore if typing in an input/textarea
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") {
      if (e.key === "Escape") { e.target.blur(); }
      return;
    }
    if (e.key === "?") {
      e.preventDefault();
      var overlay = document.querySelector(".help-overlay");
      if (overlay) overlay.classList.toggle("show");
    }
    if (e.key === "/") {
      e.preventDefault();
      var search = document.querySelector(".search-input") || document.querySelector("#sidebar-search");
      if (search) search.focus();
    }
    if (e.key === "Escape") {
      var overlay = document.querySelector(".help-overlay");
      if (overlay) overlay.classList.remove("show");
    }
  });
}

// Tab switching helper
function activateTab(el) {
  el.closest(".tab-bar").querySelectorAll("a").forEach(function(a) { a.classList.remove("active"); });
  el.classList.add("active");
}

// --- Query elapsed timer ---
// Show elapsed seconds on the HTMX indicator while a request is in flight.
(function() {
  var _timer = null;
  var _startTime = 0;

  document.addEventListener("htmx:beforeRequest", function() {
    _startTime = Date.now();
    var el = document.getElementById("query-elapsed");
    if (el) el.textContent = "";
    _timer = setInterval(function() {
      var elapsed = ((Date.now() - _startTime) / 1000).toFixed(0);
      var el = document.getElementById("query-elapsed");
      if (el) el.textContent = "(" + elapsed + "s)";
    }, 1000);
  });

  function stopTimer() {
    if (_timer) { clearInterval(_timer); _timer = null; }
    var el = document.getElementById("query-elapsed");
    if (el) el.textContent = "";
  }

  document.addEventListener("htmx:afterRequest", stopTimer);
  document.addEventListener("htmx:requestError", stopTimer);
  document.addEventListener("htmx:responseError", stopTimer);
})();
