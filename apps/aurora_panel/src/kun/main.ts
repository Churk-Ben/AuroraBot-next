import { createApp } from 'vue';

import { createPinia } from 'pinia';

import App from './App.vue';
import { createKunRouter } from './router';

import './styles.css';

createApp(App).use(createPinia()).use(createKunRouter()).mount('#app');
