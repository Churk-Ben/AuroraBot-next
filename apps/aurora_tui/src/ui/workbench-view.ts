import type { CliRenderer, KeyEvent, PasteEvent } from '@opentui/core';

import { BoxRenderable, TextareaRenderable, TextRenderable } from '@opentui/core';

import { Workbench } from '../state/workbench.ts';
import { colors } from '../theme/colors.ts';
import { ShortcutHelp } from './components/shortcut-help.ts';
import { ConversationPage } from './pages/conversation.ts';
import { StatusPage } from './pages/status.ts';
import { text, visibleText } from './text.ts';

const connections = {
  closed: '已关闭',
  connected: '已连接',
  connecting: '连接中',
  failed: '连接失败',
  reconnecting: '重连中',
  refreshing: '刷新中',
};

export class WorkbenchView {
  readonly conversation: ConversationPage;
  readonly input: TextareaRenderable;
  page: 'chat' | 'state' = 'chat';
  readonly statusPage: StatusPage;
  private readonly composer: BoxRenderable;
  private disposed = false;
  private readonly footer: TextRenderable;
  private readonly help: ShortcutHelp;
  private readonly identity: TextRenderable;
  private readonly model: Workbench;
  private readonly notice: BoxRenderable;
  private readonly quit: () => void;
  private readonly renderer: CliRenderer;
  private readonly root: BoxRenderable;
  private readonly stateTab: TextRenderable;
  private readonly status: TextRenderable;
  private readonly tabs: TextRenderable;
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
    header.add(text(renderer, 'AURORA'));
    this.tabs = text(renderer, ' 交流 ', { onMouseDown: () => this.switchPage('chat') });
    this.stateTab = text(renderer, ' 状态 ', { onMouseDown: () => this.switchPage('state') });
    header.add(this.tabs);
    header.add(this.stateTab);
    this.identity = text(renderer, '', { fg: colors.muted, flexGrow: 1, textAlign: 'right', truncate: true });
    header.add(this.identity);
    this.conversation = new ConversationPage(renderer, model, () => this.hints());
    this.statusPage = new StatusPage(renderer, model);
    this.help = new ShortcutHelp(renderer);
    this.root.add(this.conversation.root);
    this.root.add(this.statusPage.root);
    this.root.add(this.help.root);

    this.notice = new BoxRenderable(renderer, { paddingX: 3, flexShrink: 0, visible: false });
    this.status = text(renderer, '', { fg: colors.muted });
    this.notice.add(this.status);
    this.root.add(this.notice);
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
        if (!this.help.root.visible && model.submit(this.input.plainText)) this.input.clear();
      },
    });
    this.composer.add(this.input);
    this.root.add(this.composer);
    const footer = new BoxRenderable(renderer, { height: 3, paddingX: 3, paddingY: 1, flexShrink: 0 });
    this.footer = text(renderer, '', {
      height: 1,
      fg: colors.muted,
      truncate: true,
      onMouseDown: () => this.toggleHelp(),
    });
    footer.add(this.footer);
    this.root.add(footer);
    this.unsubscribe = model.listen(() => this.render());
    renderer.keyInput.on('keypress', this.key);
    renderer.keyInput.on('paste', this.paste);
    renderer.on('resize', this.resize);
    this.render();
    this.input.focus();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.unsubscribe();
    this.renderer.keyInput.off('keypress', this.key);
    this.renderer.keyInput.off('paste', this.paste);
    this.renderer.off('resize', this.resize);
    this.root.destroyRecursively();
  }

  switchPage(page: 'chat' | 'state'): void {
    if (this.help.root.visible) return;
    this.page = page;
    this.conversation.root.visible = page === 'chat';
    this.composer.visible = page === 'chat';
    this.statusPage.root.visible = page === 'state';
    this.editor().focus();
    this.render();
  }

  private editor(): TextareaRenderable {
    return this.page === 'chat' ? this.input : this.statusPage.filter;
  }

  private hints(): void {
    if (this.disposed) return;
    this.footer.content = this.help.root.visible
      ? '? / Esc 关闭'
      : `${this.conversation.unread ? '↓ 新内容 · F3  ' : ''}? 帮助`;
  }

  private readonly key = (key: KeyEvent): void => {
    const question =
      !key.ctrl && !key.meta && (key.sequence === '?' || key.name === '?' || (key.name === '/' && key.shift));
    if (key.ctrl && key.name === 'c') this.quit();
    else if (this.help.root.visible) {
      if (key.name === 'escape' || question || key.name === 'f12') this.toggleHelp();
      else if (key.name === 'pageup' || key.name === 'pagedown')
        this.help.scroll.scrollBy(key.name === 'pageup' ? -1 : 1, 'viewport');
      else if (key.name === 'up' || key.name === 'down') this.help.scroll.scrollBy(key.name === 'up' ? -1 : 1);
    } else if (key.name === 'f12' || (question && this.editor().plainText.length === 0)) this.toggleHelp();
    else if (key.name === 'tab') this.switchPage(this.page === 'chat' ? 'state' : 'chat');
    else if (key.name === 'f1') this.switchPage('chat');
    else if (key.name === 'f2') this.switchPage('state');
    else if (key.name === 'f3') this.conversation.bottom();
    else if (key.name === 'f4') this.model.retry();
    else if (key.name === 'f5') void this.model.refresh();
    else if (key.ctrl && key.name === 't') this.conversation.toggleTools();
    else if (key.ctrl && key.name === 'x') {
      const group = this.model.current();
      if (group) void this.model.cancel(group);
    } else if (key.name === 'pageup' || key.name === 'pagedown') {
      (this.page === 'chat' ? this.conversation.scroll : this.statusPage.scroll).scrollBy(
        key.name === 'pageup' ? -1 : 1,
        'viewport',
      );
    } else return;
    key.preventDefault();
    key.stopPropagation();
  };

  private readonly paste = (event: PasteEvent): void => {
    if (this.help.root.visible) {
      event.preventDefault();
      event.stopPropagation();
    }
  };

  private render(): void {
    if (this.disposed) return;
    const compact = this.help.root.visible && this.renderer.height < 24;
    this.composer.height = compact ? 3 : 5;
    this.input.height = compact ? 1 : 3;
    const { model } = this;
    this.tabs.fg = this.page === 'chat' ? colors.text : colors.muted;
    this.stateTab.fg = this.page === 'state' ? colors.text : colors.muted;
    this.identity.content = visibleText(
      `${model.instance || '未选择 bot'}${model.connection === 'connected' ? '' : ` · ${connections[model.connection]}`}`,
    );
    this.conversation.render();
    this.statusPage.render();
    this.status.content = visibleText(model.notice);
    this.notice.visible = Boolean(model.notice);
    let placeholder = '等待连接…';
    if (model.ready) placeholder = `${model.current() ? '追加引导' : '输入消息'}…`;
    this.input.placeholder = placeholder;
    this.hints();
  }

  private readonly resize = (): void => {
    this.help.resize();
    this.render();
  };

  private toggleHelp(): void {
    const open = !this.help.root.visible;
    this.editor().blur();
    this.help.root.visible = open;
    this.conversation.root.visible = !open && this.page === 'chat';
    this.statusPage.root.visible = !open && this.page === 'state';
    if (open) this.help.root.focus();
    else this.editor().focus();
    this.render();
  }
}
