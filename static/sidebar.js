// ListHub sidebar: collapse state persistence + toggle + keyboard nav
(function () {
  'use strict';

  const STORAGE_KEY = 'listhub_sidebar_state';
  const COLLAPSED_KEY = 'listhub_sidebar_collapsed';

  // ── Load and persist collapse state for <details data-sb-key="..."> ──
  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  function saveState(state) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {}
  }

  const state = loadState();

  // Restore folder open/close state
  document.querySelectorAll('details[data-sb-key]').forEach(function (el) {
    const key = el.getAttribute('data-sb-key');
    if (key in state) {
      el.open = state[key];
    }
    el.addEventListener('toggle', function () {
      state[key] = el.open;
      saveState(state);
    });
  });

  // ── Sidebar collapse toggle ──
  const toggleBtn = document.getElementById('sb-toggle');
  const body = document.body;
  const isMobile = function () { return window.matchMedia('(max-width: 768px)').matches; };

  // Restore desktop collapsed state
  try {
    if (localStorage.getItem(COLLAPSED_KEY) === '1' && !isMobile()) {
      body.classList.add('sb-collapsed');
    }
  } catch (e) {}

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      if (isMobile()) {
        body.classList.toggle('sb-open');
      } else {
        body.classList.toggle('sb-collapsed');
        try {
          localStorage.setItem(COLLAPSED_KEY, body.classList.contains('sb-collapsed') ? '1' : '0');
        } catch (e) {}
      }
    });
  }

  // Close mobile drawer when clicking a link inside it
  document.querySelectorAll('.sb-sidebar .sb-file-link').forEach(function (a) {
    a.addEventListener('click', function () {
      if (isMobile()) {
        body.classList.remove('sb-open');
      }
    });
  });

  // Close mobile drawer on backdrop click (body::after)
  document.addEventListener('click', function (e) {
    if (!isMobile() || !body.classList.contains('sb-open')) return;
    const sidebar = document.getElementById('sb-sidebar');
    if (sidebar && !sidebar.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
      body.classList.remove('sb-open');
    }
  });

  // Highlight current page in sidebar
  const currentPath = window.location.pathname;
  document.querySelectorAll('.sb-file-link').forEach(function (a) {
    if (a.getAttribute('href') === currentPath) {
      a.classList.add('active');
      // Open all parent <details> so the active item is visible
      let el = a.parentElement;
      while (el && el.tagName !== 'ASIDE') {
        if (el.tagName === 'DETAILS') el.open = true;
        el = el.parentElement;
      }
    }
  });

  // Keyboard: Cmd/Ctrl + \ to toggle sidebar
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
      e.preventDefault();
      if (toggleBtn) toggleBtn.click();
    }
  });
})();
