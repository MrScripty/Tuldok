// Test-only CDP fresh-document barrier; DOM state from the old page is not proof of reopening.
'use strict';
function pageLoadTracker() {
  const mainLoaders = new Map(), loaded = new Set();
  const identity = (frame, loader) => JSON.stringify([frame, loader]);
  return {
    observe(message) {
      if(message.method === 'Page.frameNavigated' && !message.params.frame.parentId) {
        const {id,loaderId} = message.params.frame;
        mainLoaders.set(id,loaderId);
      }
      if(message.method === 'Page.lifecycleEvent' && message.params.name === 'load') {
        const {frameId,loaderId} = message.params;
        loaded.add(identity(frameId,loaderId));
      }
    },
    reloaded(previous) {
      const loader = mainLoaders.get(previous.id);
      return Boolean(loader && loader !== previous.loaderId && loaded.has(identity(previous.id,loader)));
    }
  };
}
module.exports = {pageLoadTracker};
