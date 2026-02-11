/**
 * ListHub Tree View — Collapse / Expand
 *
 * Handles folder toggling with proper nested-collapse
 * awareness: expanding a parent won't reveal children
 * of subfolders that are still collapsed.
 */
(function () {
  'use strict';

  function toggleFolder(folderRow) {
    var depth = parseInt(folderRow.dataset.depth, 10);
    var isCollapsing = !folderRow.classList.contains('collapsed');

    folderRow.classList.toggle('collapsed');

    var next = folderRow.nextElementSibling;

    if (isCollapsing) {
      /* ── Collapse: hide every descendant ── */
      while (next) {
        var nd = parseInt(next.dataset.depth, 10);
        if (nd <= depth) break;
        next.classList.add('tree-hidden');
        next = next.nextElementSibling;
      }
    } else {
      /* ── Expand: show children, but skip inside collapsed subfolders ── */
      var skipBelow = -1;
      while (next) {
        var nd = parseInt(next.dataset.depth, 10);
        if (nd <= depth) break;

        if (skipBelow >= 0 && nd > skipBelow) {
          next = next.nextElementSibling;
          continue;
        }

        skipBelow = -1;
        next.classList.remove('tree-hidden');

        /* If this is a collapsed subfolder, skip its descendants */
        if (
          next.classList.contains('tree-row--folder') &&
          next.classList.contains('collapsed')
        ) {
          skipBelow = nd;
        }

        next = next.nextElementSibling;
      }
    }
  }

  function initTree() {
    var folders = document.querySelectorAll('.tree-row--folder');
    folders.forEach(function (folder) {
      folder.addEventListener('click', function (e) {
        /* Don't toggle if the user clicked a link inside the row */
        if (e.target.closest('a')) return;
        toggleFolder(folder);
      });
    });
  }

  /* Handle both deferred and already-loaded DOM */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTree);
  } else {
    initTree();
  }
})();
