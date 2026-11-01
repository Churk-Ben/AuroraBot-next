// 由 scripts/generate_ctx_contract.py 生成，来源为 aurora_api.contract 与 aurora_bot.conversation_contract。

export type ApiError = {
  code: string;
  message: string;
};

export type ConversationCancelRequest = {
  instance_id: string;
  run_id: string;
  session_id: string;
};

export type ConversationCancelResponse = {
  result: {
    cancelled: boolean;
    instance_id: string;
    run_id: string;
    session_id: string;
  };
};

export type ConversationInfoRequest = Record<string, never>;

export type ConversationInfoResponse = {
  result: {
    instance_ids: string[];
    session_id: string;
  };
};

export type ConversationQueryRequest = {
  instance_id: string;
  request_id: string;
  session_id: string;
};

export type ConversationQueryResponse = {
  result: {
    accepted: true;
    error: null | string;
    guidance_id: string;
    instance_id: string;
    request_id: string;
    run_id: string;
    run_status: 'cancelled' | 'completed' | 'failed' | 'pending';
    sequence: number;
    session_id: string;
  };
};

export type ConversationReceipt = {
  accepted: true;
  guidance_id: string;
  instance_id: string;
  request_id: string;
  run_id: string;
  sequence: number;
  session_id: string;
};

export type ConversationSubmitRequest = {
  instance_id: string;
  request_id: string;
  session_id: string;
  text: string;
};

export type ConversationSubmitResponse = {
  result: ConversationReceipt;
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
  conversationCancel: ConversationCancelRequest;
  conversationInfo: ConversationInfoRequest;
  conversationQuery: ConversationQueryRequest;
  conversationSubmit: ConversationSubmitRequest;
  delete: DeleteRequest;
  get: GetRequest;
  list: ListRequest;
  set: SetRequest;
}

export interface HttpResponses {
  conversationCancel: ConversationCancelResponse;
  conversationInfo: ConversationInfoResponse;
  conversationQuery: ConversationQueryResponse;
  conversationSubmit: ConversationSubmitResponse;
  delete: DeleteResponse;
  get: GetResponse;
  list: ListResponse;
  set: SetResponse;
}

export const HTTP_BINDINGS = {
  conversationCancel: {
    method: 'POST',
    path: '/conversation/cancel',
    operation: 'org.aurora.bot:operations/run/cancel',
  },
  conversationInfo: {
    method: 'POST',
    path: '/conversation/info',
    operation: null,
  },
  conversationQuery: {
    method: 'POST',
    path: '/conversation/query',
    operation: null,
  },
  conversationSubmit: {
    method: 'POST',
    path: '/conversation/submit',
    operation: 'org.aurora.bot:operations/run/submit',
  },
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
