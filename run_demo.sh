#!/bin/bash
# FinRadar B 部分 —— 一键跑通全流程演示
# 用法: bash run_demo.sh
set -e

PY="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=============================================================="
echo " FinRadar / B 模块演示：财务指标计算 → 财务风险诊断"
echo "=============================================================="
echo ""

echo "[1/3] 检查 Python ..."
"$PY" --version

echo ""
echo "[2/3] financial-diagnosis：计算财务指标"
echo "--------------------------------------------------------------"
cd "$ROOT/financial-diagnosis"
"$PY" scripts/compute_ratios.py \
    --input  demo/input_financials.json \
    --output demo/output_ratios.json --pretty

echo ""
echo "[3/3] risk-radar：识别财务风险并生成证据链"
echo "--------------------------------------------------------------"
cd "$ROOT/risk-radar"
"$PY" scripts/detect_risks.py \
    --ratios ../financial-diagnosis/demo/output_ratios.json \
    --rules  risk_rules.json \
    --output demo/output_risks.json --pretty

# 同步一份 diagnosis 输出作为 risk-radar 的 demo 输入归档
"$PY" - <<'PY'
import json, io, os
src = os.path.join("..", "financial-diagnosis", "demo", "output_ratios.json")
d = json.load(io.open(src, encoding="utf-8"))
d["_note"] = ("本文件是 risk-radar 的演示输入，等于 financial-diagnosis 的输出"
              "（即 D 在统一数据对象里传给 Risk Radar 的那一段）。由脚本生成，不要手改。")
json.dump(d, io.open(os.path.join("demo", "input_analysis.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
PY

echo ""
echo "=============================================================="
echo " 完成。产出文件："
echo "   financial-diagnosis/demo/output_ratios.json   （65 个指标 + 三段归因）"
echo "   risk-radar/demo/output_risks.json             （40 条规则 + 证据链）"
echo ""
echo " 下一步：打开可视化看板"
echo "   python3 scripts_build_dashboard.py && open $ROOT/B_demo_dashboard.html"
echo ""
echo " 真实案例（工商银行，数据来自巨潮公开披露年报）："
echo "   cd cases/icbc-601398 && bash run_case.sh"
echo "   open cases/icbc-601398/dashboard.html"
echo "=============================================================="
