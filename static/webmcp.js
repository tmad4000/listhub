/**
 * ListHub WebMCP — register ListHub's REST API as in-tab tools for
 * browser-based AI agents (Chrome 146+ behind chrome://flags/#enable-webmcp-testing).
 *
 * Tools call the existing ListHub REST API via fetch() with credentials: 'include',
 * so they inherit whatever browser session the user already has — no API key
 * handoff needed. Read tools work for everyone; write tools require the user
 * to be logged in via the web UI.
 *
 * Spec: https://github.com/webmachinelearning/webmcp
 * Browser support: Chrome 146 Canary, expanding through 2026.
 *
 * Graceful degradation: if `navigator.modelContext` is not available, this
 * file is a no-op. Safe to load on every page.
 */
(function () {
  'use strict';

  if (!('modelContext' in window.navigator)) {
    return;
  }

  var mc = window.navigator.modelContext;

  function api(path, opts) {
    var fetchOpts = Object.assign({ credentials: 'include' }, opts || {});
    fetchOpts.headers = Object.assign(
      { 'Content-Type': 'application/json' },
      fetchOpts.headers || {}
    );
    return fetch('/api/v1' + path, fetchOpts).then(function (resp) {
      if (!resp.ok) {
        return resp.text().then(function (body) {
          throw new Error('ListHub API ' + resp.status + ': ' + body.slice(0, 200));
        });
      }
      return resp.json();
    });
  }

  function textResult(text) {
    return { content: [{ type: 'text', text: text }] };
  }

  function jsonResult(obj) {
    return { content: [{ type: 'text', text: JSON.stringify(obj, null, 2) }] };
  }

  // ----- Read tools (work for any visitor) ----------------------------------

  mc.registerTool({
    name: 'listhub_search',
    description:
      'Full-text search across public ListHub items. Returns a list of matching ' +
      'items with their slug, title, owner, type, and tags. Use this to find ' +
      'content the user might want to reference, save, or browse.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query (FTS5 syntax)' }
      },
      required: ['query']
    },
    execute: function (inputs) {
      return api('/search?q=' + encodeURIComponent(inputs.query)).then(jsonResult);
    }
  });

  mc.registerTool({
    name: 'listhub_get_item',
    description:
      'Fetch a single ListHub item by slug. Returns the full markdown content ' +
      'plus metadata (title, type, visibility, tags, revision, timestamps). ' +
      'Use this to read what is currently on a list before modifying it.',
    inputSchema: {
      type: 'object',
      properties: {
        slug: { type: 'string', description: 'Item slug (the URL-safe id)' }
      },
      required: ['slug']
    },
    execute: function (inputs) {
      return api('/items/by-slug/' + encodeURIComponent(inputs.slug)).then(jsonResult);
    }
  });

  mc.registerTool({
    name: 'listhub_list_my_items',
    description:
      'List items owned by the currently logged-in user. Optionally filter by ' +
      'visibility, type, or tag. Requires the user to be signed in to ListHub ' +
      'in this browser session — if not, the call will return 401.',
    inputSchema: {
      type: 'object',
      properties: {
        visibility: {
          type: 'string',
          description: 'private, public, public_edit, shared, or unlisted'
        },
        type: {
          type: 'string',
          description: 'Filter by item_type: note, list, or document'
        },
        tag: { type: 'string', description: 'Filter by tag' }
      }
    },
    execute: function (inputs) {
      var params = [];
      if (inputs.visibility) params.push('visibility=' + encodeURIComponent(inputs.visibility));
      if (inputs.type) params.push('type=' + encodeURIComponent(inputs.type));
      if (inputs.tag) params.push('tag=' + encodeURIComponent(inputs.tag));
      var qs = params.length ? '?' + params.join('&') : '';
      return api('/items' + qs).then(jsonResult);
    }
  });

  // ----- Write tools (require login session) --------------------------------

  mc.registerTool({
    name: 'listhub_create_item',
    description:
      'Create a new ListHub item owned by the logged-in user. Use this to save ' +
      'a note, start a list, or publish a document. The visibility field ' +
      'controls who can see it: private (default), public, public_edit, shared. ' +
      'For mixed public/private content, you can use <!-- private -->...<!-- /private --> ' +
      'blocks inside the markdown content — they are stripped at render time for non-owners.',
    inputSchema: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Item title' },
        content: { type: 'string', description: 'Markdown content' },
        item_type: {
          type: 'string',
          description: 'note, list, or document (default: note)'
        },
        visibility: {
          type: 'string',
          description: 'private, public, public_edit, shared, or unlisted (default: private)'
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'List of tag strings'
        },
        slug: {
          type: 'string',
          description: 'Optional URL slug (auto-generated from title if omitted)'
        }
      },
      required: ['title']
    },
    execute: function (inputs) {
      return api('/items/new', {
        method: 'POST',
        body: JSON.stringify(inputs)
      }).then(function (item) {
        return textResult(
          'Created item ' + item.slug + ' (id ' + item.id + ', visibility ' + item.visibility + ').\n' +
          'View at /@' + (window.LISTHUB_USERNAME || 'me') + '/' + item.slug
        );
      });
    }
  });

  mc.registerTool({
    name: 'listhub_append_to_list',
    description:
      'Append a bullet entry to an existing list item. Use this to add a single ' +
      'item to a list without replacing all the content. The entry becomes a new ' +
      "line at the end of the item's markdown formatted as `- {entry}`.",
    inputSchema: {
      type: 'object',
      properties: {
        slug: { type: 'string', description: 'Slug of the list to append to' },
        entry: { type: 'string', description: 'Text of the bullet to add' }
      },
      required: ['slug', 'entry']
    },
    execute: function (inputs) {
      // We have to look up the id from slug first, then call the append endpoint
      return api('/items/by-slug/' + encodeURIComponent(inputs.slug))
        .then(function (item) {
          return api('/items/' + item.id + '/append', {
            method: 'POST',
            body: JSON.stringify({ entry: inputs.entry })
          });
        })
        .then(function (result) {
          return textResult('Appended to ' + inputs.slug + ' (revision ' + result.revision + ').');
        });
    }
  });

  mc.registerTool({
    name: 'listhub_upsert_item',
    description:
      'Create or update a ListHub item by slug. If an item with this slug ' +
      'already exists for the logged-in user, its content is updated and the ' +
      'revision bumps. Otherwise a new item is created. Idempotent — safe to ' +
      'call repeatedly. Use this when you want full control over the slug.',
    inputSchema: {
      type: 'object',
      properties: {
        slug: { type: 'string', description: 'Target slug (creates if missing)' },
        title: { type: 'string', description: 'Item title' },
        content: { type: 'string', description: 'Full markdown content' },
        item_type: {
          type: 'string',
          description: 'note, list, or document'
        },
        visibility: {
          type: 'string',
          description: 'private, public, public_edit, shared, or unlisted'
        },
        tags: {
          type: 'array',
          items: { type: 'string' }
        }
      },
      required: ['slug']
    },
    execute: function (inputs) {
      var slug = inputs.slug;
      var body = Object.assign({}, inputs);
      delete body.slug;
      return api('/items/by-slug/' + encodeURIComponent(slug), {
        method: 'PUT',
        body: JSON.stringify(body)
      }).then(function (item) {
        return textResult(
          'Upserted item ' + item.slug + ' (revision ' + item.revision + ', visibility ' + item.visibility + ').'
        );
      });
    }
  });

  mc.registerTool({
    name: 'listhub_set_visibility',
    description:
      "Change an item's visibility (private, public, public_edit, shared, or " +
      'unlisted). Owner-only operation. Use this to publish a draft or to take ' +
      'something private without changing its content.',
    inputSchema: {
      type: 'object',
      properties: {
        slug: { type: 'string', description: 'Slug of the item to update' },
        visibility: {
          type: 'string',
          description: 'New visibility: private, public, public_edit, shared, or unlisted'
        }
      },
      required: ['slug', 'visibility']
    },
    execute: function (inputs) {
      return api('/items/by-slug/' + encodeURIComponent(inputs.slug), {
        method: 'PUT',
        body: JSON.stringify({ visibility: inputs.visibility })
      }).then(function (item) {
        return textResult(
          'Set ' + inputs.slug + ' visibility to ' + item.visibility + '.'
        );
      });
    }
  });

  // ----- Page-context tools (only registered when relevant) ------------------

  // If the current page URL is /@username/<slug>, expose tools that already
  // know which item is being viewed. This lets the agent act on "this item"
  // without having to ask the user for the slug.
  var itemPageMatch = window.location.pathname.match(/^\/@([^\/]+)\/([^\/]+)$/);
  if (itemPageMatch) {
    var pageUser = itemPageMatch[1];
    var pageSlug = itemPageMatch[2];
    window.LISTHUB_USERNAME = pageUser;

    mc.registerTool({
      name: 'listhub_save_current_item_to_my_collection',
      description:
        'Fork the item currently being viewed into the logged-in user\'s own ' +
        'ListHub. Useful when the visitor wants to keep a copy of someone ' +
        "else's list under their own account. The new item is created with a " +
        'reference to the original.',
      inputSchema: { type: 'object', properties: {} },
      execute: function () {
        return api('/items/by-slug/' + encodeURIComponent(pageSlug)).then(function (orig) {
          var content =
            (orig.content || '') +
            '\n\n---\n*Forked from /@' + pageUser + '/' + pageSlug + '*';
          return api('/items/new', {
            method: 'POST',
            body: JSON.stringify({
              title: orig.title || pageSlug,
              content: content,
              item_type: orig.item_type,
              visibility: 'private',
              tags: (orig.tags || []).concat(['forked-from-' + pageUser])
            })
          });
        }).then(function (item) {
          return textResult(
            'Forked to your account as ' + item.slug + ' (private). ' +
            'Edit at /dash/edit/' + item.id
          );
        });
      }
    });
  }

  // Profile page: /@username (no further path)
  var profilePageMatch = window.location.pathname.match(/^\/@([^\/]+)\/?$/);
  if (profilePageMatch) {
    var profileUser = profilePageMatch[1];
    mc.registerTool({
      name: 'listhub_browse_user_items',
      description:
        "List the public items owned by the user whose profile is currently " +
        "being viewed (@" + profileUser + "). Returns the same data the profile " +
        "tree shows.",
      inputSchema: { type: 'object', properties: {} },
      execute: function () {
        return api('/items?owner=' + encodeURIComponent(profileUser)).then(jsonResult);
      }
    });
  }

  // Mark on the page that WebMCP is active so anyone inspecting can verify
  document.documentElement.setAttribute('data-listhub-webmcp', 'ready');
})();
