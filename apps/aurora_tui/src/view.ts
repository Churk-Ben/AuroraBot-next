import type { CliRenderer, KeyEvent } from '@opentui/core';

import type { RunGroup } from './workbench.ts';

import { BoxRenderable, InputRenderable, ScrollBoxRenderable, TextareaRenderable, TextRenderable } from '@opentui/core';

import { colors } from './theme.ts';
import { Workbench } from './workbench.ts';

const connections = {
  closed: '已关闭',
  connected: '已连接',
  connecting: '连接中',
  failed: '连接失败',
  reconnecting: '重连中',
  refreshing: '刷新中',
};
const messages = {
  accepted: '已接纳',
  expired: '旧会话 · 请核对',
  missing: '未查到回执 · F4 重试',
  rejected: '未接纳',
  sending: '提交中',
  uncertain: '结果未确认 · F5 核对',
};
const statuses = {
  cancelled: '已取消',
  completed: '运行结束',
  expired: '旧会话 · 不再跟踪',
  failed: '运行失败',
  pending: '进行中',
};

/** 过滤终端控制字符；后端文本只作为可见内容呈现。 */
export function visibleText(value: string): string {
  // oxlint-disable-next-line no-control-regex -- 显式移除不应进入终端的控制字符。
  return value.replaceAll(/[\u0000-\u0008\u000B-\u001F\u007F-\u009F]/gu, '');
}

interface Card {
  box: BoxRenderable;
  body: TextRenderable;
  bodyText: string;
  stop: TextRenderable;
  title: TextRenderable;
  tools: TextRenderable;
}

export class WorkbenchView {
  readonly chat: ScrollBoxRenderable;
  readonly input: TextareaRenderable;
  page: 'chat' | 'state' = 'chat';
  readonly state: ScrollBoxRenderable;
  private readonly cards = new Map<RunGroup, Card>();
  private readonly chatPage: BoxRenderable;
  private readonly composer: BoxRenderable;
  private details = false;
  private disposed = false;
  private readonly expanded = new Set<RunGroup>();
  private readonly filter: InputRenderable;
  private readonly footer: TextRenderable;
  private readonly history: TextRenderable;
  private readonly identity: TextRenderable;
  private readonly model: Workbench;
  private readonly pending: TextRenderable;
  private readonly quit: () => void;
  private readonly renderer: CliRenderer;
  private readonly root: BoxRenderable;
  private readonly statePage: BoxRenderable;
  private readonly stateTab: TextRenderable;
  private readonly stateText: TextRenderable;
  private readonly status: TextRenderable;
  private readonly tabs: TextRenderable;
  private unread = false;
  private readonly unsubscribe: () => void;

