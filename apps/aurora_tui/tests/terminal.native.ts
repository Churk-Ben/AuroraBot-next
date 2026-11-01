import assert from 'node:assert/strict';
// oxlint-disable-next-line vitest/no-import-node-test -- 原生 FFI 验收需要 Node 直接加载，不能经过 Vitest 转换。
import { test } from 'node:test';

import { createTestRenderer } from '@opentui/core/testing';

import { WorkbenchView } from '../src/view.ts';
import { BOT, Workbench } from '../src/workbench.ts';
import { FakeClient, settle } from './fake-client.ts';

test('真实终端渲染保留草稿、切页焦点、工具展开与滚动位置', async () => {
  const terminal = await createTestRenderer({ width: 100, height: 30, kittyKeyboard: true });
  const client = new FakeClient();
  const model = new Workbench(client);
  let quit = false;
  const view = new WorkbenchView(terminal.renderer, model, () => {
    quit = true;
  });
  try {
    await model.start();
    await settle();
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /AURORA/);
    await terminal.mockInput.pasteBracketedText('保留草稿\n第二行');
    terminal.mockInput.pressTab();
    await terminal.renderOnce();
    assert.equal(view.page, 'state');
    assert.equal(view.input.plainText, '保留草稿\n第二行');
    assert.match(terminal.captureCharFrame(), /只读浏览/);
    terminal.mockInput.pressTab();
    terminal.mockInput.pressEnter();
    await settle();
    assert.equal(client.sent[0]?.text, '保留草稿\n第二行');
    assert.equal(view.input.plainText, '');
    const record = { id: BOT.work, location: { instance_id: 'main', run_id: 'run-one', part: 'model_output' } };
    client.set({
      ...record,
      value: {
        execution_id: 'turn-one',
        text: '流式输出',
        tool_calls: [{ id: 'call', name: 'echo', arguments: { text: '参数详情' } }],
      },
    });
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /echo/);
    assert.doesNotMatch(terminal.captureCharFrame(), /参数详情/);
    terminal.mockInput.pressKey('t', { ctrl: true });
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /参数详情/);
    client.set({
      ...record,
      value: { execution_id: 'turn-one', text: Array.from({ length: 60 }, (_, i) => `输出行 ${i}`).join('\n') },
    });
    await terminal.renderOnce();
    view.chat.scrollTo(0);
    await terminal.renderOnce();
    const offset = view.chat.scrollTop;
    terminal.mockInput.pressTab();
    await terminal.renderOnce();
    terminal.mockInput.pressTab();
    await terminal.renderOnce();
    assert.equal(view.chat.scrollTop, offset);
    client.set({
      ...record,
      value: { execution_id: 'turn-one', text: Array.from({ length: 65 }, (_, i) => `输出行 ${i}`).join('\n') },
    });
    await terminal.renderOnce();
    assert.equal(view.chat.scrollTop, offset);
    assert.match(terminal.captureCharFrame(), /新内容/);
    terminal.mockInput.pressKey('F3');
    await terminal.renderOnce();
    assert.ok(view.chat.scrollTop > offset);
    terminal.resize(48, 18);
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /Ctrl\+C/);
    terminal.mockInput.pressCtrlC();
    assert.equal(quit, true);
  } finally {
    view.dispose();
    await model.close();
    await terminal.dispose();
  }
  assert.equal(client.closed, true);
  assert.equal(client.cancelled.length, 0);
});
