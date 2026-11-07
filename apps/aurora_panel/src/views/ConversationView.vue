<script setup lang="ts">
import { ref } from 'vue';

import { faComments, faStop } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { NButton, NCard, NCollapse, NCollapseItem, NEmpty, NText } from 'naive-ui';

import JsonViewer from '../components/common/JsonViewer.vue';
import MessageComposer from '../components/conversation/MessageComposer.vue';
import RunCard from '../components/conversation/RunCard.vue';
import SubmissionMessage from '../components/conversation/SubmissionMessage.vue';
import { useAutoScroll } from '../composables/useAutoScroll';
import { useConversation } from '../composables/useConversation';
import { useWorkbenchStore } from '../stores/workbench';

const store = useWorkbenchStore();
const { busy, current, groups, history, pending } = useConversation();
const feed = ref<HTMLElement>();
const { follow, onScroll } = useAutoScroll(feed, () => groups.value);
function submit() {
  if (store.submit()) follow();
}
</script>

<template>
  <section class="page-stack conversation-page" aria-label="交流工作区">
    <header class="page-heading">
      <div>
        <h1>{{ store.state.instance || '交流' }}</h1>
        <p>直接交流，观察模型与工具运行。</p>
      </div>
      <NButton
        v-if="current?.status === 'running' && typeof current.run_id === 'string'"
        type="warning"
        secondary
        :loading="store.state.cancelling"
        :disabled="!store.state.ready || store.state.cancelling"
        @click="store.cancel(String(current.run_id))"
      >
        <template #icon><FontAwesomeIcon :icon="faStop" /></template>停止运行
      </NButton>
    </header>
    <div ref="feed" class="conversation-feed" @scroll="onScroll">
      <NCard v-if="history.length" size="small">
        <NCollapse>
          <NCollapseItem :title="`已保存的上下文 · ${history.length} 条`" name="history">
            <NText depth="3">来自后端保存的历史，可能包含工具与环境输入。</NText><JsonViewer :value="history" />
          </NCollapseItem>
        </NCollapse>
      </NCard>
      <NCard v-if="!groups.length && !pending.length" class="empty-conversation">
        <NEmpty description="告诉 Bot 你想做什么，运行与工具活动会在这里更新。">
          <template #icon><FontAwesomeIcon :icon="faComments" /></template
          ><template #extra>
            <NButton v-if="!store.state.ready" type="primary" secondary @click="store.connectionVisible = true">
              连接后端
            </NButton>
          </template>
        </NEmpty>
      </NCard>
      <RunCard
        v-for="group in groups"
        :key="`${group.session}/${group.id}`"
        :group="group"
        :ready="store.state.ready"
        :session="store.state.session"
        :cancelling="store.state.cancelling"
        @cancel="store.cancel"
        @refresh="store.refresh"
        @retry="store.retry"
      />
      <NCard v-for="message in pending" :key="message.request.request_id" size="small">
        <SubmissionMessage
          :message="message"
          :ready="store.state.ready"
          :session="store.state.session"
          @refresh="store.refresh"
          @retry="store.retry"
        />
      </NCard>
    </div>
    <MessageComposer v-model="store.draft" :ready="store.state.ready" :busy="busy" @submit="submit" />
    <NText depth="3">接纳消息不代表运行完成；关闭页面只停止观察。</NText>
  </section>
</template>

<style scoped>
.conversation-feed {
  display: grid;
  gap: 16px;
  align-content: start;
  max-height: max(240px, calc(100dvh - 440px));
  padding-right: 4px;
  overflow: auto;
}

.empty-conversation {
  padding-block: 48px;
}

@media (width <= 600px) {
  .conversation-feed {
    max-height: max(200px, calc(100dvh - 560px));
  }
}
</style>
