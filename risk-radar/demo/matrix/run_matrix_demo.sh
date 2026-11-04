#!/usr/bin/env bash
# 多公司风险矩阵 · 一键复现
# 生成 3 家合成演示公司 → 算指标 → 拼矩阵 → 渲染 HTML
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd ../../.. && pwd)"

echo "== 1/4 生成演示输入 =="
python3 generate_demo_inputs.py

echo
echo "== 2/4 计算指标 =="
for f in a b c; do
  python3 "$ROOT/financial-diagnosis/scripts/compute_ratios.py" \
    -i "inputs/company_$f.json" -o "ratios/company_$f.json"
done

echo
echo "== 3/4 拼装矩阵 =="
python3 "$ROOT/risk-radar/scripts/build_risk_matrix.py" \
  --diag-dir ratios \
  --rules "$ROOT/risk-radar/risk_rules.json" \
  --pretty -o risk_matrix.json

echo
echo "== 4/4 渲染 HTML =="
python3 "$ROOT/scripts_build_matrix.py" --matrix risk_matrix.json --out risk_matrix.html

echo
echo "完成：$(pwd)/risk_matrix.html"
echo "提醒：公司均为合成演示数据，不得作为真实结论引用。"
