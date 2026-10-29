import stylelint from 'stylelint';
import { describe, expect, it } from 'vitest';

describe('样式检查入口', () => {
  it.each([
    ['fixture.css', '.example { color: red; }', '.example { unknown-property: red; }'],
    ['fixture.scss', '$color: red;\n\n.example { color: $color; }', '.example { unknown-property: red; }'],
    ['fixture.vue', '<style>.example { color: red; }</style>', '<style>.example { unknown-property: red; }</style>'],
  ])('识别 %s 中的有效样式与未知属性', async (filename, valid, invalid) => {
    const options = { codeFilename: `apps/aurora_panel/src/${filename}`, configFile: 'stylelint.config.ts' };
    const validResult = await stylelint.lint({ ...options, code: valid });
    expect(validResult.results.flatMap((result) => result.warnings)).toEqual([]);
    const result = await stylelint.lint({ ...options, code: invalid });
    expect(result.errored).toBe(true);
    expect(result.results[0]?.warnings.some((warning) => warning.rule === 'property-no-unknown')).toBe(true);
  });
});
