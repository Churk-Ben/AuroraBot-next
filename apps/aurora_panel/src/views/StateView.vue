<script setup lang="ts">
import { computed, ref } from 'vue';

import { faMagnifyingGlass } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { NCard, NEmpty, NInput, NTag } from 'naive-ui';

import JsonViewer from '../components/common/JsonViewer.vue';
import StateTable from '../components/state/StateTable.vue';
import { useWorkbenchStore } from '../stores/workbench';
import { address } from '../utils/state';

const store = useWorkbenchStore();
const filter = ref('');
const selectedAddress = ref('');
const records = computed(() =>
  store.state.records
    .filter((item) => `${item.id} ${JSON.stringify(item.location)}`.toLowerCase().includes(filter.value.toLowerCase()))
    .toSorted((a, b) => address(a).localeCompare(address(b))),
);
const selected = computed(
  () => records.value.find((item) => address(item) === selectedAddress.value) ?? records.value[0],
);
</script>

<template>
  <section class="page-stack" aria-label="状态工作区">
    <header class="page-heading">
      <div>
        <h1>公开状态</h1>
        <p>读取和订阅后端已开放的数据。</p>
      </div>
      <NTag :bordered="false">只读 · {{ store.state.records.length }} 项</NTag>
    </header>
    <NInput
      v-model:value="filter"
      :input-props="{ id: 'state-filter', 'aria-label': '筛选状态' }"
      placeholder="按状态 ID 或位置筛选…"
      clearable
    >
      <template #prefix><FontAwesomeIcon :icon="faMagnifyingGlass" /></template>
    </NInput>
    <div class="state-browser">
      <StateTable :records="records" @select="selectedAddress = address($event)" />
      <NCard class="state-detail" title="当前值" size="small">
        <template v-if="selected">
          <div class="state-address">
            <strong class="text-content">{{ selected.id }}</strong>
            <div class="text-content muted">{{ JSON.stringify(selected.location) }}</div>
          </div>
          <JsonViewer :value="selected.value" />
        </template>
        <NEmpty v-else :description="filter ? '没有匹配的状态' : '后端尚未开放或写入状态'" />
      </NCard>
    </div>
  </section>
</template>

<style scoped>
.state-browser {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.state-detail {
  min-width: 0;
}

.state-address {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

@media (width <= 1100px) {
  .state-browser {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
