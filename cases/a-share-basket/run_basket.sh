#!/usr/bin/env bash
# 真实 A 股样本篮：11 家公司端到端跑通指标 → 同业对比 → 逐公司风险 → 多公司矩阵。
#
# 数据来源：A（financial-extraction）对 11 家公司 2025 年年报的抽取结果。
# 不是合成数据，每个科目带年报页码。
#
# 用法：
#   bash run_basket.sh                    # 用 inputs/ 里已有的 B 输入
#   bash run_basket.sh /path/to/A/extracted   # 从 A 的抽取结果重新生成输入
set -euo pipefail
cd "$(dirname "$0")"
ROOT="../.."

if [ $# -ge 1 ]; then
  echo "[1/7] 从 A 的抽取结果生成 B 输入：$1"
  python3 "$ROOT/data-bridge/scripts/from_a_extract.py" --dir "$1" --out-dir inputs
else
  echo "[1/7] 使用已有 inputs/（共 $(ls inputs/*.json | wc -l | tr -d ' ') 家公司）"
fi

echo "[2/7] 计算指标"
mkdir -p ratios
for f in inputs/*.json; do
  b=$(basename "$f" .json); b=${b#input_}
  python3 "$ROOT/financial-diagnosis/scripts/compute_ratios.py" -i "$f" -o "ratios/$b.json" >/dev/null
  printf "      %s\n" "$b"
done

echo "[3/7] 同业对比（每家公司对其余 N-1 家）"
mkdir -p comparison
for f in ratios/*.json; do
  b=$(basename "$f" .json)
  python3 "$ROOT/risk-radar/scripts/build_comparison.py" \
    --target "$f" --peers ratios --out "comparison/$b.json" >/dev/null 2>&1 || \
    echo "      [warn] $b 对比未生成（样本不足或行业不一致）"
done

echo "[4/7] 逐公司风险判定（E01/E04/E02/S01/P06 启用同业分位阈值）"
# 这一步是本轮补的：此前只有 risk_matrix.json 带同业阈值，D 读的是逐公司输出，
# 主输出里看不到 peer_p75/peer_p25，动态阈值等于没接上。
mkdir -p risk
for f in ratios/*.json; do
  b=$(basename "$f" .json)
  if [ -f "comparison/$b.json" ]; then
    python3 "$ROOT/risk-radar/scripts/detect_risks.py" \
      --ratios "$f" --rules "$ROOT/risk-radar/risk_rules.json" \
      --comparison "comparison/$b.json" --pretty -o "risk/$b.json" >/dev/null
  else
    python3 "$ROOT/risk-radar/scripts/detect_risks.py" \
      --ratios "$f" --rules "$ROOT/risk-radar/risk_rules.json" \
      --pretty -o "risk/$b.json" >/dev/null
  fi
  printf "      %s\n" "$b"
done

echo "[5/7] 生成多公司风险矩阵（启用同业分位阈值）"
python3 "$ROOT/risk-radar/scripts/build_risk_matrix.py" \
  --diag-dir ratios \
  --rules "$ROOT/risk-radar/risk_rules.json" \
  --comparison-dir comparison \
  --pretty -o risk_matrix.json

echo "[6/7] 生成矩阵看板"
python3 "$ROOT/scripts_build_matrix.py" --matrix risk_matrix.json --out risk_matrix.html

echo "[7/7] 生成同业对比页（目标：600519 茅台，板块池 BK1277 白酒Ⅱ）"
POOL="$ROOT/risk-radar/data/peer_samples/boards/BK1277.json"
if [ -f "$POOL" ]; then
  python3 "$ROOT/risk-radar/scripts/build_peer_view.py" \
    --ratios-dir ratios --board-pool "$POOL" --target 600519 \
    --pretty -o peer_view.json
  python3 "$ROOT/scripts_build_peer_view.py" --view peer_view.json --out peer_view.html
else
  echo "      [warn] 无白酒板块池，跳过同业对比页。建池："
  echo "      python3 $ROOT/risk-radar/scripts/fetch_industry_samples.py --code 600519 --write"
fi

echo
echo "完成："
echo "  $(pwd)/ratios/               逐公司指标"
echo "  $(pwd)/comparison/           逐公司同业对比"
echo "  $(pwd)/risk/                 逐公司风险（含 peer_p75/peer_p25 阈值）"
echo "  $(pwd)/risk_matrix.json"
echo "  $(pwd)/risk_matrix.html"
echo "  $(pwd)/peer_view.json"
echo "  $(pwd)/peer_view.html"
