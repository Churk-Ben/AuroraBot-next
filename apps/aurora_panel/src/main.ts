import { createApp } from 'vue';

import { config } from '@fortawesome/fontawesome-svg-core';
import { createPinia } from 'pinia';

import App from './App.vue';
import { createPanelRouter } from './router/index.ts';

import '@fortawesome/fontawesome-svg-core/styles.css';
import './styles/base.css';

config.autoAddCss = false;
createApp(App).use(createPinia()).use(createPanelRouter()).mount('#app');
