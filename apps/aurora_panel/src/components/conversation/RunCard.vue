<script setup lang="ts">
import type { RunGroup, Submission } from '../../types/workbench';

import { faStop } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { NAvatar, NButton, NCard, NThing } from 'naive-ui';

import SubmissionMessage from './SubmissionMessage.vue';
import ToolActivity from './ToolActivity.vue';

defineProps<{ cancelling: boolean; group: RunGroup; ready: boolean; session: string }>();
const emit = defineEmits<{ cancel: [run: string]; refresh: []; retry: [message: Submission] }>();
</script>

<template>
  <NCard size="small" :title="`运行 ${group.id.slice(0, 8)}`" class="run-card">
    <template #header-extra>
      <NButton
        v-if="group.session === session && group.messages.some((item) => item.status === 'accepted')"
        size="small"
        secondary
        type="warning"
        :disabled="!ready || cancelling"
        @click="emit('cancel', group.id)"
      >
        <template #icon><FontAwesomeIcon :icon="faStop" /></template>停止
      </NButton>
    </template>
    <div class="run-messages">
      <SubmissionMessage
        v-for="message in group.messages"
        :key="message.request.request_id"
        :message="message"
        :ready="ready"
        :session="session"
        @refresh="emit('refresh')"
        @retry="emit('retry', $event)"
      />
      <NThing v-for="activity in group.activities" :key="activity.execution" content-indented>
        <template #avatar><NAvatar round size="small" color="#326656">A</NAvatar></template>
        <template #header>Aurora</template>
        <template #description>模型过程</template>
        <div v-if="activity.text" class="text-content">{{ activity.text }}</div>
        <span v-else-if="!activity.tools.length" class="muted">等待模型输出…</span>
        <ToolActivity v-if="activity.tools.length" :tools="activity.tools" :results="activity.results" />
      </NThing>
    </div>
  </NCard>
</template>

<style scoped>
.run-card {
  min-width: 0;
}

.run-messages {
  display: grid;
  gap: 24px;
}
</style>
