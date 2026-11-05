# FinScope C v3.2｜三项估值能力升级与验收说明

**交付定位**：基于 C v3.1 源码实施后端代码优化，并用可复现的合成企业情景测试真实公式、三表联动与审核闸门。保留原先的 API、历史规则与前端目录。该版本改进了分析流程与错误拦截，但**不承诺市场价格与内在价值接近，也未提供未经授权的全市场实时数据**。

## 一、三项问题的完成情况

| 待解决问题 | 本次完成的工程能力 | 尚需完成的真实数据/人工确认 |
|---|---|---|
| 1. 真实业务可比公司库 | 新增 `valuation/config/verified_peer_research.json`，建立罗博特科光电子与光伏设备双业务候选池；记录产品、客户、证据网址、样本纯度、相似性及审批状态；新增分部/时点/口径/币种/审核人多重闸门与研究 API；手工传入罗博特科可比公司也不能绕过 | 每家候选的同日行情、规范化财务与纯业务分部数据、分析师最终审批。当前全部设为 `approved:false`，**未生成虚构可比倍数**。其他公司的业务证据库需逐家扩充 |
| 2. 经营预测与三表联动 | 新增 `valuation/research/driver_forecast.py`，支持分部收入、增速、毛利、费用、税、应收周转天数、存货周转天数、应付周转天数、D&A、CAPEX、债务、分红、股权融资；联动 FCFF、利润表、现金流、资产负债表；替代 DCF 单一利润率与营运资本比例外推 | 标的公司各业务基期报表、并购后收入确认、合理经营情景、集团母子股本及现金负债事实需接入 D 统一财务对象；缺期初资产负债信息时仅出运营 FCFF，**不能谎称完整三表** |
| 3. Excel 公式与数值验证 | 生成 5 表**可编辑公式底稿**（分部收入与EBIT、驱动参数、三表联动、财务一致性校验、DCF验证）；217 个公式，支持跨工作表推导；45 项独立算术审计；`artifact_tool` 公式再求值及无错误扫描；原生 Excel COM 校验脚本 | 2026-11-05 已在 Windows Excel 16.0 原生重算，217 个公式 0 错误，**EXCEL_OK**，报告见 `SYNTHETIC_ONLY_three_statement_model.native_check.json`；四家公司的 18 表底稿同样通过 |

## 二、与提供 Skills 的对照

- `comps-valuation-model` 的逻辑以**估值基准日一致、同行经营方式可比、规范化倍数、输入数据可复核、Excel重算**为核心。本版本按这些要求设立明确阻断条件。
- `finance-skills-main/plugins/market-analysis/skills/company-valuation` 的 DCF/relative/SOTP 方法框架已经映射到业务驱动预测和分部核验。它所举的美国市场无风险利率、默认权重、终值折中仅用于学习，不能不加调整直接用在 A 股项目。
- C v3.1 原有的**负股权价值待核验、WACC不自动贴合市场价格、SOTP缺少真实分部时禁用、不能用行业代理凑满样本**继续保留。

## 三、业务可比库用法与责任划分

`GET /api/valuation/companies/300757/peer-research?as_of=2026-11-04` 返回光电子/光伏业务拆分、候选企业、相似产品、产品来源链接和待核验状态。候选研究不等于自动推荐使用。

`valuation.research.peer_registry.validate_for_comps()` 只批准**相同业务分部、相同估值基准日、同币种、同LYR/TTM/NTM口径、同一倍数类型**中至少两家通过的样本。允许正式研究人员显式提供 `analyst_approved / approved_by / approval_date / market_as_of / data_source_url / caliber / currency`；多元化集团还须 `pure_play_financials_confirmed` 和 `pure_play_financials_source_url`。禁止未经审批把光模块制造商与光模块设备制造商混为一组。

罗博特科（300757）同业候选尚无经过审核的当前市场倍数，因此本交付**不会输出该股票的真实 Comps 目标价**。应先在后端中填入受支持的来源与分部盈利数据，审完再运行，并非通过调高市价反推倍数。

## 四、分业务经营预测输入结构

原 API `POST /api/valuation/run` 或 `POST /api/valuation/session/{id}/run` 的估值输入新增顶层 `operating_forecast`（亦接受 `meta.operating_forecast`），核心字段：

