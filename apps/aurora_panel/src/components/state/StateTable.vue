<script setup lang="ts">
import type { StateRecord } from '@aurorabot/client';
import type { DataTableColumns } from 'naive-ui';

import { h } from 'vue';

import { NButton, NDataTable } from 'naive-ui';

import { address } from '../../utils/state';

defineProps<{ records: StateRecord[] }>();
const emit = defineEmits<{ select: [record: StateRecord] }>();
const columns: DataTableColumns<StateRecord> = [
  {
    title: '状态 ID',
    key: 'id',
    minWidth: 240,
    render: (record) =>
      h(
        NButton,
        {
          text: true,
          type: 'primary',
          style: { maxWidth: '100%', whiteSpace: 'normal', textAlign: 'left', overflowWrap: 'anywhere' },
          onClick: () => emit('select', record),
        },
        () => record.id,
      ),
  },
  { title: '位置', key: 'location', minWidth: 160, render: (record) => JSON.stringify(record.location) },
];
</script>

<template>
  <NDataTable
    :columns="columns"
    :data="records"
    :row-key="address"
    :pagination="{ pageSize: 10 }"
    :scroll-x="440"
    size="small"
  />
</template>
