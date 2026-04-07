// ListHub sidebar (V1.1):
// - Section expand/collapse with chevron buttons + title links
// - Only one section expanded by default (but multiple allowed)
// - localStorage persistence of folder (tree) collapse state
// - Mobile drawer + sidebar collapse toggle
// - Active link highlighting with auto-expand ancestors
// - Cmd/Ctrl + \ to toggle sidebar
(function () {
  'use strict';

  const STORAGE_KEY = 'listhub_sidebar_state';
  const COLLAPSED_KEY = 'listhub_sidebar_collapsed';
  const SECTIONS_KEY = 'listhub_sidebar_sections';

  // ── Folder state (tree) ──
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

  // Restore folder open/close state (inside tree)
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

  // ── Section (top-level) state ──
  function loadSectionState() {
    try {
      return JSON.parse(localStorage.getItem(SECTIONS_KEY) || 'null');
    } catch (e) {
      return null;
    }
  }
  function saveSectionState(map) {
    try {
      localStorage.setItem(SECTIONS_KEY, JSON.stringify(map));
    } catch (e) {}
  }

  const sections = Array.from(document.querySelectorAll('.sb-section'));
  if (sections.length) {
    const persisted = loadSectionState();
    // Determine initial expanded state per section
    sections.forEach(function (section, idx) {
      const id = section.getAttribute('data-sb-section');
      let expanded;
      if (persisted && id in persisted) {
        expanded = persisted[id];
      } else {
        // Default: first applicable section expanded. Focused section takes
        // precedence (if present). Otherwise Your docs for logged in, else Community.
        if (id === 'focused') {
          expanded = true;
        } else if (persisted) {
          expanded = false;
        } else {
          // No persisted state at all: expand first non-focused section only
          // unless a focused section is present which wins.
          const hasFocused = sections.some(function (s) {
            return s.getAttribute('data-sb-section') === 'focused';
          });
          if (hasFocused) {
            expanded = (id === 'focused');
          } else {
            // First section in the DOM wins
            expanded = (idx === 0);
          }
        }
      }
      if (expanded) section.classList.add('sb-expanded');
      else section.classList.remove('sb-expanded');
      const chevron = section.querySelector('.sb-section-chevron');
      if (chevron) chevron.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });

    // Toggle on chevron click
    sections.forEach(function (section) {
      const chevron = section.querySelector('.sb-section-chevron');
      if (!chevron) return;
      chevron.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const expanded = section.classList.toggle('sb-expanded');
        chevron.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        // Persist all section states
        const snapshot = {};
        sections.forEach(function (s) {
          snapshot[s.getAttribute('data-sb-section')] = s.classList.contains('sb-expanded');
        });
        saveSectionState(snapshot);
      });
    });
  }

  // ── Sidebar collapse toggle (global hamburger) ──
  const toggleBtn = document.getElementById('sb-toggle');
  const body = document.body;
  const isMobile = function () { return window.matchMedia('(max-width: 768px)').matches; };

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

  // Close mobile drawer when clicking a file link
  document.querySelectorAll('.sb-sidebar .sb-file-link').forEach(function (a) {
    a.addEventListener('click', function () {
      if (isMobile()) body.classList.remove('sb-open');
    });
  });

  // Close mobile drawer on backdrop click
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
        // Also ensure the parent section is expanded
        if (el.classList && el.classList.contains('sb-section')) {
          el.classList.add('sb-expanded');
          const chevron = el.querySelector('.sb-section-chevron');
          if (chevron) chevron.setAttribute('aria-expanded', 'true');
        }
        el = el.parentElement;
      }
    }
  });

  // Keyboard: Cmd/Ctrl + \ toggles sidebar
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
      e.preventDefault();
      if (toggleBtn) toggleBtn.click();
    }
  });
})();
