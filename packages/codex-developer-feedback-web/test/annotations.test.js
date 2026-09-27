import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canvasPoint } from '../src/annotations.js';
import { createItem } from '../src/core.js';
test('touch coordinates map to original screenshot after resizing and clamp captured pointer', () => {
  const rect = { left: 20, top: 80, width: 200, height: 400 };
  assert.deepEqual(canvasPoint({ clientX: 120, clientY: 280 }, rect, 400, 800), { x: 200, y: 400 });
  assert.deepEqual(canvasPoint({ clientX: -20, clientY: 600 }, rect, 400, 800), { x: 0, y: 800 });
});
test('large drawings retain bounds and separate stroke data without argument overflow', () => {
  const points = Array.from({length: 150000}, (_, i) => ({ x: i % 300, y: i % 800 }));
  const strokes = [{ tool: 'pen', points }];
  const item = createItem({sourceApp:'test', sourceDisplayName:'Test', environment:'dev'}, {screenshot:'data:image/png;base64,aA==',comment:'',points,strokes,width:400,height:800,pathname:'/'});
  assert.deepEqual(item.selectionBounds, {left:0, top:0, width:299,height:799});
  assert.equal(item.contextMetadata.annotations.strokes, strokes);
});
