import type { GlobalThemeOverrides } from 'naive-ui';

/** 品牌色与 TUI assets/palette.svg 保持一致；各界面独立选择中性背景。 */
export const brandColors = {
  accent: '#4B79EC',
  complement: '#ECBE4B',
  accentLight: '#81A1F2',
  accentDeep: '#3555A5',
};

export const themeVariables = {
  '--aurora-accent': brandColors.accent,
  '--aurora-complement': brandColors.complement,
};

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: brandColors.accent,
    primaryColorHover: brandColors.accentLight,
    primaryColorPressed: brandColors.accentDeep,
    primaryColorSuppl: brandColors.accentLight,
    borderRadius: '8px',
    fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif',
  },
};
