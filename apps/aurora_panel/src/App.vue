<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, shallowRef, triggerRef, watch } from 'vue';

import Icon from './Icon.vue';
import { address, BOT, object, PanelWorkbench } from './workbench.ts';

const model = new PanelWorkbench();
const state = shallowRef(model.state);
const unlisten = model.listen(() => triggerRef(state));
const page = ref<'conversation' | 'state'>('conversation');
const showConnection = ref(true);
const connecting = ref(false);
const endpoint = ref(import.meta.env.DEV ? 'http://127.0.0.1:10270' : window.location.origin);
const token = ref('');
const origin = window.location.origin;
const drafts = reactive<Record<string, string>>({});
const draft = computed({
  get: () => drafts[`${state.value.url}/${state.value.instance}`] ?? '',
  set: (value: string) => {
    drafts[`${state.value.url}/${state.value.instance}`] = value;
  },
});
const filter = ref('');
const selectedAddress = ref('');
const feed = ref<HTMLElement>();
const follow = ref(true);
const statusNames = {
  accepted: '已接纳 · 运行中',
  cancelled: '已取消',
  closed: '未连接',
  completed: '已完成',
  connected: '已连接',
  connecting: '连接中',
  expired: '会话已失效',
  failed: '失败',
  missing: '未查到回执',
  reconnecting: '重新连接中',
  refreshing: '同步状态中',
  rejected: '未接纳',
  sending: '发送中',
  uncertain: '待核对',
};
const submissions = computed(() =>
  state.value.submissions.filter((item) => item.request.instance_id === state.value.instance),
);
const pending = computed(() => submissions.value.filter((item) => !item.receipt));
const groups = computed(() => {
  const identities = new Map<string, { id: string; session: string }>();
  for (const item of submissions.value)
    if (item.receipt)
      identities.set(`${item.receipt.session_id}/${item.receipt.run_id}`, {
        id: item.receipt.run_id,
        session: item.receipt.session_id,
      });
  for (const item of state.value.activities)
    if (item.instance === state.value.instance)
      identities.set(`${item.session}/${item.run}`, { id: item.run, session: item.session });
  return [...identities.values()].map((group) => ({
    ...group,
    messages: submissions.value.filter(
      (item) => item.receipt?.run_id === group.id && item.receipt.session_id === group.session,
    ),
    activities: state.value.activities.filter(
      (item) => item.run === group.id && item.session === group.session && item.instance === state.value.instance,
    ),
  }));
});
const records = computed(() =>
  state.value.records
    .filter((item) => `${item.id} ${JSON.stringify(item.location)}`.toLowerCase().includes(filter.value.toLowerCase()))
    .toSorted((a, b) => address(a).localeCompare(address(b))),
);
const selected = computed(
  () => records.value.find((item) => address(item) === selectedAddress.value) ?? records.value[0],
);
const history = computed(() => {
  const record = state.value.records.find(
    (item) => item.id === BOT.messages && item.location.instance_id === state.value.instance,
  );
  const messages = object(record?.value)?.messages;
  return Array.isArray(messages) ? messages : [];
});
const current = computed(() =>
  object(
    state.value.records.find((item) => item.id === BOT.run && item.location.instance_id === state.value.instance)
      ?.value,
  ),
);
const busy = computed(() => submissions.value.some((item) => item.status === 'sending'));
const json = (value: unknown) => JSON.stringify(value, null, 2);

async function connect() {
  if (connecting.value) return;
  connecting.value = true;
  const credential = token.value;
  token.value = '';
  await model.connect(endpoint.value.trim(), credential);
  connecting.value = false;
  if (state.value.ready) showConnection.value = false;
}

function submit() {
  if (model.submit(draft.value)) {
    draft.value = '';
    follow.value = true;
  }
}

function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    submit();
  }
}

function selectInstance(event: Event) {
  model.select((event.target as HTMLSelectElement).value);
}

