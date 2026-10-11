# FinScope · D 模块 — Agent 编排与总集成

本文件说明 FinScope 小组作业中 D 部分的工作内容，方便 A/B/C/E 对接。

## 一句话职责

把 A（财报抽取）、B（指标诊断与风险）、C（估值）三个 Skill 串成一条能跑通的 Agent 链路，在末端生成简易投研报告，并输出统一的数据接口给 E 做前端展示。

## 我负责什么

| 事项 | 说明 |
| --- | --- |
| 总 Workflow | 定义从上传年报到最后出报告的完整执行顺序 |
| 统一数据 Schema | 定义 A/B/C/E 共用的数据对象，全项目对接的基础 |
| 编排调用 | 按顺序调用 A/B/C，负责模块之间的数据传递 |
| 全流程测试 | 用样例年报跑通整条链路，记录每一步的输入与输出 |
| Debug | 定位跨模块问题，协调各方对齐接口 |

这五项之外，D 还负责 Report Generation Skill，把前面几个模块的结果组合成一份简易投研报告。

## 统一数据 Schema

这是 D 交付里最关键的一项。A、B、C 各填其中一部分，E 只读不写。

```json
{
  "company":    { "name": "", "ticker": "", "industry": "", "report_period": "" },
  "financials": {  },
  "ratios":     {  },
  "risks":      [  ],
  "valuation":  { "comps": {  }, "dcf": {  } },
  "sources":    [  ]
}
```

字段归属：

| 字段 | 负责人 | 说明 |
| --- | --- | --- |
| company | D 定义，A 补全 | 公司名称、代码、行业、报告期 |
| financials | A | 三表与关键科目抽取结果 |
| ratios | B | 成长、盈利、偿债、营运、现金流质量 |
| risks | B | 风险条目列表 |
| valuation | C | comps 与 dcf 两块 |
| sources | A/B/C 各自补充 | 数据来源与年报页码 |
| 全字段 | E 只读 | 不重新计算任何数据 |

## 调用链路

```
用户上传年报 PDF
  → Financial Extraction    → financial_data.json     (A)
  → Financial Diagnosis     → financial_analysis.json (B)
  → Risk Radar              → risk_analysis.json      (B)
  → Valuation (Comps + DCF) → valuation.json          (C)
  → Report Generation       → final_report.json / HTML (D)
  → 交给 E 做前端展示
```

每一步的产物都回填进上面那个统一对象，下游模块读的始终是同一个结构。

## 目录结构

拟定的 D 模块目录（仓库中位于 `03_Agent/`）：

```
03_Agent/
├── orchestrator/   编排逻辑、Skill 调用顺序、错误处理
├── schema/         统一数据接口定义
├── config/         配置
├── tests/          全流程测试用例与样例数据
├── Orchestrator.md 工作流说明
└── README.md       本文件
```

## 怎么和我对接

- **A / B / C**：按上面的 Schema 填自己那部分。交付不只是 SKILL.md，还要带上接口定义（INPUT/OUTPUT_SCHEMA.md）和最小可运行的 demo，我才能接得上，按顺序调用。
- **E**：不需要打开任何 Skill 文件，只读最终的 report JSON 就能渲染全部页面。
- **优先顺序**：先把接口定下来，再写各自的 Skill。接口变了要及时同步，否则下游要重做。

## 验收标准

A + B + C 一条链跑通：上传年报 → A → B → Risk → C → Report，输出统一的 report JSON。

## 进度与待办

见 `00_Project/TODO.md`。

---

文档类型：D 模块说明 | 项目：FinScope
