// Deterministic event-order regression. This proves the barrier, not Chromium execution.
'use strict';
const assert = require('node:assert/strict');
const {pageLoadTracker} = require('./browser_page_load.cjs');
const tracker = pageLoadTracker(), previous = {id:'main',loaderId:'old-document'};
const navigate = (id,loaderId,parentId) => tracker.observe({method:'Page.frameNavigated',params:{frame:{id,loaderId,parentId}}});
const lifecycle = (frameId,loaderId,name='load') => tracker.observe({method:'Page.lifecycleEvent',params:{frameId,loaderId,name}});
navigate('main','old-document');lifecycle('main','old-document');
// The failing smoke's old document already contained admitted/rejected text after reload was requested.
assert.equal(tracker.reloaded(previous),false,'An old loaded document must not satisfy reopen');
navigate('subframe','subframe-document','main');lifecycle('subframe','subframe-document');
assert.equal(tracker.reloaded(previous),false,'A child frame load is not the main page reopening');
navigate('main','new-document');lifecycle('main','new-document','DOMContentLoaded');
assert.equal(tracker.reloaded(previous),false,'New document commit/DOMContentLoaded alone is not load completion');
lifecycle('main','old-document');
assert.equal(tracker.reloaded(previous),false,'A late old-loader load event must not qualify the new document');
lifecycle('main','new-document');
assert.equal(tracker.reloaded(previous),true,'Only the changed main loader with its own load event qualifies');
console.log('CDP reopen barrier rejects old documents, subframes and mismatched lifecycle events.');
