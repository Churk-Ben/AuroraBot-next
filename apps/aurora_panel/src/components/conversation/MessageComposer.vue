<script setup lang="ts">
import { faPaperPlane } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { NButton, NCard, NInput, NText } from 'naive-ui';

defineProps<{ busy: boolean; ready: boolean }>();
const emit = defineEmits<{ submit: [] }>();
const draft = defineModel<string>({ required: true });
function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    emit('submit');
  }
}
</script>

<template>
  <NCard size="small">
    <form class="composer" @submit.prevent="emit('submit')">
      <NInput
        v-model:value="draft"
        type="textarea"
        :input-props="{ id: 'message', 'aria-label': '发送给 Bot 的消息' }"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="!ready"
        :placeholder="ready ? '输入消息，或为正在进行的任务补充引导…' : '连接后即可开始交流'"
        @keydown="keydown"
      />
      <div class="composer-actions">
        <NText depth="3">Enter 发送 · Shift + Enter 换行</NText
        ><NButton type="primary" attr-type="submit" :disabled="!ready || busy || !draft.trim()">
          <template #icon><FontAwesomeIcon :icon="faPaperPlane" /></template>发送
        </NButton>
      </div>
    </form>
  </NCard>
</template>

<style scoped>
.composer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}
</style>
