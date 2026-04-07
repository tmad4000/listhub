// ListHub sidebar (V1.2):
// - Top-level sections: chevron button + title link
// - Folder rows: chevron button toggles open/closed, folder name links to folder view
// - localStorage persistence (folders + sections, independently)
// - Active link highlighting with auto-expand ancestors
// - Cmd/Ctrl + \ to toggle sidebar collapse
(function () {
  'use strict';

  const STORAGE_KEY = 'listhub_sidebar_state';        // folder (tree) state
  const COLLAPSED_KEY = 'listhub_sidebar_collapsed';  // whole sidebar hidden
  const SECTIONS_KEY = 'listhub_sidebar_sections';    // top-level section expanded

  // ── Folder (tree) state ──
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
  const folderState = loadState();

  // Restore folder open/close state for the new v2 folders
  document.querySelectorAll('.sb-folder-v2[data-sb-key]').forEach(function (el) {
    const key = el.getAttribute('data-sb-key');
    if (key in folderState && folderState[key]) {
      el.classList.add('sb-folder-open');
    }
    const chevron = el.querySelector(':scope > .sb-folder-row > .sb-folder-chevron');
    if (chevron) {
      chevron.setAttribute('aria-expanded', el.classList.contains('sb-folder-open') ? 'true' : 'false');
      chevron.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const isOpen = el.classList.toggle('sb-folder-open');
        chevron.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        folderState[key] = isOpen;
        saveState(folderState);
      });
    }
  });

  // Legacy: restore <details data-sb-key> state if any still exist
  document.querySelectorAll('details[data-sb-key]').forEach(function (el) {
    const key = el.getAttribute('data-sb-key');
    if (key in folderState) {
      el.open = folderState[key];
    }
    el.addEventListener('toggle', function () {
      folderState[key] = el.open;
      saveState(folderState);
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
    sections.forEach(function (section, idx) {
      const id = section.getAttribute('data-sb-section');
      let expanded;
      if (persisted && id in persisted) {
        expanded = persisted[id];
      } else {
        if (id === 'focused') {
          expanded = true;
        } else if (persisted) {
          expanded = false;
        } else {
          const hasFocused = sections.some(function (s) {
            return s.getAttribute('data-sb-section') === 'focused';
          });
          if (hasFocused) {
            expanded = (id === 'focused');
          } else {
            expanded = (idx === 0);
          }
        }
      }
      if (expanded) section.classList.add('sb-expanded');
      else section.classList.remove('sb-expanded');
      const chevron = section.querySelector('.sb-section-chevron');
      if (chevron) chevron.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });

    function toggleSection(section) {
      const chevron = section.querySelector('.sb-section-chevron');
      const expanded = section.classList.toggle('sb-expanded');
      if (chevron) chevron.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      const snapshot = {};
      sections.forEach(function (s) {
        snapshot[s.getAttribute('data-sb-section')] = s.classList.contains('sb-expanded');
      });
      saveSectionState(snapshot);
    }

    sections.forEach(function (section) {
      const chevron = section.querySelector('.sb-section-chevron');
      const header = section.querySelector('.sb-section-header');
      if (chevron) {
        chevron.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          toggleSection(section);
        });
      }
      if (header) {
        // Click anywhere on the header toggles — except on title/action links
        header.addEventListener('click', function (e) {
          if (e.target.closest('.sb-section-title, .sb-section-action, .sb-section-chevron')) return;
          e.preventDefault();
          toggleSection(section);
        });
      }
    });
  }

  // ── Sidebar collapse toggle ──
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

  document.querySelectorAll('.sb-sidebar .sb-file-link, .sb-sidebar .sb-folder-link').forEach(function (a) {
    a.addEventListener('click', function () {
      if (isMobile()) body.classList.remove('sb-open');
    });
  });

  document.addEventListener('click', function (e) {
    if (!isMobile() || !body.classList.contains('sb-open')) return;
    const sidebar = document.getElementById('sb-sidebar');
    if (sidebar && !sidebar.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
      body.classList.remove('sb-open');
    }
  });

  // Highlight current page in sidebar and auto-expand ancestors
  const currentPath = window.location.pathname;
  const highlightLinks = document.querySelectorAll('.sb-file-link, .sb-folder-link');
  highlightLinks.forEach(function (a) {
    if (a.getAttribute('href') === currentPath) {
      a.classList.add('active');
      // Walk up and open all ancestor folders + parent section
      let el = a.parentElement;
      while (el && el.tagName !== 'ASIDE') {
        // Legacy: details
        if (el.tagName === 'DETAILS') el.open = true;
        // New: sb-folder-v2
        if (el.classList && el.classList.contains('sb-folder-v2')) {
          el.classList.add('sb-folder-open');
          const ch = el.querySelector(':scope > .sb-folder-row > .sb-folder-chevron');
          if (ch) ch.setAttribute('aria-expanded', 'true');
        }
        // Parent section
        if (el.classList && el.classList.contains('sb-section')) {
          el.classList.add('sb-expanded');
          const ch = el.querySelector('.sb-section-chevron');
          if (ch) ch.setAttribute('aria-expanded', 'true');
        }
        el = el.parentElement;
      }
    }
  });

  // Cmd/Ctrl + \ toggles sidebar
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
      e.preventDefault();
      if (toggleBtn) toggleBtn.click();
    }
  });
})();
