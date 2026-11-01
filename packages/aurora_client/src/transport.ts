import type {
  HttpRequests,
  HttpResponses,
  JsonValue,
  StateAddress,
  StateChange,
  WatchMessage,
} from './generated/ctx-contract.ts';

import { HTTP_BINDINGS, WATCH_BINDING } from './generated/ctx-contract.ts';

/** 服务端返回的公开错误；状态值和内部错误不拼入消息。 */
export class RemoteError extends Error {
  readonly code: string;
  readonly status?: number;

  constructor(code: string, message: string, status?: number) {
    super(`${code}: ${message}`);
    this.name = 'RemoteError';
    this.code = code;
    this.status = status;
  }
}

export class ProtocolError extends Error {
  constructor() {
    super('API 返回了无效的 ctx 传输数据');
    this.name = 'ProtocolError';
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 拒绝 JSON.stringify 会静默丢弃或转换的数据，并隔离调用者的可变对象。 */
function jsonValue(value: unknown, parents = new Set<object>()): JsonValue {
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string' && value.isWellFormed()) return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'object' || value === null || parents.has(value)) {
    throw new TypeError('请求或响应必须是可编码为 UTF-8 的有限 JSON 数据');
  }
  parents.add(value);
  try {
    if (Array.isArray(value)) {
      return Array.from(value, (item: unknown) => jsonValue(item, parents));
    }
    if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) {
      throw new TypeError('JSON 对象必须是普通对象');
    }
    if (Object.getOwnPropertySymbols(value).length > 0) throw new TypeError('JSON 对象不支持 Symbol 键');
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => {
        if (!key.isWellFormed()) throw new TypeError('JSON 对象键不能包含孤立代理字符');
        return [key, jsonValue(item, parents)];
      }),
    );
  } finally {
    parents.delete(value);
  }
}

export function encodeRequest(request: object): string {
  const fields = { ...request } as Record<string, unknown>;
  if (fields.key === undefined) delete fields.key;
  if (fields.location === undefined) delete fields.location;
  return JSON.stringify(jsonValue(fields));
}

function decode(text: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(text);
    const checked = jsonValue(value);
    if (record(checked)) return checked;
  } catch {
    throw new ProtocolError();
  }
  throw new ProtocolError();
}

function checkError(body: Record<string, unknown>, status?: number): void {
  if (!Object.hasOwn(body, 'error')) return;
  const error = body.error;
  if (!record(error) || typeof error.code !== 'string' || typeof error.message !== 'string') {
    throw new ProtocolError();
  }
  throw new RemoteError(error.code, error.message, status);
}

function address(value: unknown): value is StateAddress {
  return (
    record(value) &&
    typeof value.id === 'string' &&
    record(value.location) &&
    Object.entries(value.location).every(([key, item]) => key.length > 0 && typeof item === 'string' && item.length > 0)
  );
}

function change(value: unknown): value is StateChange {
  return (
    address(value) &&
    'revision' in value &&
    Number.isSafeInteger(value.revision) &&
    Number(value.revision) > 0 &&
    'action' in value &&
    (value.action === 'set' || value.action === 'delete') &&
    'existed' in value &&
    typeof value.existed === 'boolean' &&
    Object.hasOwn(value, 'value') &&
    Object.hasOwn(value, 'previous')
  );
}

export function decodeMessage(text: unknown): WatchMessage {
  if (typeof text !== 'string') throw new ProtocolError();
  const body = decode(text);
  if (body.type === 'error') checkError(body);
  if (body.type === 'ready') return { type: 'ready' };
  if (body.type === 'event' && body.event === WATCH_BINDING.event && change(body.data)) {
    return { type: 'event', event: WATCH_BINDING.event, data: body.data };
  }
  throw new ProtocolError();
}

/** HTTP 请求不重试；关闭会中止并等待所有在途请求。 */
export class Transport {
  readonly url: string;
  private readonly lifetime = new AbortController();
  private readonly pending = new Set<Promise<unknown>>();
  private readonly timeoutMs: number;

  constructor(url: string, timeoutMs: number) {
    const parsed = new URL(url);
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== '/' ||
      parsed.search ||
      parsed.hash
    ) {
      throw new TypeError('连接地址须为 http(s)://主机:端口');
    }
    this.url = parsed.origin;
    this.timeoutMs = timeoutMs;
  }

  async close(): Promise<void> {
    this.lifetime.abort(new Error('客户端已关闭'));
    await Promise.allSettled(this.pending);
  }

  request<Action extends keyof HttpRequests>(
    action: Action,
    request: HttpRequests[Action],
    signal?: AbortSignal,
  ): Promise<HttpResponses[Action]['result']> {
    const task = this.send(action, request, signal);
    this.pending.add(task);
    void task.then(
      () => this.pending.delete(task),
      () => this.pending.delete(task),
    );
    return task;
  }

  private async send<Action extends keyof HttpRequests>(
    action: Action,
    request: HttpRequests[Action],
    signal?: AbortSignal,
  ): Promise<HttpResponses[Action]['result']> {
    this.lifetime.signal.throwIfAborted();
    const deadline = new AbortController();
    const timer = setTimeout(() => deadline.abort(new Error('ctx 请求超时')), this.timeoutMs);
    const signals = [this.lifetime.signal, deadline.signal];
    if (signal) signals.push(signal);
    try {
      const binding = HTTP_BINDINGS[action];
      const response = await fetch(this.url + binding.path, {
        method: binding.method,
        headers: { 'Content-Type': 'application/json' },
        body: encodeRequest(request),
        redirect: 'error',
        signal: AbortSignal.any(signals),
      });
      const body = decode(await response.text());
      checkError(body, response.status);
      if (response.status !== 200 || !Object.hasOwn(body, 'result')) throw new ProtocolError();
      const result = body.result;
      if (
        (action === 'set' && result !== null) ||
        (action === 'delete' && typeof result !== 'boolean') ||
        (action === 'list' && (!Array.isArray(result) || !result.every((item: unknown) => address(item))))
      ) {
        throw new ProtocolError();
      }
      return result as HttpResponses[Action]['result'];
    } finally {
      clearTimeout(timer);
    }
  }
}
