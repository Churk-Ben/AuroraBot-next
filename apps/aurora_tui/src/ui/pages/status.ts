import type { CliRenderer } from '@opentui/core';

import { BoxRenderable, InputRenderable, ScrollBoxRenderable, TextRenderable } from '@opentui/core';

import { Workbench } from '../../state/workbench.ts';
import { colors } from '../../theme/colors.ts';
import { text, visibleText } from '../text.ts';

export class StatusPage {
  readonly filter: InputRenderable;
  readonly root: BoxRenderable;
  readonly scroll: ScrollBoxRenderable;
  private readonly content: TextRenderable;
  private readonly model: Workbench;
  constructor(renderer: CliRenderer, model: Workbench) {
    this.model = model;
    this.root = new BoxRenderable(renderer, {
      flexDirection: 'column',
      flexGrow: 1,
      minHeight: 0,
      visible: false,
      paddingX: 2,
    });
    this.root.add(text(renderer, '只读浏览', { fg: colors.muted, marginY: 1 }));
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
    this.filter.on('input', () => this.render());
    this.root.add(this.filter);
    this.scroll = new ScrollBoxRenderable(renderer, {
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
    this.content = text(renderer, '');
    this.scroll.add(this.content);
    this.root.add(this.scroll);
  }
  render(): void {
    const filter = this.filter.value.toLocaleLowerCase();
    const records = [...this.model.records.values()].filter(
      (record) =>
        (!record.location.instance_id || record.location.instance_id === this.model.instance) &&
        `${record.id} ${JSON.stringify(record.location)}`.toLocaleLowerCase().includes(filter),
    );
    this.content.content = visibleText(
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
}
