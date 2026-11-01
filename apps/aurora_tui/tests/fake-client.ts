import type {
  ConversationCancelRequest,
  ConversationQueryRequest,
  ConversationQueryResponse,
  ConversationSubmitRequest,
  StateRecord,
  SubscriptionUpdate,
} from '@aurorabot/client';

import type { WorkbenchClient } from '../src/state/workbench.ts';

import { RemoteError } from '@aurorabot/client';

export class FakeClient implements WorkbenchClient {
  readonly cancelled: ConversationCancelRequest[] = [];
  closed = false;
  readonly conversation = {
    info: async () => ({ session_id: this.session, instance_ids: this.instances }),
    submit: async (request: ConversationSubmitRequest) => {
      this.sent.push(request);
      if (this.loseRequest) throw new TypeError('网络中断');
      const receipt = {
        session_id: request.session_id,
        instance_id: request.instance_id,
        request_id: request.request_id,
        guidance_id: `guide-${this.sent.length}`,
        sequence: this.sent.length,
        run_id: 'run-one',
        accepted: true as const,
      };
      this.receipts.set(request.request_id, { ...receipt, run_status: 'pending', error: null });
      if (this.loseResponse) throw new TypeError('响应丢失');
      return receipt;
    },
    query: async (request: ConversationQueryRequest) => {
      const receipt = this.receipts.get(request.request_id);
      if (!receipt) throw new RemoteError('not_found', '回执不存在', 404);
      return receipt;
    },
    cancel: async (request: ConversationCancelRequest) => {
      this.cancelled.push(request);
      for (const receipt of this.receipts.values())
        if (receipt.run_id === request.run_id) receipt.run_status = 'cancelled';
      return { ...request, cancelled: true };
    },
  };
  instances = ['main'];
  loseRequest = false;
  loseResponse = false;
  observer?: (update: SubscriptionUpdate) => void;
  readonly receipts = new Map<string, ConversationQueryResponse['result']>();
  records: StateRecord[] = [];
  readonly sent: ConversationSubmitRequest[] = [];

  session = 'host-one';

  async close(): Promise<void> {
    this.closed = true;
  }

  set(record: StateRecord): void {
    this.observer?.({
      type: 'change',
      change: { ...record, action: 'set', revision: 1, existed: false, previous: null },
    });
  }

  subscribe(_filters: object, observer: (update: SubscriptionUpdate) => void) {
    this.observer = observer;
    observer({ type: 'snapshot', records: this.records });
    observer({ type: 'status', status: { state: 'connected' } });
    return { ready: Promise.resolve(), status: { state: 'connected' as const } };
  }
}

export async function settle(): Promise<void> {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}
