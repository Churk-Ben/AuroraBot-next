<script setup lang="ts">
import type { Submission } from '../../types/workbench';

import { NAlert, NAvatar, NButton, NSpace, NTag, NThing } from 'naive-ui';

import { statusNames } from '../../constants/status';

defineProps<{ message: Submission; ready: boolean; session: string }>();
const emit = defineEmits<{ refresh: []; retry: [message: Submission] }>();
</script>

<template>
  <NThing class="submission-message" content-indented>
    <template #avatar><NAvatar class="user-avatar" round size="small">你</NAvatar></template>
    <template #header>你</template>
    <template #description>
      <NTag size="small" :bordered="false">{{ statusNames[message.status] }}</NTag>
    </template>
    <div class="text-content">{{ message.request.text }}</div>
    <NAlert v-if="message.error" type="warning" class="message-error">{{ message.error }}</NAlert>
    <template v-if="['uncertain', 'missing'].includes(message.status)" #action>
      <NSpace>
        <NButton size="small" :disabled="!ready" @click="emit('refresh')">核对状态</NButton
        ><NButton
          size="small"
          :disabled="!ready || message.request.session_id !== session"
          @click="emit('retry', message)"
        >
          用原请求重试
        </NButton>
      </NSpace>
    </template>
  </NThing>
</template>

<style scoped>
.user-avatar {
  color: #181818;
  background-color: var(--aurora-complement);
}

.submission-message {
  min-width: 0;
}

.message-error {
  margin-top: 12px;
}
</style>