function scroll() {
  if (feed.value) follow.value = feed.value.scrollHeight - feed.value.scrollTop - feed.value.clientHeight < 80;
}

watch(state, async () => {
  if (!follow.value) return;
  await nextTick();
  if (feed.value) feed.value.scrollTop = feed.value.scrollHeight;
});

const leave = () => {
  void model.disconnect();
};
window.addEventListener('pagehide', leave);
onBeforeUnmount(() => {
  unlisten();
  window.removeEventListener('pagehide', leave);
  leave();
});
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#" aria-label="Aurora 工作台" @click.prevent="page = 'conversation'"
        ><span class="brand-mark">A<span></span></span><span>Aurora<small>WORKSPACE</small></span></a
      >
      <div class="sidebar-caption">工作台</div>
      <nav aria-label="主导航">
        <button
          :class="{ active: page === 'conversation' }"
          :aria-current="page === 'conversation' ? 'page' : undefined"
          @click="page = 'conversation'"
        >
          <Icon name="chat" />交流<Icon class="nav-arrow" name="chevron" />
        </button>
        <button
          :class="{ active: page === 'state' }"
          :aria-current="page === 'state' ? 'page' : undefined"
          @click="page = 'state'"
        >
          <Icon name="state" />状态<span class="nav-count">{{ state.records.length }}</span>
        </button>
      </nav>
      <div class="instance-control">
        <label for="instance">当前 Bot</label
        ><select
          id="instance"
          :value="state.instance"
          :disabled="!state.instances.length || !state.ready"
          @change="selectInstance"
        >
          <option v-if="!state.instances.length" value="">等待连接</option>
          <option v-for="instance in state.instances" :key="instance">{{ instance }}</option>
        </select>
      </div>
      <div class="sidebar-bottom">
        <div class="connection-line">
          <span class="status-dot" :class="{ online: state.ready }"></span>{{ statusNames[state.connection] }}
        </div>
        <span class="endpoint" :title="state.url">{{ state.url || '尚未选择后端' }}</span
        ><button class="sidebar-settings" @click="showConnection = !showConnection">
          <Icon name="link" />连接设置
        </button>
        <div class="sidebar-footnote">与你的 Bot 保持同步</div>
      </div>
    </aside>

    <main>
      <header class="topbar">
        <div class="breadcrumb">工作台 <span>/</span> {{ page === 'conversation' ? '交流' : '状态' }}</div>
        <div class="topbar-right">
          <button class="icon-button" aria-label="连接设置" @click="showConnection = !showConnection">
            <Icon name="link" />
          </button>
          <span class="live-label"
            ><span class="status-dot" :class="{ online: state.ready }"></span
            >{{ state.ready ? '实时同步' : statusNames[state.connection] }}</span
          ><button
            class="icon-button"
            aria-label="核对后端状态"
            :disabled="state.connection !== 'connected'"
            @click="model.refresh()"
          >
            <Icon name="refresh" />
          </button>
        </div>
      </header>

      <section v-if="showConnection" class="connection-panel" aria-labelledby="connection-title">
        <div class="connection-intro">
          <span class="eyebrow">YOUR WORKSPACE, CONNECTED</span>
          <h1 id="connection-title">连接你的 Aurora</h1>
          <p>在浏览器中交流、观察运行，<br />让每一步都有迹可循。</p>
          <div class="connection-decoration" aria-hidden="true"><span></span><span></span><span></span><b>✦</b></div>
        </div>
        <form class="connection-form" @submit.prevent="connect">
          <div class="form-heading">
            <Icon name="link" />
            <h2>后端连接</h2>
          </div>
          <label for="endpoint">API 地址</label
          ><input
            id="endpoint"
            v-model="endpoint"
            type="url"
            required
            placeholder="https://aurora.example.com"
            autocomplete="url"
            :disabled="connecting"
          /><label for="token">访问令牌</label
          ><input
            id="token"
            v-model="token"
            type="password"
            required
            autocomplete="off"
            placeholder="输入当前后端的访问令牌"
            :disabled="connecting"
          />
          <p class="field-help">令牌仅用于本次连接，不会保存到浏览器。</p>
          <div class="form-actions">
            <button class="button primary" :disabled="connecting">
              {{ connecting ? '正在连接…' : '连接工作台' }}<Icon name="arrow" />
            </button>
            <button v-if="state.ready" type="button" class="button quiet" @click="showConnection = false">
              返回工作台
            </button>
            <button v-if="state.connection !== 'closed'" type="button" class="button quiet" @click="model.disconnect()">
              断开
            </button>
          </div>
          <p class="connection-hint">
            后端需允许此页面的来源：<code>{{ origin }}</code>
          </p>
        </form>
      </section>

      <div v-if="state.notice" class="notice" role="status">{{ state.notice }}</div>
      <div v-if="state.connection !== 'connected' && state.url && !showConnection" class="notice">
        连接尚未就绪，以下为最后观察到的内容。<button @click="showConnection = true">检查连接</button>
      </div>

      <section v-show="page === 'conversation' && !showConnection" class="conversation-page" aria-label="交流工作区">
        <div class="page-heading">
          <div>
            <span class="eyebrow">CONVERSATION</span>
            <h1>{{ state.instance || '交流' }}<span class="heading-tag">Bot</span></h1>
            <p>直接交流，共同推进。</p>
          </div>
          <button
            v-if="current?.status === 'running' && typeof current.run_id === 'string'"
            class="button stop"
            :disabled="!state.ready || state.cancelling"
            @click="model.cancel(String(current.run_id))"
          >
            <Icon name="stop" />{{ state.cancelling ? '正在停止…' : '停止运行' }}
          </button>
        </div>
        <div ref="feed" class="conversation-feed" @scroll="scroll">
          <details v-if="history.length" class="history">
            <summary>
              已保存的上下文 <span>{{ history.length }} 条</span>
            </summary>
            <p>来自后端保存的历史，可能包含工具与环境输入。</p>
            <pre>{{ json(history) }}</pre>
          </details>
          <div v-if="!groups.length && !pending.length" class="empty-conversation">
            <div class="empty-symbol"><Icon name="chat" /></div>
            <h2>从一个想法开始</h2>
            <p>告诉 {{ state.instance || 'Bot' }} 你想做什么。<br />运行过程和工具活动会在这里更新。</p>
            <div class="empty-chips">
              <span><span class="status-dot online"></span>实时观察</span><span>随时补充引导</span
              ><span>明确停止运行</span>
            </div>
          </div>
          <article v-for="group in groups" :key="`${group.session}/${group.id}`" class="run-group">
            <div class="run-heading">
              <span class="run-id">RUN / {{ group.id.slice(0, 8) }}</span
              ><span class="run-status">{{
                group.messages[0] ? statusNames[group.messages[0].status] : '观察到的运行'
              }}</span
              ><button
                v-if="group.session === state.session && group.messages.some((item) => item.status === 'accepted')"
                class="text-button"
                :disabled="!state.ready || state.cancelling"
                @click="model.cancel(group.id)"
              >
                停止
              </button>
            </div>
            <div v-for="message in group.messages" :key="message.request.request_id" class="message user-message">
              <span class="avatar user-avatar">你</span>
              <div>
                <div class="message-label">
                  你 <span>{{ statusNames[message.status] }}</span>
                </div>
                <p class="message-content">{{ message.request.text }}</p>
                <p v-if="message.error" class="error-text">{{ message.error }}</p>
              </div>
            </div>
            <div v-for="activity in group.activities" :key="activity.execution" class="message model-message">
              <span class="avatar bot-avatar">A</span>
              <div class="model-body">
                <div class="message-label">Aurora <span>模型过程</span></div>
                <p v-if="activity.text" class="message-content">{{ activity.text }}</p>
                <span v-else-if="!activity.tools.length" class="muted">等待模型输出…</span>
                <details v-if="activity.tools.length" class="tool-activity">
                  <summary>
                    工具活动
                    <span>{{ activity.tools.length }} 项{{ activity.results.length ? ' · 已返回结果' : '' }}</span>
                  </summary>
                  <pre>{{ json(activity.tools) }}</pre>
                  <template v-if="activity.results.length">
                    <h3>执行结果</h3>
                    <pre>{{ json(activity.results) }}</pre>
                  </template>
                </details>
              </div>
            </div>
          </article>
          <div v-for="message in pending" :key="message.request.request_id" class="message user-message pending">
            <span class="avatar user-avatar">你</span>
            <div>
              <div class="message-label">
                你 <span>{{ statusNames[message.status] }}</span>
              </div>
              <p class="message-content">{{ message.request.text }}</p>
              <p v-if="message.error" class="error-text">{{ message.error }}</p>
              <div v-if="['uncertain', 'missing'].includes(message.status)" class="recovery-actions">
                <button class="text-button" :disabled="!state.ready" @click="model.refresh()">核对状态</button>
                <button
                  class="text-button"
                  :disabled="!state.ready || message.request.session_id !== state.session"
                  @click="model.retry(message)"
                >
                  用原请求重试
                </button>
              </div>
            </div>
          </div>
        </div>
        <form class="composer" @submit.prevent="submit">
          <label class="sr-only" for="message">发送给 Bot 的消息</label
          ><textarea
            id="message"
            v-model="draft"
            rows="3"
            :disabled="!state.ready"
            :placeholder="state.ready ? '输入消息，或为正在进行的任务补充引导…' : '连接后即可开始交流'"
            @keydown="keydown"
          ></textarea>
          <div class="composer-bottom">
            <span>Enter 发送 <span class="separator">·</span> Shift + Enter 换行</span
            ><button class="button primary" :disabled="!state.ready || busy || !draft.trim()">
              发送<Icon name="send" />
            </button>
          </div>
        </form>
        <p class="conversation-footnote">模型文本展示运行过程；接纳消息不代表运行已完成。</p>
      </section>

      <section v-show="page === 'state' && !showConnection" class="state-page" aria-label="状态工作区">
        <div class="page-heading">
          <div>
            <span class="eyebrow">STATE EXPLORER</span>
            <h1>
              公开状态<span class="heading-tag">{{ state.records.length }}</span>
            </h1>
            <p>读取和订阅后端公开的数据。</p>
          </div>
          <span class="readonly-label">只读观察</span>
        </div>
        <label class="sr-only" for="state-filter">筛选状态</label
        ><input
          id="state-filter"
          v-model="filter"
          class="state-search"
          placeholder="按状态 ID 或位置筛选…"
          type="search"
        />
        <div class="state-browser">
          <div class="state-list" aria-label="状态地址">
            <button
              v-for="record in records"
              :key="address(record)"
              :class="{ selected: selected && address(selected) === address(record) }"
              @click="selectedAddress = address(record)"
            >
              <span>{{ record.id.split('/').at(-1) }}</span
              ><code>{{ record.id }}</code
              ><small>{{ json(record.location) }}</small>
            </button>
            <p v-if="!records.length" class="empty-state">
              {{ filter ? '没有匹配的状态。' : '后端尚未开放或写入状态。' }}
            </p>
          </div>
          <div class="state-detail">
            <template v-if="selected">
              <div class="state-detail-heading">
                <span>当前值</span><code>{{ selected.id }}</code>
              </div>
              <pre>{{ json(selected.value) }}</pre>
            </template>
            <div v-else class="empty-state">选择状态，查看当前值。</div>
          </div>
        </div>
      </section>
      <footer class="workspace-footer"><span>AURORA / WORKSPACE</span><span>交流 · 观察 · 继续</span></footer>
    </main>
  </div>
</template>
