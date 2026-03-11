// Milkdown entry point for bundling
import { Editor, rootCtx, defaultValueCtx } from '@milkdown/core';
import { commonmark } from '@milkdown/preset-commonmark';
import { history } from '@milkdown/plugin-history';
import { listener, listenerCtx } from '@milkdown/plugin-listener';

// Export everything needed
export { Editor, rootCtx, defaultValueCtx, commonmark, history, listener, listenerCtx };

// Also expose a simple init function
export async function createMilkdownEditor(container, initialContent, onUpdate) {
    const editor = await Editor.make()
        .config((ctx) => {
            ctx.set(rootCtx, container);
            ctx.set(defaultValueCtx, initialContent || '');
        })
        .use(commonmark)
        .use(history)
        .use(listener)
        .create();

    if (onUpdate) {
        editor.action((ctx) => {
            ctx.get(listenerCtx).markdownUpdated((ctx, markdown, prevMarkdown) => {
                onUpdate(markdown);
            });
        });
    }

    return editor;
}
