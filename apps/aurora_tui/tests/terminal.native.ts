import assert from 'node:assert/strict';
// oxlint-disable-next-line vitest/no-import-node-test -- 原生 FFI 验收需要 Node 直接加载，不能经过 Vitest 转换。
import { test } from 'node:test';

import { createTestRenderer } from '@opentui/core/testing';

import { BOT, Workbench } from '../src/state/workbench.ts';
import { WorkbenchView } from '../src/ui/workbench-view.ts';
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
    view.conversation.scroll.scrollTo(0);
    await terminal.renderOnce();
    const offset = view.conversation.scroll.scrollTop;
    terminal.mockInput.pressKey('F12');
    await terminal.renderOnce();
    terminal.mockInput.pressEscape();
    await terminal.renderOnce();
    assert.equal(view.conversation.scroll.scrollTop, offset);
    terminal.mockInput.pressTab();
    await terminal.renderOnce();
    terminal.mockInput.pressTab();
    await terminal.renderOnce();
    assert.equal(view.conversation.scroll.scrollTop, offset);
    client.set({
      ...record,
      value: { execution_id: 'turn-one', text: Array.from({ length: 65 }, (_, i) => `输出行 ${i}`).join('\n') },
    });
    await terminal.renderOnce();
    assert.equal(view.conversation.scroll.scrollTop, offset);
    assert.match(terminal.captureCharFrame(), /新内容/);
    terminal.mockInput.pressKey('F3');
    await terminal.renderOnce();
    assert.ok(view.conversation.scroll.scrollTop > offset);
    terminal.resize(48, 18);
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), / {3}\? 帮助/);
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

test('帮助面板分栏、阻止底层操作，并保留问号输入、草稿和焦点', async () => {
  const terminal = await createTestRenderer({ width: 120, height: 32, kittyKeyboard: true });
  const client = new FakeClient();
  const model = new Workbench(client);
  const view = new WorkbenchView(terminal.renderer, model, () => {});
  try {
    await model.start();
    await settle();
    await terminal.renderOnce();
    const initial = terminal.captureCharFrame();
    assert.match(initial, / {3}\? 帮助/);
    assert.doesNotMatch(initial, /Ctrl\+C/);
    terminal.mockInput.pressKey('/', { shift: true });
    await terminal.renderOnce();
    const help = terminal.captureCharFrame();
    assert.match(help, /快捷键/);
    assert.match(help, /输入 +工作台 +运行/);
    assert.match(help, /Ctrl\+C/);
    assert.match(help, / {3}\? \/ Esc 关闭/);
    assert.equal(view.input.plainText, '');
    terminal.mockInput.pressTab();
    terminal.mockInput.pressEnter();
    terminal.mockInput.pressKey('x', { ctrl: true });
    await terminal.mockInput.pasteBracketedText('不应进入草稿');
    assert.equal(view.page, 'chat');
    assert.equal(view.input.plainText, '');
    assert.equal(client.sent.length, 0);
    assert.equal(client.cancelled.length, 0);
    terminal.mockInput.pressKey('ESCAPE');
    assert.equal(view.input.focused, true);
    await terminal.mockInput.pasteBracketedText('草稿');
    terminal.mockInput.pressKey('?');
    assert.equal(view.input.plainText, '草稿?');
    terminal.mockInput.pressKey('F12');
    terminal.resize(48, 18);
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /快捷键/);
    assert.match(terminal.captureCharFrame(), /Esc 关闭/);
    for (let line = 0; line < 40; line++) terminal.mockInput.pressArrow('down');
    await terminal.renderOnce();
    assert.match(terminal.captureCharFrame(), /核对运行结果/);
    terminal.mockInput.pressKey('?');
    assert.equal(view.input.plainText, '草稿?');
    assert.equal(view.input.focused, true);
    terminal.mockInput.pressTab();
    await terminal.mockInput.pasteBracketedText('run');
    terminal.mockInput.pressKey('F12');
    terminal.mockInput.pressTab();
    terminal.mockInput.pressKey('ESCAPE');
    assert.equal(view.page, 'state');
    assert.equal(view.statusPage.filter.value, 'run');
    assert.equal(view.statusPage.filter.focused, true);
  } finally {
    view.dispose();
    await model.close();
    await terminal.dispose();
  }
});
