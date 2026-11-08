<script setup lang="ts">
import { ref, watch } from 'vue';

import { KunButton, KunDrawer, KunInput } from '@kungal/ui-vue';
import { Link2, ShieldCheck } from '@lucide/vue';
import { storeToRefs } from 'pinia';

import { useWorkbenchStore } from '../../stores/workbench';

const store = useWorkbenchStore();
const { connectionVisible, connecting, state } = storeToRefs(store);
const { disconnect } = store;
const endpoint = ref(import.meta.env.DEV ? 'http://127.0.0.1:10270' : window.location.origin);
const token = ref('');
const error = ref('');
const origin = window.location.origin;
watch(connectionVisible, (visible) => {
  if (!visible) token.value = '';
});
async function connect() {
  if (connecting.value) return;
  error.value = '';
  try {
    const url = new URL(endpoint.value.trim());
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      !['', '/'].includes(url.pathname)
    )
      throw new Error('invalid');
  } catch {
    error.value = '请填写完整的 http(s)://主机:端口，不含路径';
    return;
  }
  if (!token.value.trim()) {
    error.value = '请输入访问令牌';
    return;
  }
  await store.connect(endpoint.value.trim(), () => {
    const credential = token.value;
    token.value = '';
    return credential;
  });
}
</script>

<template>
  <KunDrawer v-model="connectionVisible" title="连接你的 Aurora" size="md">
    <p class="muted connection-intro">连接一个正在运行的后端，开始你的工作。</p>
    <form class="connection-form" @submit.prevent="connect">
      <KunInput
        :model-value="endpoint"
        v-bind="{ 'data-testid': 'endpoint', autocomplete: 'url' }"
        @update:model-value="endpoint = String($event)"
        label="API 地址"
        :disabled="connecting"
        placeholder="http://127.0.0.1:10270"
      />
      <KunInput
        :model-value="token"
        v-bind="{ 'data-testid': 'token', autocomplete: 'off' }"
        @update:model-value="token = String($event)"
        label="访问令牌"
        type="password"
        :disabled="connecting"
        placeholder="输入当前后端的访问令牌"
      />
      <p class="credential-note"><ShieldCheck :size="17" />令牌仅用于本次连接，不会保存到浏览器。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="action-row">
        <KunButton type="submit" color="primary" :loading="connecting" :disabled="connecting">
          <Link2 :size="17" />{{ connecting ? '正在连接…' : '连接工作台' }}
        </KunButton>
        <KunButton v-if="state.connection !== 'closed'" variant="light" @click="disconnect()">断开</KunButton>
      </div>
    </form>
    <p v-if="state.notice" class="workspace-notice" role="status">{{ state.notice }}</p>
    <div class="connection-origin">
      <strong>浏览器来源</strong>
      <p>后端需允许当前来源：</p>
      <code>{{ origin }}</code>
      <p>localhost 和 127.0.0.1 是不同来源。</p>
    </div>
  </KunDrawer>
</template>
