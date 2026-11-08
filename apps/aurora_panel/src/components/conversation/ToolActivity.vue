<script setup lang="ts">
import type { JsonValue } from '@aurorabot/client';

import { NCollapse, NCollapseItem } from 'naive-ui';

import JsonViewer from '../common/JsonViewer.vue';

defineProps<{ results: JsonValue[]; tools: JsonValue[] }>();
</script>

<template>
  <NCollapse class="tool-activity">
    <NCollapseItem :title="`工具活动 · ${tools.length} 项${results.length ? ' · 已返回结果' : ''}`" name="tools">
      <JsonViewer :value="tools" /><template v-if="results.length">
        <h4>执行结果</h4>
        <JsonViewer :value="results" />
      </template>
    </NCollapseItem>
  </NCollapse>
</template>

<style scoped>
.tool-activity {
  margin-top: 12px;
}
</style>
