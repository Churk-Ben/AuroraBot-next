import { describe, expect, it } from 'vitest';

import { planChecks } from '../check-plan.ts';

describe('工作区检查选项', () => {
  it('默认检查不包含写入型参数，并包含前后端测试', () => {
    const tasks = planChecks({});
    expect(tasks.some(({ args }) => args.includes('--fix'))).toBe(false);
    expect(tasks.some(({ args }) => args.includes('format'))).toBe(true);
    expect(tasks.find(({ args }) => args.includes('format'))?.args).toContain('--check');
    expect(tasks.some(({ args }) => args.includes('pytest'))).toBe(true);
    expect(tasks.some(({ tool, args }) => tool === 'pnpm' && args.includes('test'))).toBe(true);
  });

  it('测试及覆盖率选择不启动 lint', () => {
    const tasks = planChecks({ coverage: true });
    expect(tasks).toHaveLength(2);
    expect(tasks.find(({ tool }) => tool === 'uv')?.args).toContain('--cov');
    expect(planChecks({ lint: true }).some(({ args }) => args.includes('pytest'))).toBe(false);
  });

  it('格式预览不会因修复选项而变为写入', () => {
    const tasks = planChecks({ fix: true, check: true });
    expect(tasks.some(({ args }) => args.includes('--fix'))).toBe(true);
    expect(tasks.find(({ args }) => args.includes('format'))?.args).toContain('--check');
    expect(tasks.find(({ tool }) => tool === 'pnpm')?.args).toContain('format:check');
  });

  it('拒绝不完整或无效的修复组合', () => {
    expect(() => planChecks({ 'unsafe-fixes': true })).toThrow('需要同时指定 --fix');
    expect(() => planChecks({ test: true, fix: true })).toThrow('需要启用 lint');
  });
});
