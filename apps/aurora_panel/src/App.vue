<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';

import { dateZhCN, NConfigProvider, NGlobalStyle, zhCN } from 'naive-ui';

import WorkbenchLayout from './layouts/WorkbenchLayout.vue';
import { useWorkbenchStore } from './stores/workbench';
import { themeOverrides } from './theme';

const store = useWorkbenchStore();
const leave = () => {
  void store.disconnect();
};
onMounted(() => window.addEventListener('pagehide', leave));
onBeforeUnmount(() => {
  window.removeEventListener('pagehide', leave);
  leave();
});
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <NGlobalStyle />
    <WorkbenchLayout />
  </NConfigProvider>
</template>
