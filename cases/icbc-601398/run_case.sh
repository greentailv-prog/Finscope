#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 真实案例 · 中国工商银行（601398.SH）端到端复算
#
# 输出四份产物：
#   1. output_ratios.json          银行业口径的指标结果
#   2. output_risks.json           银行业剖面下的风险诊断
#   3. output_risks_generic.json   【对照组】误用制造业通用口径的结果
#   4. dashboard.html              可视化看板
#
# 用法: bash run_case.sh
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="${PYTHON:-python3}"

echo "FinRadar · 真实案例复算 —— 中国工商银行 601398.SH"
echo "工作区根目录: $ROOT"
echo

# ---------- 1. 指标 ---------- #
echo "[1/4] 指标计算（financial-diagnosis）"
"$PY" "$ROOT/financial-diagnosis/scripts/compute_ratios.py" \
      -i "$HERE/input_financials.json" \
      -o "$HERE/output_ratios.json" --pretty
echo

# ---------- 2. 风险（正确口径） ---------- #
echo "[2/4] 风险诊断 —— 银行业剖面"
"$PY" "$ROOT/risk-radar/scripts/detect_risks.py" \
      --ratios "$HERE/output_ratios.json" \
      --rules  "$ROOT/risk-radar/risk_rules.json" \
      --industry banking \
      -o "$HERE/output_risks.json" --pretty
echo

# ---------- 3. 风险（对照组：误用制造业口径） ---------- #
echo "[3/4] 风险诊断 —— 对照组：误用制造业通用口径"
"$PY" - "$HERE" <<'PYEOF'
import json, io, sys
here = sys.argv[1]
d = json.load(io.open(here + "/input_financials.json", encoding="utf-8"))
# 故意把行业信息抹掉，伪装成"没识别出这是银行"
d["meta"]["industry_profile"] = "general"
d["meta"]["wacc"] = 0.09
d["company"]["industry"] = "制造业（错误归类对照组）"
json.dump(d, io.open(here + "/_tmp_as_manufacturing.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
PYEOF

"$PY" "$ROOT/financial-diagnosis/scripts/compute_ratios.py" \
      -i "$HERE/_tmp_as_manufacturing.json" \
      -o "$HERE/_tmp_gen_ratios.json" --pretty >/dev/null

"$PY" "$ROOT/risk-radar/scripts/detect_risks.py" \
      --ratios "$HERE/_tmp_gen_ratios.json" \
      --rules  "$ROOT/risk-radar/risk_rules.json" \
      --industry manufacturing \
      -o "$HERE/output_risks_generic.json" --pretty
rm -f "$HERE/_tmp_as_manufacturing.json" "$HERE/_tmp_gen_ratios.json"
echo

# ---------- 4. 看板 ---------- #
echo "[4/4] 生成可视化看板"
"$PY" "$ROOT/scripts_build_dashboard.py" \
      --diag "$HERE/output_ratios.json" \
      --risk "$HERE/output_risks.json" \
      --out  "$HERE/dashboard.html" --note real
echo

echo "全部完成。产物："
echo "  $HERE/output_ratios.json"
echo "  $HERE/output_risks.json"
echo "  $HERE/output_risks_generic.json   ← 对照组"
echo "  $HERE/dashboard.html"
