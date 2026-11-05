# C v3.3 修订记录（2026-11-05）

依据 D 的 `07_C必须修改项.md` 与三个估值 Skill 的银行口径，完成 C1–C4 和 P1。

## C1 · Excel 与路径

- `run()` 默认 `export_excel=True`；`/from-workflow`、`/run`、会话运行、改参重算都同步生成底稿。
- 底稿按 `<ticker>_<year>_估值底稿.xlsx` 覆盖写入 `valuation/output/`，`excel_path` 返回相对包根路径。
- 18 表优先；`artifact_tool`/`artifact_tool_v2` 都找不到时回退 12 表，`excel_format` 写明。
- 每张表带来源与生成时间（18 表写 A2，12 表写 A1）。
- `scripts/excel_native_verify.ps1` 改为 UTF-8 with BOM，Windows PowerShell 5.1 可直接运行。
- 四家样例和合成案例全部经 Microsoft Excel COM 重算，0 个公式错误；`EXCEL_OK=true` 有 `.native_check.json` 为证。
- `DELIVERY_MANIFEST.md` 只列真实存在的文件。

## C2 · 600519 结果 JSON

- 新增 `valuation/output/600519_2025_result.json`：dcf / comps / scenarios / sensitivity / assumptions / status 均非空。
- 分业务驱动路径也输出 `wacc_g` 5×5 与三情景（`scenario_basis="driver_rows_scaled"`）；
  `growth_margin` 在分部模式下不适用，置 `null` 并写 warning。

## C3 · 银行语义

- 银行/保险/证券：`status="partial"`、`industry_support="limited"`、
  `gate_reason="standard_fcff_unsupported; ddm_used"`；保留 DDM/剩余收益、PB/PE Comps、blended。
- 配置层把「对外支持度」与「标准 FCFF 是否适用」拆成 `support` 和 `standard_fcff_supported`，
  避免改 `support` 时误把 DCF 留回银行模型。
- 地产/REITs 仍为 `unsupported`，只在地没有 NAV/FFO 口径时使用。
- 依据：company-valuation skill 的 method applicability 表（Banks/Insurance：DCF ❌、P/B ✅、SOTP ❌、DDM/excess return fallback；折现率只用股权成本）。

## C4 · 无行情

- `market_data.price=null` → `dcf.per_share=null`、`blended.blended_per_share=null`、
  `scenarios.*.per_share=null`、`sensitivity` 矩阵全 `null`；`equity_value` 保留。
- `warnings` 写「未获取到实时行情，每股价值未计算」。

## P1 · 假设来源

- `source_type="user_scenario"` 改为 `model`，保持 7.5 的四类枚举。

## 其他

- 补回 `tests/reports`、`tests/reports_web` 的回归 fixture；新增 `test_delivery_rules.py`。
- 前端银行判断改为 `ddm.ok && (limited/unsupported 或 gate_reason)`；无 DCF 时经营图表给出 DDM 说明，不再产生 NaN。
- `补丁文件/` 同步为累积补丁，完整包以包根为准。
