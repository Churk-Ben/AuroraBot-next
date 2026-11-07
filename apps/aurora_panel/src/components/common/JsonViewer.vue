<script setup lang="ts">
import { computed } from 'vue';

import { NCode } from 'naive-ui';

const props = defineProps<{ value: unknown }>();
const code = computed(() => JSON.stringify(props.value, null, 2) ?? 'null');
</script>

<template>
  <div class="json-viewer"><NCode :code="code" word-wrap /></div>
</template>

<style scoped>
.json-viewer {
  max-height: 420px;
  padding: 12px;
  overflow: auto;
  overflow-wrap: anywhere;
  background: #f6f8fa;
  border-radius: 8px;
}
</style>
