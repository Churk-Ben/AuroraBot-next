/** 工作区检查入口：先 uv sync --all-packages 与 pnpm install，再 pnpm check。 */
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));

// 使用 pnpm 的实际入口，兼容 JS 启动器与原生可执行文件。
const pnpm = process.env.npm_execpath;
if (!pnpm) {
  throw new Error('请使用 pnpm check 运行工作区检查');
}

function run(command: string, args: string[], cwd = root): void {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (result.error) {
    console.error(result.error.message);
  }
  if (result.error || result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

for (const task of ['format:check', 'lint', 'typecheck', 'test']) {
  if (/\.[cm]?js$/u.test(pnpm)) {
    run(process.execPath, [pnpm, 'run', task]);
  } else {
    run(pnpm, ['run', task]);
  }
}

for (const args of [['ruff', 'check', '.'], ['ruff', 'format', '--check', '.'], ['pytest']]) {
  run('uv', ['run', '--locked', ...args]);
}

// 在真实消费方验证 pnpm 工作区链接及共享 client 入口。
for (const app of ['aurora_tui', 'aurora_panel']) {
  run(
    process.execPath,
    ['--experimental-strip-types', '--input-type=module', '-e', 'await import("@aurorabot/client");'],
    fileURLToPath(new URL(`../apps/${app}/`, import.meta.url)),
  );
}
