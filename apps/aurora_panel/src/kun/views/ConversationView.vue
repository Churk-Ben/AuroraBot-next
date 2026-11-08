<script setup lang="ts">
import { nextTick, ref } from 'vue';

import { KunButton, KunTextarea } from '@kungal/ui-vue';
import {
  ArrowUp,
  AudioLines,
  ChevronRight,
  Code2,
  Compass,
  History,
  Lightbulb,
  Link2,
  Square,
  Wrench,
} from '@lucide/vue';

import { useAutoScroll } from '../../composables/useAutoScroll';
import { useConversation } from '../../composables/useConversation';
import { useWorkbenchStore } from '../../stores/workbench';
import SubmissionMessage from '../components/SubmissionMessage.vue';

const store = useWorkbenchStore();
const { busy, current, groups, history, pending } = useConversation();
const feed = ref<HTMLElement>();
const composer = ref<InstanceType<typeof KunTextarea>>();
const { follow, onScroll } = useAutoScroll(feed, () => groups.value);
const starters = [
  { icon: Compass, title: '梳理一个计划', text: '帮我把一个想法拆成可以执行的步骤。', caption: '把想法变成下一步' },
  { icon: Code2, title: '一起解决问题', text: '我遇到了一个问题，想和你一起分析。', caption: '从线索里找到答案' },
  { icon: Lightbulb, title: '探索新的可能', text: '我们来聊聊一个新想法。', caption: '为灵感留一点空间' },
];
function choose(text: string) {
  if (!store.state.ready) {
    store.connectionVisible = true;
    return;
  }
  store.draft = text;
  composer.value?.focus();
}
async function submit() {
  await nextTick();
  if (store.submit()) follow();
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    submit();
  }
}
</script>

<template>
  <section class="conversation-page" aria-label="交流工作区">
    <div ref="feed" class="conversation-feed" @scroll="onScroll">
      <div class="feed-inner">
        <details v-if="history.length" class="activity-details saved-context">
          <summary><History :size="16" />已保存的上下文 · {{ history.length }} 条</summary>
          <p class="muted">来自后端保存的历史，可能包含工具与环境输入。</p>
          <pre>{{ JSON.stringify(history, null, 2) }}</pre>
        </details>
        <div v-if="!groups.length && !pending.length" class="conversation-welcome">
          <div class="welcome-symbol"><AudioLines :size="34" :stroke-width="1.5" /></div>
          <span class="eyebrow">一点灵感，无限可能</span>
          <h1>今天，我们一起做点什么？</h1>
          <p>聊一个想法，解决一个问题，或让 Aurora 帮你迈出第一步。</p>
          <KunButton v-if="!store.state.ready" color="primary" @click="store.connectionVisible = true">
            <Link2 :size="17" />连接你的 Aurora<ChevronRight :size="16" />
          </KunButton>
          <div class="starter-grid">
            <button
              v-for="starter in starters"
              :key="starter.title"
              class="starter-card"
              type="button"
              @click="choose(starter.text)"
            >
              <component :is="starter.icon" :size="21" />
              <strong>{{ starter.title }}</strong
              ><span>{{ starter.caption }}</span>
            </button>
          </div>
        </div>
        <section v-for="group in groups" :key="`${group.session}/${group.id}`" class="run-group" aria-label="运行记录">
          <div class="run-divider">
            <span>运行 {{ group.id.slice(0, 8) }}</span>
            <KunButton
              v-if="group.session === store.state.session && group.messages.some((item) => item.status === 'accepted')"
              size="sm"
              variant="light"
              color="warning"
              :disabled="!store.state.ready || store.state.cancelling"
              @click="store.cancel(group.id)"
            >
              <Square :size="12" />停止
            </KunButton>
          </div>
          <SubmissionMessage v-for="message in group.messages" :key="message.request.request_id" :message="message" />
          <article v-for="activity in group.activities" :key="activity.execution" class="message assistant-message">
            <span class="message-avatar bot-avatar"><AudioLines :size="18" /></span>
            <div class="message-body">
              <div class="message-byline"><strong>Aurora</strong><span>模型过程</span></div>
              <div v-if="activity.text" class="message-text">{{ activity.text }}</div>
              <p v-else-if="!activity.tools.length" class="muted">等待模型输出…</p>
              <details v-if="activity.tools.length" class="activity-details">
                <summary>
                  <Wrench :size="15" />工具活动 · {{ activity.tools.length }} 项<ChevronRight :size="14" />
                </summary>
                <h3>调用</h3>
                <pre>{{ JSON.stringify(activity.tools, null, 2) }}</pre>
                <h3>结果</h3>
                <pre>{{ JSON.stringify(activity.results, null, 2) }}</pre>
              </details>
            </div>
          </article>
        </section>
        <SubmissionMessage v-for="message in pending" :key="message.request.request_id" :message="message" />
      </div>
    </div>
    <div class="composer-dock">
      <div v-if="current?.status === 'running' && typeof current.run_id === 'string'" class="running-bar">
        <span>Aurora 正在运行</span>
        <KunButton
          size="sm"
          variant="light"
          color="warning"
          :disabled="!store.state.ready || store.state.cancelling"
          :loading="store.state.cancelling"
          @click="store.cancel(String(current.run_id))"
        >
          <Square :size="13" />停止运行
        </KunButton>
      </div>
      <form class="composer" @submit.prevent="submit" @keydown="keydown">
        <KunTextarea
          :key="`${store.state.url}/${store.state.instance}`"
          ref="composer"
          v-model="store.draft"
          label="发送给 Bot 的消息"
          :rows="3"
          resize="none"
          auto-grow
          max-height="200px"
          :disabled="!store.state.ready"
          :placeholder="store.state.ready ? '有什么想法？和 Aurora 聊聊…' : '连接 Aurora 后，在这里开始交流…'"
        />
        <div class="composer-bottom">
          <span class="composer-hint">Enter 发送 <span>· Shift + Enter 换行</span></span>
          <KunButton
            color="primary"
            type="submit"
            is-icon-only
            aria-label="发送消息"
            :disabled="!store.state.ready || busy || !store.draft.trim()"
          >
            <ArrowUp :size="20" />
          </KunButton>
        </div>
      </form>
      <p class="composer-footnote">接纳消息不代表运行完成 · 关闭页面只停止观察</p>
    </div>
  </section>
</template>
