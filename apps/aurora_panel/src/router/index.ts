import type { RouterHistory } from 'vue-router';

import { createRouter, createWebHashHistory } from 'vue-router';

/** Hash 路由支持静态产物直接部署，无需服务端回退规则。 */
export function createPanelRouter(history: RouterHistory = createWebHashHistory()) {
  return createRouter({
    history,
    routes: [
      { path: '/', redirect: '/conversation' },
      {
        path: '/conversation',
        name: 'conversation',
        component: () => import('../views/ConversationView.vue'),
        meta: { title: '交流' },
      },
      { path: '/state', name: 'state', component: () => import('../views/StateView.vue'), meta: { title: '状态' } },
      { path: '/:pathMatch(.*)*', redirect: '/conversation' },
    ],
  });
}