```json
{
  "operating_forecast": {
    "base_year": 2025,
    "as_of": "2025-12-31",
    "years": 5,
    "segments": [
      {"name":"业务A","base_revenue":60000000000,"growth_path":[0.10,0.08,0.06,0.05,0.04],"gross_margin_path":[0.45,0.45,0.45,0.45,0.45],"opex_ratio_path":[0.16,0.16,0.16,0.16,0.16],"source_url":"synthetic:test"}
    ],
    "tax_rate":0.20,
    "dso_days_path":[60,60,60,60,60],
    "dio_days_path":[50,50,50,50,50],
    "dpo_days_path":[65,65,65,65,65],
    "da_ratio_path":[0.04,0.04,0.04,0.04,0.04],
    "capex_ratio_path":[0.07,0.07,0.07,0.07,0.07],
    "other_nwc_opening":0,
    "other_nwc_ratio_path":[0,0,0,0,0],
    "opening_balance": {
      "cash":10000000000,"receivables":20000000000,"inventory":10000000000,"ppe":50000000000,"other_assets":10000000000,
      "payables":15000000000,"debt":25000000000,"other_liabilities":10000000000,"equity":50000000000
    },
    "interest_rate_path":[0.05,0.05,0.05,0.05,0.05]
  }
}
```

**注意**：此结构中的“业务A”和全部数字均是合成示例，不对应真实上市公司。数值输入统一元；五个年份是预测年度，利率传小数。正式模型必须用多个分部的历史净收入汇总匹配当前年报、完整期初资产负债表，并传入当前股份数、净债务、资本成本与日期等必要信息。

## 五、验收与复算

从交付包根目录执行：

```bash
python -m unittest discover -s valuation/tests -p 'test_v3*py' -v
python -m valuation.tests.build_synthetic_example
python valuation/research/excel_audit.py valuation/output/SYNTHETIC_ONLY_result.json valuation/output/SYNTHETIC_ONLY_three_statement_model.xlsx
python valuation/scripts/validate_with_artifact_tool.py valuation/output/SYNTHETIC_ONLY_three_statement_model.xlsx valuation/output/SYNTHETIC_ONLY_result.json
```

本次测试：**41 项离线代码测试通过**（含 `test_delivery_rules` 的 C1–C4）；合成案例 **45/45项独立数学检查通过**；新底稿 **5个工作表、217个公式、5个预测年度均平衡**，`artifact_tool` 与 Microsoft Excel COM 均可重算并匹配后端 DCF 值；未检出单元格公式错误。

有桌面 Excel 的 Windows 环境运行：

```powershell
powershell -ExecutionPolicy Bypass -File valuation/scripts/excel_native_verify.ps1 -Workbook "valuation/output/SYNTHETIC_ONLY_three_statement_model.xlsx"
```

脚本会调用 `Excel.Application`、`CalculateFullRebuild()`、扫描各表错误值及预测资产负债差异；通过后才标注 `EXCEL_OK`，否则为 `EXCEL_FAIL`。本次交付已在 Windows Excel 16.0 执行，5 表合成底稿和四家 18 表底稿均为 `EXCEL_OK`；对应报告在同目录 `*.native_check.json`。

## 六、接入与替换提醒

- 本版基于上一轮 **FinScope C v3.1 完整源码**进行修改；下载完整包后在原本 v3.1 后端项目之外先独立运行测试，再部署。保留 `/api/valuation/...` 原有 HTTP 入口。
- 新的 `peer-research` 接口只提供**候选证据与审批信息**，不自动获取或编造实时倍数。前端应将 `review_required` 显示为“估值不可用/需业务核验”，不能展示为0元目标价。
- 5表快速底稿专为**完整三表情景**使用；原有非完整三表路径继续沿用原专业18表/兼容12表导出。5表尚未把所有 Comps/SOTP 结果全部合并进同一工作簿。
- 对真实罗博特科，至少需要截至估值时点的A/H股股份、净债务、并购后的完整分部收入与利润、经营资金占用及研发资本化/费用化口径，再做正式估值。
- 避免把“估值值与当前股价差距很大”作为错误的直接判断标准。通过数据、方法与前瞻假设的核验，解释差异来源才是核心。
