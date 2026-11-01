// 由 scripts/generate_ctx_contract.py 生成，请修改 aurora_api.contract 后重新生成。

export type ApiError = {
  code: string;
  message: string;
};

export type DeleteRequest = {
  key: StateId;
  location?: Location;
};

export type DeleteResponse = {
  result: boolean;
};

export type ErrorResponse = {
  error: ApiError;
};

export type GetRequest = {
  key: StateId;
  location?: Location;
};

export type GetResponse = {
  result: JsonValue;
};

export type JsonValue = boolean | JsonValue[] | null | number | string | { [key: string]: JsonValue };

export type ListRequest = {
  key?: StateId;
  location?: Location;
};

export type ListResponse = {
  result: StateAddress[];
};

export type Location = { [key: string]: string };

export type SetRequest = {
  key: StateId;
  location?: Location;
  value: JsonValue;
};

export type SetResponse = {
  result: null;
};

export type StateAddress = {
  id: StateId;
  location: Location;
};

export type StateChange = {
  action: 'delete' | 'set';
  existed: boolean;
  id: StateId;
  location: Location;
  previous: JsonValue;
  revision: number;
  value: JsonValue;
};

export type StateId = string;

export type WatchError = {
  error: ApiError;
  type: 'error';
};

export type WatchEvent = {
  data: StateChange;
  event: 'org.aurora.core:events/ctx/changed';
  type: 'event';
};

export type WatchMessage = WatchError | WatchEvent | WatchReady;

export type WatchReady = {
  type: 'ready';
};

export type WatchRequest = {
  key?: StateId;
  location?: Location;
};

export interface HttpRequests {
  delete: DeleteRequest;
  get: GetRequest;
  list: ListRequest;
  set: SetRequest;
}

export interface HttpResponses {
  delete: DeleteResponse;
  get: GetResponse;
  list: ListResponse;
  set: SetResponse;
}

export const HTTP_BINDINGS = {
  delete: {
    method: 'POST',
    path: '/ctx/delete',
    operation: 'org.aurora.core:operations/ctx/delete',
  },
  get: {
    method: 'POST',
    path: '/ctx/get',
    operation: 'org.aurora.core:operations/ctx/get',
  },
  list: {
    method: 'POST',
    path: '/ctx/list',
    operation: 'org.aurora.core:operations/ctx/list',
  },
  set: {
    method: 'POST',
    path: '/ctx/set',
    operation: 'org.aurora.core:operations/ctx/set',
  },
} as const;

export const WATCH_BINDING = {
  path: '/ctx/watch',
  subscribe: 'org.aurora.core:operations/ctx/subscribe',
  unsubscribe: 'org.aurora.core:operations/ctx/unsubscribe',
  event: 'org.aurora.core:events/ctx/changed',
} as const;