  constructor(renderer: CliRenderer, model: Workbench, quit: () => void) {
    this.renderer = renderer;
    this.model = model;
    this.quit = quit;
    this.root = new BoxRenderable(renderer, {
      id: 'workbench',
      width: '100%',
      height: '100%',
      flexDirection: 'column',
      backgroundColor: colors.background,
    });
    renderer.root.add(this.root);
    const header = new BoxRenderable(renderer, {
      height: 3,
      flexShrink: 0,
      paddingX: 2,
      alignItems: 'center',
      flexDirection: 'row',
      gap: 2,
      border: ['bottom'],
      borderColor: colors.border,
    });
    this.root.add(header);
    header.add(this.text('AURORA'));
    this.tabs = this.text(' 交流 ', { onMouseDown: () => this.switchPage('chat') });
    this.stateTab = this.text(' 状态 ', { onMouseDown: () => this.switchPage('state') });
    header.add(this.tabs);
    header.add(this.stateTab);
    this.identity = this.text('', { fg: colors.muted, flexGrow: 1, textAlign: 'right', truncate: true });
    header.add(this.identity);

    this.chatPage = new BoxRenderable(renderer, { flexDirection: 'column', flexGrow: 1, minHeight: 0 });
    this.statePage = new BoxRenderable(renderer, {
      flexDirection: 'column',
      flexGrow: 1,
      minHeight: 0,
      visible: false,
      paddingX: 2,
    });
    this.root.add(this.chatPage);
    this.root.add(this.statePage);
    this.chat = new ScrollBoxRenderable(renderer, {
      id: 'chat-scroll',
      flexGrow: 1,
      minHeight: 0,
      scrollX: false,
      stickyScroll: true,
      stickyStart: 'bottom',
      scrollbarOptions: {
        showArrows: false,
        trackOptions: { backgroundColor: colors.background, foregroundColor: colors.border },
      },
      contentOptions: { paddingX: 2, paddingY: 1, gap: 1 },
    });
    this.chatPage.add(this.chat);
    this.history = this.text('', { fg: colors.muted });
    this.pending = this.text('', { fg: colors.muted });
    this.chat.add(this.history);
    this.chat.add(this.pending);
    this.chat.verticalScrollBar.on('change', () => {
      if (this.atBottom()) this.unread = false;
      this.hints();
    });

    this.statePage.add(this.text('只读浏览', { fg: colors.muted, marginY: 1 }));
    this.filter = new InputRenderable(renderer, {
      id: 'state-filter',
      placeholder: '筛选状态 ID 或 location…',
      placeholderColor: colors.muted,
      cursorColor: colors.accent,
      selectionBg: colors.border,
      selectionFg: colors.text,
      backgroundColor: colors.surface,
      textColor: colors.text,
      focusedBackgroundColor: colors.surface,
      focusedTextColor: colors.text,
    });
    this.filter.on('input', () => this.renderState());
    this.statePage.add(this.filter);
    this.state = new ScrollBoxRenderable(renderer, {
      id: 'state-scroll',
      flexGrow: 1,
      minHeight: 0,
      scrollX: false,
      scrollbarOptions: {
        showArrows: false,
        trackOptions: { backgroundColor: colors.background, foregroundColor: colors.border },
      },
      contentOptions: { paddingY: 1 },
    });
    this.stateText = this.text('');
    this.state.add(this.stateText);
    this.statePage.add(this.state);

    this.status = this.text('', { paddingX: 2, fg: colors.muted, flexShrink: 0 });
    this.root.add(this.status);
    this.composer = new BoxRenderable(renderer, {
      height: 5,
      flexShrink: 0,
      marginX: 1,
      paddingX: 1,
      paddingY: 1,
      backgroundColor: colors.surface,
      border: ['left'],
      borderColor: colors.accent,
    });
    this.input = new TextareaRenderable(renderer, {
      id: 'message-input',
      width: '100%',
      height: 3,
      placeholder: '输入消息…',
      placeholderColor: colors.muted,
      cursorColor: colors.accent,
      selectionBg: colors.border,
      selectionFg: colors.text,
      textColor: colors.text,
      focusedTextColor: colors.text,
      backgroundColor: colors.surface,
      focusedBackgroundColor: colors.surface,
      wrapMode: 'word',
      keyBindings: [
        { name: 'return', action: 'submit' },
        { name: 'return', shift: true, action: 'newline' },
        { name: 'return', meta: true, action: 'newline' },
      ],
      onSubmit: () => {
        if (model.submit(this.input.plainText)) this.input.clear();
      },
    });
    this.composer.add(this.input);
    this.root.add(this.composer);
    this.footer = this.text('', { height: 1, paddingX: 2, fg: colors.muted, truncate: true, flexShrink: 0 });
    this.root.add(this.footer);
    this.unsubscribe = model.listen(() => this.render());
    renderer.keyInput.on('keypress', this.key);
    renderer.on('resize', this.resize);
    this.render();
    this.input.focus();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.unsubscribe();
    this.renderer.keyInput.off('keypress', this.key);
    this.renderer.off('resize', this.resize);
    this.root.destroyRecursively();
  }

  switchPage(page: 'chat' | 'state'): void {
    this.page = page;
    this.chatPage.visible = page === 'chat';
    this.composer.visible = page === 'chat';
    this.statePage.visible = page === 'state';
    (page === 'chat' ? this.input : this.filter).focus();
    this.render();
  }

  private atBottom(): boolean {
    return this.chat.scrollTop + this.chat.viewport.height >= this.chat.scrollHeight - 1;
  }

  private hints(): void {
    if (this.disposed) return;
    this.footer.content = `${this.unread ? '↓ 新内容 · F3  ' : ''}Tab 切页 · Ctrl+C 退出`;
  }

  private readonly key = (key: KeyEvent): void => {
    if (key.ctrl && key.name === 'c') this.quit();
    else if (key.name === 'tab') this.switchPage(this.page === 'chat' ? 'state' : 'chat');
    else if (key.name === 'f1') this.switchPage('chat');
    else if (key.name === 'f2') this.switchPage('state');
    else if (key.name === 'f3') {
      this.chat.scrollTo(Infinity);
      this.unread = false;
      this.hints();
    } else if (key.name === 'f4') this.model.retry();
    else if (key.name === 'f5') void this.model.refresh();
    else if (key.ctrl && key.name === 't') {
      this.details = !this.details;
      this.render();
    } else if (key.ctrl && key.name === 'x') {
      const group = this.model.current();
      if (group) void this.model.cancel(group);
    } else if (key.name === 'pageup' || key.name === 'pagedown') {
      (this.page === 'chat' ? this.chat : this.state).scrollBy(key.name === 'pageup' ? -1 : 1, 'viewport');
    } else return;
    key.preventDefault();
    key.stopPropagation();
  };

