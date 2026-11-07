import type { App as VueApp } from 'vue';

import { createApp, nextTick } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../src/App.vue';
import { FakeClient, settle } from './fake-client.ts';

const clients: FakeClient[] = [];
const prepared: FakeClient[] = [];
function createClient() {
  const client = prepared.shift() ?? new FakeClient();
  clients.push(client);
  return client;
}
vi.mock('@aurorabot/client', async (original) => {
  const actual = await original<typeof import('@aurorabot/client')>();
  return {
    ...actual,
    CtxClient: vi.fn(createClient),
  };
});

let app: undefined | VueApp;
function element<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`缺少元素：${selector}`);
  return node;
}
function input(selector: string, value: string) {
  const node = element<HTMLInputElement | HTMLTextAreaElement>(selector);
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
}
async function connect() {
  input('#endpoint', 'http://localhost:10270');
  input('#token', 'test-panel-runtime-token-1234567890');
  element('form.connection-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  await nextTick();
  const client = clients.at(-1);
  if (!client) throw new Error('未建立客户端');
  return client;
}

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  sessionStorage.clear();
  document.body.innerHTML = '<div id="test-app"></div>';
  app = createApp(App);
  app.mount('#test-app');
});
afterEach(async () => {
  app?.unmount();
  await settle();
  clients.length = 0;
  prepared.length = 0;
  // Vue 开发工具探测使用一次性计时器，页面轮询必须已停止。
  await vi.advanceTimersByTimeAsync(3000);
  vi.useRealTimers();
});

describe('浏览器工作台页面交互', () => {
  it('连接后清空令牌且不写入浏览器存储，页面卸载释放连接', async () => {
    await connect();
    expect(document.body.textContent).toContain('实时同步');
    element<HTMLButtonElement>('button[aria-label="连接设置"]').click();
    await nextTick();
    expect(element<HTMLInputElement>('#token').value).toBe('');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.documentElement.innerHTML).not.toContain('test-panel-runtime-token');
    app?.unmount();
    app = undefined;
    await settle();
    await vi.advanceTimersByTimeAsync(3000);
    expect(clients.every((client) => client.closed)).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('中文组字与换行不提交，Enter 只发送一次并清空草稿', async () => {
    const client = await connect();
    input('#message', '中文消息');
    const textarea = element<HTMLTextAreaElement>('#message');
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }));
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }));
    expect(client.sent).toHaveLength(0);
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await settle();
    await nextTick();
    expect(client.sent).toHaveLength(1);
    expect(client.sent[0]?.text).toBe('中文消息');
    expect(textarea.value).toBe('');
    expect(document.body.textContent).toContain('已接纳 · 运行中');
  });

  it('切页保留草稿，公开状态按地址筛选并将内容作为文本显示', async () => {
    const client = await connect();
    input('#message', '还没发送的草稿');
    client.emit({
      id: 'dev.panel:state/example',
      location: { instance_id: 'main' },
      value: '<img src=x onerror=alert(1)>',
    });
    element<HTMLButtonElement>('nav button:nth-child(2)').click();
    await nextTick();
    input('#state-filter', 'dev.panel');
    await nextTick();
    expect(element('.state-detail').textContent).toContain('<img src=x onerror=alert(1)>');
    expect(document.querySelector('.state-detail img')).toBeNull();
    element<HTMLButtonElement>('nav button:first-child').click();
    await nextTick();
    expect(element<HTMLTextAreaElement>('#message').value).toBe('还没发送的草稿');
    expect(client.sent).toHaveLength(0);
  });

  it('尚未完成的握手仍可断开，避免把用户锁在连接等待中', async () => {
    const client = new FakeClient();
    const pending = Promise.withResolvers<undefined>();
    client.subscribe = () => ({ ready: pending.promise, status: { state: 'connected' } });
    client.close = async () => {
      client.closed = true;
      pending.reject(new Error('已关闭'));
    };
    prepared.push(client);
    input('#endpoint', 'http://localhost:10270');
    input('#token', 'test-panel-runtime-token-1234567890');
    element('form.connection-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await settle();
    await nextTick();
    const disconnect = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent?.trim() === '断开',
    );
    if (!disconnect) throw new Error('缺少断开入口');
    expect(disconnect.disabled).toBe(false);
    disconnect.click();
    await settle();
    await nextTick();
    expect(element<HTMLButtonElement>('form.connection-form button.primary').disabled).toBe(false);
    expect(client.closed).toBe(true);
  });
});
