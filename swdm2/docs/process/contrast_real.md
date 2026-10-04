# WCAG 对比度实算表（t62 D5.19 · 用户指控"暗色黑灰看不见字")

> 方法：W3C 相对亮度（sRGB→线性→0.2126R+0.7152G+0.0722B)，对比度=(L1+0.05)/(L2+0.05)。
> 引擎：math_computation python 回执（Computation/vibe-math-v4-*/script.py,2026-10-04)。
> 判据：正文 ≥4.5:1；大字（≥15px 600)/图标 ≥3:1。

## Dark 主题（墨绿黑底）

| 配对 | 实算 | 判定 |
|---|---|---|
| textPrimary #E8F5EE on SurfaceCanvas #0D1511 | 16.54 | PASS 正文 |
| textPrimary #E8F5EE on Card #14201A | 14.97 | PASS 正文 |
| textSecondary #9FB8AB on Card #14201A | 7.93 | PASS 正文 |
| textSecondary #9FB8AB on SurfaceCanvas #0D1511 | 8.76 | PASS 正文 |
| textTertiary #6E8579 on Card #14201A | 4.23 | PASS 大字/图标 |
| textTertiary #6E8579 on SurfaceCanvas #0D1511 | 4.67 | PASS 正文 |
| textDisabled #4A5A50 on Card #14201A | 2.29 | 禁用语义位（WCAG 豁免：disabled 文本无对比要求） |
| textOnAccent #072B1D on Accent500 #3ED598 | 8.14 | PASS 正文 |
| **误配检查** textPrimary #E8F5EE on Accent500 #3ED598 | 1.68 | **FAIL——白字 on 薄荷绿的黑历史（t53 1.88 同族），禁止此配对** |
| textPrimary #E8F5EE on Selected #1E3A2C | 11.04 | PASS 正文 |
| textSecondary #9FB8AB on Raised #22362C | 6.08 | PASS 正文 |

## Light 主题「薄荷清晨」(t62 默认）

| 配对 | 实算 | 判定 |
|---|---|---|
| textPrimary #14201A on Canvas #F6FBF7 | 16.03 | PASS 正文 |
| textPrimary #14201A on Card #FFFFFF | 16.78 | PASS 正文 |
| textOnAccent #052E1F on Accent500 #3ED598 | 7.89 | PASS 正文 |
| textSecondary #4A5A50 on Canvas #F6FBF7 | 6.99 | PASS 正文 |
| textSecondary #4A5A50 on Card #FFFFFF | 7.32 | PASS 正文 |
| textTertiary #6E8579 on Card #FFFFFF | 3.97 | PASS 大字/图标 |

## 结论

1. **token 层全合格**（禁用位=豁免）。用户"看不清"根因不在 token 值。
2. 根因一=**默认主题 Dark 与亮色裁定相悖**（t62 修复：ThemeService.Current=Light+App.xaml 合并 Light).
3. 根因二=误配白字 on accent(1.68/1.88)=**已全局杜绝**（TextOnAccent 深字令牌+页面绑定点 t53/t62 审查）。
4. 禁用位 2.29 为 WCAG 豁免（disabled 无要求），保留语义降亮是标准做法。
