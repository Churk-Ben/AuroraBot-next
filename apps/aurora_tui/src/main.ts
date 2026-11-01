import process from 'node:process';
import { parseArgs } from 'node:util';

import { CtxClient } from '@aurorabot/client';
import { createCliRenderer } from '@opentui/core';

import { Workbench } from './state/workbench.ts';
import { colors } from './theme/colors.ts';
import { shortcutHelp } from './ui/shortcuts.ts';
import { WorkbenchView } from './ui/workbench-view.ts';

async function main(): Promise<void> {
  const { values } = parseArgs({
    options: {
      connect: { type: 'string', default: 'http://127.0.0.1:10270' },
      instance: { type: 'string' },
      help: { type: 'boolean', short: 'h' },
    },
  });
  if (values.help) {
    process.stdout.write(
      `Aurora 终端工作台\n\npnpm --filter @aurorabot/tui start [--connect URL] [--instance ID]\n\n${shortcutHelp}\n`,
    );
    return;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY)
    throw new Error('TUI 需要交互终端，请在 PowerShell 或其他终端中启动。');
  const client = new CtxClient(values.connect);
  const model = new Workbench(client, values.instance);
  const renderer = await createCliRenderer({
    exitOnCtrlC: false,
    exitSignals: [],
    useMouse: true,
    screenMode: 'alternate-screen',
    backgroundColor: colors.background,
    openConsoleOnError: false,
  });
  let view: undefined | WorkbenchView;
  let closing: Promise<void> | undefined;
  const close = (): Promise<void> => {
    closing ??= (async () => {
      view?.dispose();
      try {
        await model.close();
      } finally {
        renderer.destroy();
        await renderer.closed;
      }
    })();
    return closing;
  };
  const quit = (): void => {
    void close().catch((error: unknown) => {
      process.exitCode = 1;
      console.error(error);
    });
  };
  process.on('SIGINT', quit);
  process.on('SIGTERM', quit);
  try {
    view = new WorkbenchView(renderer, model, quit);
    void model.start();
    await renderer.closed;
  } finally {
    await close();
    process.off('SIGINT', quit);
    process.off('SIGTERM', quit);
  }
}

try {
  await main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
