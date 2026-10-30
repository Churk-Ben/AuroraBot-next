/** 根据显式选项选择检查，不在导入时运行外部进程。 */
export interface CheckOptions {
  check?: boolean;
  coverage?: boolean;
  fix?: boolean;
  lint?: boolean;
  test?: boolean;
  'unsafe-fixes'?: boolean;
}

export interface CheckTask {
  args: string[];
  cwd?: string;
  tool: 'node' | 'pnpm' | 'uv';
}

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
    pnpm('run', 'test');
    uv('pytest', ...(options.coverage ? ['--cov', '--cov-report=term-missing'] : []));
  }
  return tasks;
}
