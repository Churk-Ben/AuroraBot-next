import type { Submission } from '../types/workbench.ts';

import { computed, onScopeDispose, reactive, ref, shallowRef, triggerRef } from 'vue';

import { defineStore } from 'pinia';

import { PanelWorkbench } from '../services/workbench.ts';

/** 跨页面共享一个连接所有者；凭证、草稿和请求均不持久化。 */
export const useWorkbenchStore = defineStore('workbench', () => {
  const service = new PanelWorkbench();
  const state = shallowRef(service.state);
  const unlisten = service.listen(() => triggerRef(state));
  const connectionVisible = ref(true);
  const connecting = ref(false);
  const drafts = reactive<Record<string, string>>({});
  const draft = computed({
    get: () => drafts[`${state.value.url}/${state.value.instance}`] ?? '',
    set: (value: string) => {
      drafts[`${state.value.url}/${state.value.instance}`] = value;
    },
  });

  async function connect(url: string, readToken: () => string): Promise<void> {
    if (connecting.value) return;
    connecting.value = true;
    try {
      await service.connect(url, readToken());
      if (state.value.ready) connectionVisible.value = false;
    } finally {
      connecting.value = false;
    }
  }

  function submit(): boolean {
    if (!service.submit(draft.value)) return false;
    draft.value = '';
    return true;
  }

  onScopeDispose(() => {
    unlisten();
    void service.disconnect();
  });

  return {
    state,
    drafts,
    draft,
    connecting,
    connectionVisible,
    connect,
    submit,
    cancel: (run: string) => service.cancel(run),
    disconnect: () => service.disconnect(),
    refresh: () => service.refresh(),
    retry: (message: Submission) => service.retry(message),
    select: (instance: string) => service.select(instance),
  };
});
