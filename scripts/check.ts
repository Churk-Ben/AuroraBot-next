/** 工作区检查入口：先 uv sync --all-packages 与 pnpm install，再 pnpm check。 */
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

import { planChecks } from './check-plan.ts';

const root = fileURLToPath(new URL('../', import.meta.url));

// 使用 pnpm 的实际入口，兼容 JS 启动器与原生可执行文件。
const pnpm = process.env.npm_execpath;
if (!pnpm) {
  throw new Error('请使用 pnpm check 运行工作区检查');
}

function run(command: string, args: string[], cwd = root): boolean {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (result.error) {
    console.error(result.error.message);
  }
  if (result.error || result.status !== 0) {
    return false;
  }
  return true;
}

try {
  const { values } = parseArgs({
    options: {
      lint: { type: 'boolean' },
      test: { type: 'boolean' },
      coverage: { type: 'boolean' },
      fix: { type: 'boolean' },
      'unsafe-fixes': { type: 'boolean' },
      check: { type: 'boolean' },
    },
  });
  const tasks = planChecks(values);
  let failures = 0;
  for (const task of tasks) {
    let command: string = task.tool;
    let args = task.args;
    if (task.tool === 'pnpm') {
      command = /\.[cm]?js$/u.test(pnpm) ? process.execPath : pnpm;
      args = command === process.execPath ? [pnpm, ...args] : args;
    } else if (task.tool === 'node') {
      command = process.execPath;
    }
    if (!run(command, args, task.cwd ? resolve(root, task.cwd) : root)) {
      failures++;
    }
  }
  console.log(failures ? `${failures} 项检查失败。` : '全部检查通过。');
  process.exitCode = failures ? 1 : 0;
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 2;
}
