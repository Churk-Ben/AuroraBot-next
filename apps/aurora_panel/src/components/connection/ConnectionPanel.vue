<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui';

import { reactive, ref, toRefs } from 'vue';

import { faLink } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { NAlert, NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSpace, NText } from 'naive-ui';
import { storeToRefs } from 'pinia';

import { useWorkbenchStore } from '../../stores/workbench';

const store = useWorkbenchStore();
const { connectionVisible, connecting, state } = storeToRefs(store);
const { disconnect } = store;
const formRef = ref<FormInst>();
const fields = reactive({
  endpoint: import.meta.env.DEV ? 'http://127.0.0.1:10270' : window.location.origin,
  token: '',
});
const { endpoint, token } = toRefs(fields);
function clearToken() {
  fields.token = '';
}
const origin = window.location.origin;
const rules: FormRules = {
  endpoint: [
    { required: true, message: '请输入 API 地址', trigger: ['input', 'blur'] },
    {
      validator: (_rule, value: string) => {
        try {
          const url = new URL(value.trim());
          return (
            ['http:', 'https:'].includes(url.protocol) &&
            !url.username &&
            !url.password &&
            !url.search &&
            !url.hash &&
            ['', '/'].includes(url.pathname)
          );
        } catch {
          return false;
        }
      },
      message: '请填写完整的 http(s)://主机:端口，不含路径',
      trigger: 'blur',
    },
  ],
  token: { required: true, message: '请输入访问令牌', trigger: 'blur' },
};

async function connect() {
  if (store.connecting) return;
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  await store.connect(fields.endpoint.trim(), () => {
    const credential = fields.token;
    fields.token = '';
    return credential;
  });
}
</script>

<template>
  <NDrawer
    v-model:show="connectionVisible"
    :width="480"
    :style="{ maxWidth: '100vw' }"
    :auto-focus="true"
    @after-leave="clearToken"
  >
    <NDrawerContent title="连接你的 Aurora" closable>
      <NForm
        ref="formRef"
        class="connection-form"
        :model="fields"
        :rules="rules"
        :disabled="connecting"
        @submit.prevent="connect"
      >
        <NFormItem label="API 地址" path="endpoint" :label-props="{ for: 'endpoint' }">
          <NInput
            v-model:value="endpoint"
            :input-props="{ id: 'endpoint', autocomplete: 'url' }"
            placeholder="http://127.0.0.1:10270"
          />
        </NFormItem>
        <NFormItem label="访问令牌" path="token" :label-props="{ for: 'token' }">
          <NInput
            v-model:value="token"
            type="password"
            show-password-on="click"
            :input-props="{ id: 'token', autocomplete: 'off' }"
            placeholder="输入当前后端的访问令牌"
          />
        </NFormItem>
        <NText depth="3">令牌仅用于本次连接，不会保存到浏览器。</NText>
        <NSpace class="connection-actions">
          <NButton type="primary" attr-type="submit" :loading="connecting" :disabled="connecting">
            <template #icon><FontAwesomeIcon :icon="faLink" /></template>{{ connecting ? '正在连接…' : '连接工作台' }}
          </NButton>
          <NButton v-if="state.connection !== 'closed'" :disabled="false" @click="disconnect()"> 断开 </NButton>
        </NSpace>
      </NForm>
      <NAlert v-if="state.notice" type="warning" class="connection-help">{{ state.notice }}</NAlert>
      <NAlert type="info" title="浏览器来源" class="connection-help">
        后端需允许当前来源：<code class="text-content">{{ origin }}</code
        >。localhost 和 127.0.0.1 是不同来源。
      </NAlert>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.connection-actions {
  margin-top: 24px;
}

.connection-help {
  margin-top: 20px;
}
</style>