  private render(): void {
    if (this.disposed) return;
    const atBottom = this.atBottom();
    const { model } = this;
    this.tabs.fg = this.page === 'chat' ? colors.text : colors.muted;
    this.stateTab.fg = this.page === 'state' ? colors.text : colors.muted;
    this.identity.content = visibleText(
      `${model.instance || '未选择 bot'}${model.connection === 'connected' ? '' : ` · ${connections[model.connection]}`}`,
    );
    this.history.visible = Boolean(model.history);
    this.history.content = visibleText(`历史上下文\n\n${model.history}`);
    const pending = model.messages.filter((message) => !message.receipt);
    this.pending.visible = pending.length > 0;
    this.pending.content =
      pending.length > 0
        ? visibleText(
            pending
              .slice(-20)
              .map((message) => `你 · ${messages[message.status]}\n${message.request.text}\n${message.error ?? ''}`)
              .join('\n\n'),
          )
        : '';
    let contentChanged = false;
    for (const group of model.groups) {
      let card = this.cards.get(group);
      if (!card) {
        const box = new BoxRenderable(this.renderer, {
          flexDirection: 'column',
          gap: 1,
          flexShrink: 0,
          paddingBottom: 1,
        });
        const title = this.text('', { fg: colors.muted });
        const body = this.text('');
        const tools = this.text('', {
          fg: colors.muted,
          onMouseDown: () => {
            if (this.expanded.has(group)) this.expanded.delete(group);
            else this.expanded.add(group);
            this.render();
          },
        });
        const stop = this.text('■ 停止', {
          fg: colors.muted,
          onMouseDown: () => {
            void model.cancel(group);
          },
        });
        for (const child of [title, body, tools, stop]) box.add(child);
        this.chat.add(box);
        card = { box, title, body, bodyText: '', tools, stop };
        this.cards.set(group, card);
        contentChanged = true;
      }
      let label = `进行中 · ${group.phase || '等待执行'}`;
      if (group.confirmed || group.status === 'expired') label = statuses[group.status];
      else if (group.observed && group.observed !== 'running')
        label = `后端报告 ${group.observed} · ${group.phase || '等待核对'}`;
      card.title.content = visibleText(`● 运行 ${group.id.slice(0, 8)}  ${label}`);
      const guides = model.messages
        .filter((message) => message.receipt?.run_id === group.id && message.request.session_id === group.session)
        .map(
          (message) =>
            `你${message.status === 'accepted' ? '' : ` · ${messages[message.status]}`}\n${message.request.text}`,
        );
      const outputs = [...group.outputs.values()].filter(Boolean).map((text) => `模型输出\n${text}`);
      const content = visibleText([...guides, ...outputs].join('\n\n') || '正在等待运行活动…');
      if (card.bodyText !== content) {
        card.body.content = content;
        card.bodyText = content;
        contentChanged = true;
      }
      const expanded = this.details || this.expanded.has(group);
      card.tools.visible = group.tools.size > 0;
      card.tools.content = visibleText(
        [...group.tools.values()]
          .map(
            (tool) =>
              `${expanded ? '▾' : '▸'} ${tool.name} · ${tool.status}${expanded ? `\n${JSON.stringify({ arguments: tool.arguments, result: tool.result }, null, 2)?.slice(0, 8000)}` : ''}`,
          )
          .join('\n'),
      );
      card.stop.visible =
        model.ready &&
        group.session === model.session &&
        group.status === 'pending' &&
        (group.observed === 'running' || !group.observed);
    }
    for (const [group, card] of this.cards) {
      if (!model.groups.includes(group)) {
        card.box.destroyRecursively();
        this.cards.delete(group);
        this.expanded.delete(group);
      }
    }
    if (contentChanged && !atBottom) this.unread = true;
    this.status.content = visibleText(model.notice);
    this.status.visible = Boolean(model.notice);
    let placeholder = '等待连接…';
    if (model.ready) placeholder = `${model.current() ? '追加引导' : '输入消息'}…`;
    this.input.placeholder = placeholder;
    this.renderState();
    this.hints();
  }

  private renderState(): void {
    const filter = this.filter.value.toLocaleLowerCase();
    const records = [...this.model.records.values()].filter(
      (record) =>
        (!record.location.instance_id || record.location.instance_id === this.model.instance) &&
        `${record.id} ${JSON.stringify(record.location)}`.toLocaleLowerCase().includes(filter),
    );
    this.stateText.content = visibleText(
      `${records.length} 个状态\n\n${
        records
          .slice(0, 100)
          .map(
            (record) =>
              `${record.id}\n${JSON.stringify(record.location)}\n${JSON.stringify(record.value, null, 2).slice(0, 8000)}`,
          )
          .join('\n\n') || '暂无匹配状态。'
      }`,
    );
  }

  private readonly resize = (): void => this.render();

  private text(
    content: string,
    options: Omit<ConstructorParameters<typeof TextRenderable>[1], 'content'> = {},
  ): TextRenderable {
    return new TextRenderable(this.renderer, {
      content: visibleText(content),
      fg: colors.text,
      wrapMode: 'word',
      flexShrink: 0,
      ...options,
    });
  }
}
