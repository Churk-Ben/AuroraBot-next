/** 工作区检查入口：先 uv sync --all-packages 与 pnpm install，再 pnpm check。 */
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

export interface CheckOptions {
  check?: boolean;
  coverage?: boolean;
  fix?: boolean;
  full?: boolean;
  lint?: boolean;
  test?: boolean;
  'unsafe-fixes'?: boolean;
}

export interface CheckTask {
  args: string[];
  cwd?: string;
  tool: 'node' | 'pnpm' | 'uv';
}

/** 根据显式选项选择检查，不在导入时运行外部进程。 */
export function planChecks(options: CheckOptions): CheckTask[] {
  const lint = options.lint || !(options.test || options.coverage);
  const test = options.test || options.coverage || !options.lint;
  if ((options.fix || options.check || options['unsafe-fixes']) && !lint) {
    throw new Error('修复选项需要启用 lint 检查');
  }
  if ((options.check || options['unsafe-fixes']) && !options.fix) {
    throw new Error('--check 和 --unsafe-fixes 需要同时指定 --fix');
  }
  const tasks: CheckTask[] = [];
  const pnpm = (...args: string[]) => tasks.push({ tool: 'pnpm', args });
  const uv = (...args: string[]) => tasks.push({ tool: 'uv', args: ['run', '--locked', ...args] });
  if (lint) {
    pnpm('run', options.fix && !options.check ? 'format' : 'format:check');
    pnpm('run', 'lint');
    pnpm('run', 'typecheck');
    uv('ruff', 'check', ...(options.fix ? ['--fix'] : []), ...(options['unsafe-fixes'] ? ['--unsafe-fixes'] : []), '.');
    uv('ruff', 'format', ...(options.fix && !options.check ? [] : ['--check']), '.');
    for (const app of ['aurora_tui', 'aurora_panel']) {
      tasks.push({
        tool: 'node',
        args: ['--experimental-strip-types', '--input-type=module', '-e', 'await import("@aurorabot/client");'],
        cwd: `apps/${app}`,
      });
    }
  }
  if (test) {
    if (options.full || options.coverage) {
      pnpm('run', 'test');
      pnpm('--filter', '@aurorabot/tui', 'test:terminal');
      uv('pytest', ...(options.coverage ? ['--cov', '--cov-report=term-missing'] : []));
    } else {
      pnpm('exec', 'vitest', 'run', 'packages/aurora_client', 'scripts/__tests__/check-plan.test.ts');
      uv('pytest', 'tests/contract');
    }
  }
  return tasks;
}

const root = fileURLToPath(new URL('../', import.meta.url));

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

if (import.meta.main) {
  try {
    // 使用 pnpm 的实际入口，兼容 JS 启动器与原生可执行文件。
    const pnpm = process.env.npm_execpath;
    if (!pnpm) {
      throw new Error('请使用 pnpm check 运行工作区检查');
    }
    const { values } = parseArgs({
      options: {
        lint: { type: 'boolean' },
        test: { type: 'boolean' },
        coverage: { type: 'boolean' },
        full: { type: 'boolean' },
        fix: { type: 'boolean' },
        'unsafe-fixes': { type: 'boolean' },
        check: { type: 'boolean' },
      },
    });
    const tasks = planChecks(values);
    if (tasks.some(({ args }) => args.includes('pytest'))) {
      console.log(
        values.full || values.coverage ? '测试范围：完整测试。' : '测试范围：快速边界测试；完整测试使用 --full。',
      );
    }
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
}
