<script setup lang="ts">
import type { MenuOption } from 'naive-ui';

import { computed, h, ref } from 'vue';
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router';

import { faComments, faDatabase, faLink, faRotate } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import {
  NAlert,
  NButton,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NSelect,
  NSpace,
  NTag,
  NTooltip,
} from 'naive-ui';

import ConnectionPanel from '../components/connection/ConnectionPanel.vue';
import { useCompactLayout } from '../composables/useCompactLayout';
import { statusNames } from '../constants/status';
import { useWorkbenchStore } from '../stores/workbench';

const store = useWorkbenchStore();
const route = useRoute();
const router = useRouter();
const compact = useCompactLayout();
const manualCollapse = ref(false);
const collapsed = computed(() => compact.value || manualCollapse.value);
const instances = computed(() => store.state.instances.map((value) => ({ label: value, value })));
const menu: MenuOption[] = [
  {
    key: 'conversation',
    label: () => h(RouterLink, { to: '/conversation', 'data-testid': 'nav-conversation' }, () => '交流'),
    icon: () => h(FontAwesomeIcon, { icon: faComments }),
  },
  {
    key: 'state',
    label: () => h(RouterLink, { to: '/state', 'data-testid': 'nav-state' }, () => '状态'),
    icon: () => h(FontAwesomeIcon, { icon: faDatabase }),
  },
];
</script>

<template>
  <NLayout has-sider class="workbench-layout">
    <NLayoutSider
      bordered
      collapse-mode="width"
      :width="220"
      :collapsed-width="64"
      :collapsed="collapsed"
      :native-scrollbar="false"
      show-trigger="bar"
      @collapse="manualCollapse = true"
      @expand="manualCollapse = false"
    >
      <RouterLink class="brand" to="/conversation" aria-label="Aurora 工作台">{{
        collapsed ? 'A' : 'Aurora'
      }}</RouterLink>
      <nav aria-label="主导航">
        <NMenu
          :value="String(route.name)"
          :collapsed="collapsed"
          :collapsed-width="64"
          :options="menu"
          @update:value="router.push({ name: $event })"
        />
      </nav>
    </NLayoutSider>
    <NLayout class="main-layout">
      <NLayoutHeader bordered class="workspace-header">
        <span class="breadcrumb">工作台 / {{ route.meta.title }}</span>
        <NSpace align="center" :size="12">
          <NTag
            class="connection-line"
            :type="store.state.ready ? 'success' : 'default'"
            :bordered="false"
            size="small"
          >
            {{ store.state.ready ? '实时同步' : statusNames[store.state.connection] }}
          </NTag>
          <NTooltip>
            <template #trigger>
              <NButton
                quaternary
                circle
                aria-label="核对后端状态"
                :disabled="store.state.connection !== 'connected'"
                @click="store.refresh()"
              >
                <template #icon><FontAwesomeIcon :icon="faRotate" /></template>
              </NButton>
            </template>
            <template #default>核对后端状态</template>
          </NTooltip>
          <NButton secondary aria-label="连接设置" @click="store.connectionVisible = true">
            <template #icon><FontAwesomeIcon :icon="faLink" /></template>连接
          </NButton>
        </NSpace>
      </NLayoutHeader>
      <NLayoutContent class="workspace-content" :native-scrollbar="false">
        <div class="workspace-toolbar">
          <div class="instance-picker">
            <label for="instance">当前 Bot</label
            ><NSelect
              :input-props="{ id: 'instance', 'aria-label': '当前 Bot' }"
              :value="store.state.instance || null"
              :options="instances"
              :disabled="!store.state.ready"
              placeholder="等待连接"
              @update:value="store.select"
            />
          </div>
          <span class="endpoint" :title="store.state.url">{{ store.state.url || '连接后即可开始交流' }}</span>
        </div>
        <NAlert
          v-if="store.state.notice"
          class="workspace-notice"
          :type="store.state.ready ? 'info' : 'warning'"
          role="status"
        >
          {{ store.state.notice }}
        </NAlert>
        <NAlert v-if="!store.state.ready && store.state.url" class="workspace-notice" type="warning">
          连接尚未就绪，以下为最后观察到的内容。<NButton text type="primary" @click="store.connectionVisible = true">
            检查连接
          </NButton>
        </NAlert>
        <RouterView v-slot="{ Component }">
          <KeepAlive :max="2"><component :is="Component" /></KeepAlive>
        </RouterView>
      </NLayoutContent>
    </NLayout>
  </NLayout>
  <ConnectionPanel />
</template>

<style scoped>
.workbench-layout {
  height: 100dvh;
}

.main-layout {
  min-width: 0;
}

.brand {
  display: block;
  height: 76px;
  padding: 20px 22px;
  font-size: 27px;
  font-weight: 700;
  color: #326656;
  text-decoration: none;
}

.workspace-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 76px;
  padding: 16px 28px;
}

.breadcrumb {
  color: #667085;
}

.workspace-content {
  height: calc(100dvh - 76px);
  padding: 24px 28px;
  background: #f6f8fa;
}

.workspace-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.instance-picker {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 260px;
  max-width: 100%;
}

.instance-picker label {
  flex-shrink: 0;
  color: #667085;
}

.endpoint {
  overflow: hidden;
  text-overflow: ellipsis;
  color: #667085;
  white-space: nowrap;
}

.workspace-notice {
  margin-bottom: 16px;
}

@media (width <= 600px) {
  .workspace-header {
    padding: 12px 16px;
  }

  .breadcrumb {
    display: none;
  }

  .workspace-content {
    padding: 20px 16px;
  }

  .endpoint {
    display: none;
  }
}
</style>
