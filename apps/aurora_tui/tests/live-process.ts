import assert from 'node:assert/strict';
import process from 'node:process';
import { setTimeout } from 'node:timers/promises';

import { CtxClient } from '@aurorabot/client';
import { createTestRenderer } from '@opentui/core/testing';

import { Workbench } from '../src/state/workbench.ts';
import { WorkbenchView } from '../src/ui/workbench-view.ts';

async function until(condition: () => boolean): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (!condition()) {
    assert.ok(Date.now() < deadline, '等待后端状态超时');
    await setTimeout(10);
  }
}

const url = process.argv[2];
assert.ok(url);
const terminal = await createTestRenderer({ width: 100, height: 30 });
const model = new Workbench(new CtxClient(url));
const view = new WorkbenchView(terminal.renderer, model, () => {});
const observer = new CtxClient(url);
try {
  await model.start();
  await until(() => model.ready);
  await terminal.mockInput.pasteBracketedText('开始工具调用');
  terminal.mockInput.pressEnter();
  await until(() => model.messages[0]?.status === 'accepted' && (model.groups[0]?.tools.size ?? 0) > 0);
  const first = model.messages[0]?.receipt;
  assert.ok(first);
  await terminal.mockInput.pasteBracketedText('继续等待，不要重复执行');
  terminal.mockInput.pressEnter();
  await until(() => model.messages[1]?.status === 'accepted');
  assert.equal(model.messages[1]?.receipt?.run_id, first.run_id);
  assert.notEqual(model.messages[1]?.receipt?.guidance_id, first.guidance_id);
  await terminal.renderOnce();
  assert.match(terminal.captureCharFrame(), /echo/);
  terminal.mockInput.pressTab();
  await terminal.renderOnce();
  assert.match(terminal.captureCharFrame(), /只读浏览/);
  assert.ok(model.records.size > 0);
  view.dispose();
  await model.close();
  const query = { session_id: first.session_id, instance_id: first.instance_id, request_id: first.request_id };
  const detached = await observer.conversation.query(query);
  assert.equal(detached.run_status, 'pending');
  const resumed = new Workbench(observer);
  const resumedView = new WorkbenchView(terminal.renderer, resumed, () => {});
  try {
    await resumed.start();
    await until(() => resumed.ready && Boolean(resumed.current()));
    terminal.mockInput.pressKey('x', { ctrl: true });
    await until(() => resumed.notice.includes('取消已确认'));
    const cancelled = await observer.conversation.query(query);
    assert.equal(cancelled.run_status, 'cancelled');
  } finally {
    resumedView.dispose();
    await resumed.close();
  }
} finally {
  view.dispose();
  await model.close();
  await observer.close();
  await terminal.dispose();
}
process.stdout.write(`${JSON.stringify({ event: 'complete' })}\n`);
