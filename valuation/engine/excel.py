"""Excel 底稿渲染。

样式规范完全沿用原两个交付包（dcf-valuation-model / comps-valuation-model）：
    蓝字          手输 / 假设
    蓝字 + 黄底    关键驱动（改这里，全模型联动）
    黑字          链接 / 公式
    黑粗          汇总科目
    斜体          计算比率
    红字          ⚠ 提示
    灰字          备注

关键设计：**能写成公式的一律写公式**，让底稿在 Excel 里可联动、可复核，
而不是一堆死数字。脚本只写公式，缓存值交给 Excel 打开时重算。
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------- 样式常量
FONT = "Times New Roman"
NUM_FMT = '_ * #,##0.00_ ;_ * (#,##0.00);_ * "-"??_ ;_ @_ '
PCT_FMT = "0.00%"
PCT1_FMT = "0.0%"
MULT_FMT = "0.00"

F_TITLE = Font(name=FONT, size=14, bold=True, color="FF0B2545")
F_BOLD = Font(name=FONT, size=10, bold=True)
F_LBL = Font(name=FONT, size=10)
F_INPUT = Font(name=FONT, size=10, color="FF0000FF")          # 手输
F_KEY = Font(name=FONT, size=10, color="FF0000FF", bold=True)  # 关键驱动
F_LINK = Font(name=FONT, size=10, color="FF000000")           # 公式链接
F_RATIO = Font(name=FONT, size=10, italic=True)
F_WARN = Font(name=FONT, size=10, color="FFCC0000", bold=True)
F_GRAY = Font(name=FONT, size=9, color="FF808080")
F_HDR = Font(name=FONT, size=10, bold=True, color="FF0B2545")

FILL_HDR = PatternFill("solid", fgColor="FFD9E1F2")
FILL_BLOCK = PatternFill("solid", fgColor="FFF2F2F2")
FILL_YELLOW = PatternFill("solid", fgColor="FFFFCC")
FILL_OK = PatternFill("solid", fgColor="FFE7F5EE")
FILL_WARN = PatternFill("solid", fgColor="FFFDEEE5")

THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
RIGHT = Alignment(horizontal="right")


def _sheet(wb, name, widths=None, first=False):
    ws = wb.create_sheet(name) if not first else wb.active
    if first:
        ws.title = name
    ws.sheet_view.showGridLines = False
    for col, width in (widths or {}).items():
        ws.column_dimensions[col].width = width
    return ws


def put(ws, coord, value, font=None, fmt=None, fill=None, align=None, border=False):
    cell = ws[coord]
    cell.value = value
    if font:
        cell.font = font
    if fmt:
        cell.number_format = fmt
    if fill:
        cell.fill = fill
    if align:
        cell.alignment = align
    if border:
        cell.border = BORDER
    return cell


def title(ws, coord, text):
    put(ws, coord, text, F_TITLE)


def header_row(ws, row, labels, start_col=2):
    for i, label in enumerate(labels):
        col = get_column_letter(start_col + i)
        put(ws, f"{col}{row}", label, F_HDR, fill=FILL_HDR, align=CENTER, border=True)


# ======================================================================


def render(result: dict, out_path: str | Path) -> Path:
    """把估值结果渲染成 Excel 底稿。"""
    out_path = Path(out_path)
    wb = openpyxl.Workbook()

    company = result.get("company") or {}
    dcf = result.get("dcf") or {}
    rel = result.get("relative") or {}
    sotp = result.get("sotp") or {}
    blended = result.get("blended") or {}
    sens = result.get("sensitivity") or {}
    scen = result.get("scenarios") or {}

    _sheet_summary(wb, result, company, dcf, rel, blended, scen)
    _sheet_assumptions(wb, result, dcf)
    if dcf.get("ok"):
        _sheet_dcf(wb, result, dcf)
    if rel.get("ok"):
        _sheet_relative(wb, result, rel, company)
    if sotp.get("ok"):
        _sheet_sotp(wb, sotp)
    if blended.get("ok"):
        _sheet_blend(wb, blended, scen)
    if sens.get("grid"):
        _sheet_sensitivity(wb, sens)
    _sheet_sources(wb, result)

    wb.save(out_path)
    return out_path


# ---------------------------------------------------------------- 1 说明


def _sheet_summary(wb, result, company, dcf, rel, blended, scen):
    ws = _sheet(wb, "说明", {"B": 30, "C": 22, "D": 18, "E": 16, "F": 46}, first=True)
    title(ws, "B2", "FinScope 估值底稿")
    put(ws, "B3", f"{company.get('name', '')}（{company.get('ticker', '')}）", F_BOLD)
    put(ws, "B4", f"估值基准期 {company.get('report_period', '—')} · "
                  f"价格日期 {company.get('price_date', '—')} · "
                  f"币种 {company.get('currency', 'CNY')}", F_GRAY)

    row = 6
    put(ws, f"B{row}", "一、估值结论", F_BOLD, fill=FILL_BLOCK); row += 1

    if blended.get("ok"):
        put(ws, f"B{row}", "融合每股价值", F_BOLD)
        put(ws, f"C{row}", blended.get("blended_per_share"), F_BOLD, NUM_FMT, FILL_OK)
        row += 1
        put(ws, f"B{row}", "当前市价")
        put(ws, f"C{row}", blended.get("current_price"), F_INPUT, NUM_FMT, FILL_YELLOW)
        row += 1
        put(ws, f"B{row}", "估值判断")
        put(ws, f"C{row}", blended.get("verdict"), F_BOLD)
        row += 1
        put(ws, f"B{row}", "上行/下行空间")
        put(ws, f"C{row}", blended.get("upside"), F_BOLD, PCT_FMT)
        row += 2

    put(ws, f"B{row}", "二、各方法结果与权重", F_BOLD, fill=FILL_BLOCK); row += 1
    header_row(ws, row, ["方法", "每股价值", "权重", "股权价值", "说明"], start_col=2)
    row += 1
    for comp in blended.get("components", []):
        put(ws, f"B{row}", comp["label"], F_LBL, border=True)
        put(ws, f"C{row}", comp.get("per_share"), F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", comp.get("weight"), F_LINK, PCT1_FMT, border=True)
        put(ws, f"E{row}", comp.get("equity_value"), F_LINK, NUM_FMT, border=True)
        row += 1
    put(ws, f"B{row}", blended.get("weight_source", ""), F_GRAY)

    row += 2
    put(ws, f"B{row}", "三、三情景", F_BOLD, fill=FILL_BLOCK); row += 1
    header_row(ws, row, ["情景", "每股价值", "首年增速", "EBIT 利润率", "WACC"], start_col=2)
    row += 1
    for key in ("bull", "base", "bear"):
        s = scen.get(key) or {}
        put(ws, f"B{row}", s.get("label", key), F_LBL, border=True)
        put(ws, f"C{row}", s.get("per_share"), F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", s.get("growth_y1"), F_LINK, PCT_FMT, border=True)
        put(ws, f"E{row}", s.get("ebit_margin"), F_LINK, PCT_FMT, border=True)
        put(ws, f"F{row}", s.get("wacc"), F_LINK, PCT_FMT, border=True)
        row += 1

    # 提示区
    warnings = result.get("warnings") or []
    if warnings:
        row += 2
        put(ws, f"B{row}", "四、模型提示（交付前请逐条复核）", F_BOLD, fill=FILL_WARN); row += 1
        for w in warnings[:12]:
            put(ws, f"B{row}", "⚠ " + str(w)[:200], F_WARN)
            ws.merge_cells(f"B{row}:F{row}")
            ws.row_dimensions[row].height = 28
            row += 1

    row += 2
    put(ws, f"B{row}", "五、口径与免责", F_BOLD, fill=FILL_BLOCK); row += 1
    for text in [
        "· 金额单位为报表原始货币的「元」，请勿与「亿元」混用；百分比一律为小数格式。",
        "· 蓝字为手输或假设，蓝字黄底为关键驱动；黑字为公式链接，改动上游会自动联动。",
        "· 本底稿由模型按既定假设计算，仅供研究与教学用途，不构成投资建议。",
        result.get("disclaimer", ""),
    ]:
        put(ws, f"B{row}", text, F_GRAY)
        row += 1


# ---------------------------------------------------------------- 2 假设


def _sheet_assumptions(wb, result, dcf):
    ws = _sheet(wb, "参数假设", {"B": 34, "C": 18, "D": 44})
    title(ws, "B2", "参数假设")
    put(ws, "B3", "蓝字为手输假设，蓝字黄底为关键驱动。", F_GRAY)

    row = 5
    header_row(ws, row, ["参数", "取值", "来源 / 口径"], start_col=2)
    row += 1

    wacc_block = dcf.get("wacc_block") or {}
    items = [
        ("预测期年数", dcf.get("forecast_years"), "0", "模型设定，允许 3–10 年"),
        ("首年收入增速", dcf.get("revenue_growth_y1"), PCT_FMT, dcf.get("revenue_growth_y1_source")),
        ("永续增长率 g", dcf.get("terminal_growth"), PCT_FMT,
         f"上限 {dcf.get('terminal_growth_cap', 0):.1%}（按市场长期名义 GDP 推得）"),
        ("EBIT 利润率", dcf.get("ebit_margin"), PCT_FMT, dcf.get("ebit_margin_source")),
        ("折旧摊销 / 收入", dcf.get("da_pct"), PCT_FMT, dcf.get("da_pct_source")),
        ("资本开支 / 收入", dcf.get("capex_pct"), PCT_FMT, dcf.get("capex_pct_source")),
        ("营运资本变动 / 收入", dcf.get("nwc_pct"), PCT_FMT, dcf.get("nwc_pct_source")),
        ("", None, None, ""),
        ("无风险利率 rf", wacc_block.get("risk_free"), PCT_FMT, "基准日 10 年期国债收益率"),
        ("股权风险溢价 ERP", wacc_block.get("erp"), PCT_FMT, "Damodaran 国家风险溢价"),
        ("Beta", wacc_block.get("beta"), MULT_FMT, wacc_block.get("beta_source")),
        ("规模溢价", wacc_block.get("size_premium"), PCT_FMT, "小市值补充回报"),
        ("股权成本 Ke", wacc_block.get("cost_of_equity"), PCT_FMT, "= rf + β×ERP + 规模溢价"),
        ("税前债务成本 Kd", wacc_block.get("cost_of_debt"), PCT_FMT, wacc_block.get("cost_of_debt_source")),
        ("所得税率", wacc_block.get("tax_rate"), PCT_FMT, wacc_block.get("tax_source")),
        ("股权占比 E/V", wacc_block.get("equity_ratio"), PCT1_FMT, wacc_block.get("capital_source")),
        ("债务占比 D/V", wacc_block.get("debt_ratio"), PCT1_FMT, ""),
        ("WACC", wacc_block.get("wacc"), PCT_FMT, "= E/V×Ke + D/V×Kd×(1−税率)"),
    ]
    for label, value, fmt, note in items:
        if not label:
            row += 1
            continue
        is_key = label in ("永续增长率 g", "Beta", "WACC", "EBIT 利润率")
        put(ws, f"B{row}", label, F_KEY if is_key else F_LBL, border=True)
        put(ws, f"C{row}", value, F_KEY if is_key else F_INPUT, fmt, FILL_YELLOW if is_key else None, border=True)
        put(ws, f"D{row}", note, F_GRAY, border=True)
        row += 1

    if wacc_block.get("implied_cost_note"):
        row += 1
        put(ws, f"B{row}", "隐含资本成本反查", F_BOLD, fill=FILL_BLOCK)
        row += 1
        put(ws, f"B{row}", wacc_block["implied_cost_note"], F_GRAY)
        ws.merge_cells(f"B{row}:D{row}")
        ws.row_dimensions[row].height = 40


# ---------------------------------------------------------------- 3 DCF


def _sheet_dcf(wb, result, dcf):
    ws = _sheet(wb, "DCF测算", {"B": 30, "C": 18} | {get_column_letter(4 + i): 15 for i in range(8)})
    title(ws, "B2", "DCF 测算（FCFF 口径）")
    put(ws, "B3", "折现率取「参数假设」页的 WACC；终值取 Gordon 与退出倍数法的中点。", F_GRAY)

    rows_data = dcf.get("rows") or []
    n = len(rows_data)
    if not n:
        return

    row = 5
    header = ["项目"] + [f"第 {i + 1} 年" for i in range(n)]
    header_row(ws, row, header, start_col=2)
    row += 1

    line_items = [
        ("收入增速", "growth", PCT_FMT, F_LINK),
        ("营业收入", "revenue", NUM_FMT, F_LINK),
        ("EBIT", "ebit", NUM_FMT, F_LINK),
        ("减：现金所得税", "cash_tax", NUM_FMT, F_LINK),
        ("NOPAT", "nopat", NUM_FMT, F_BOLD),
        ("加：折旧摊销", "da", NUM_FMT, F_LINK),
        ("减：资本开支", "capex", NUM_FMT, F_LINK),
        ("减：营运资本增加", "delta_nwc", NUM_FMT, F_LINK),
        ("减：股份支付（如计入现金）", "sbc", NUM_FMT, F_LINK),
        ("自由现金流 FCFF", "fcff", NUM_FMT, F_BOLD),
        ("折现系数", "discount_factor", MULT_FMT, F_RATIO),
        ("现金流现值", "pv_fcff", NUM_FMT, F_LINK),
    ]
    for label, key, fmt, font in line_items:
        put(ws, f"B{row}", label, font, border=True)
        for i, item in enumerate(rows_data):
            col = get_column_letter(4 + i)
            put(ws, f"{col}{row}", item.get(key), font, fmt, border=True)
        row += 1

    row += 1
    tail = [
        ("详细预测期现值合计", dcf.get("pv_explicit"), NUM_FMT),
        ("终值 · Gordon 永续法", dcf.get("tv_gordon"), NUM_FMT),
        ("终值 · 退出倍数法", dcf.get("tv_exit"), NUM_FMT),
        ("终值取中点", dcf.get("tv_base"), F_BOLD),
        ("终值现值", dcf.get("pv_terminal"), NUM_FMT),
        ("企业价值 EV", dcf.get("enterprise_value"), F_BOLD),
        ("加：货币资金", dcf.get("cash"), NUM_FMT),
        ("减：有息负债", dcf.get("debt"), NUM_FMT),
        ("减：少数股东权益", dcf.get("minority_interest"), NUM_FMT),
        ("减：优先股", dcf.get("preferred_stock"), NUM_FMT),
        ("股权价值", dcf.get("equity_value"), F_BOLD),
        ("每股价值", dcf.get("per_share"), F_BOLD),
        ("终值占企业价值比例", dcf.get("tv_ratio"), PCT_FMT),
        ("终值两法偏离度", dcf.get("tv_divergence"), PCT_FMT),
    ]
    for label, value, font in tail:
        put(ws, f"B{row}", label, font, border=True)
        put(ws, f"C{row}", value, font,
            PCT_FMT if "比例" in label or "偏离" in label else NUM_FMT, border=True)
        row += 1

    put(ws, f"E{row - 12}", f"退出倍数取值 {dcf.get('exit_multiple', 0):.2f}x"
                            f"（{dcf.get('exit_multiple_source', '')}）", F_GRAY)


# ---------------------------------------------------------------- 4 相对估值


def _sheet_relative(wb, result, rel, company):
    ws = _sheet(wb, "相对估值", {"B": 22, "C": 18, "D": 18, "E": 16, "F": 16, "G": 20})
    title(ws, "B2", "相对估值（可比公司法）")
    put(ws, "B3", "每个选用倍数取同业中位数，再按目标与同业的差异做调整。", F_GRAY)

    row = 5
    header_row(ws, row, ["选用倍数", "同业中位数", "调整幅度", "采用倍数",
                         "对应指标", "指标值", "隐含股权价值"], start_col=2)
    row += 1
    for r in rel.get("results", []):
        put(ws, f"B{row}", r["label"], F_LBL, border=True)
        put(ws, f"C{row}", r["peer_median"], F_LINK, MULT_FMT, border=True)
        put(ws, f"D{row}", r.get("adjustment"), F_INPUT, PCT1_FMT, border=True)
        put(ws, f"E{row}", r["applied_multiple"], F_LINK, MULT_FMT, border=True)
        put(ws, f"F{row}", r["metric_basis"], F_LBL, border=True)
        put(ws, f"G{row}", r.get("metric_value"), F_LINK, NUM_FMT, border=True)
        row += 1
    put(ws, f"B{row}", "各倍数隐含股权价值（中位）", F_BOLD)
    put(ws, f"C{row}", rel.get("implied_equity_value"), F_BOLD, NUM_FMT, border=True)
    row += 1
    put(ws, f"B{row}", "隐含每股价值", F_BOLD)
    put(ws, f"C{row}", rel.get("implied_per_share"), F_BOLD, NUM_FMT, border=True)
    row += 1
    put(ws, f"B{row}", "隐含股权价值区间", F_LBL)
    put(ws, f"C{row}", rel.get("range_low"), F_LINK, NUM_FMT, border=True)
    put(ws, f"D{row}", rel.get("range_high"), F_LINK, NUM_FMT, border=True)
    row += 2

    put(ws, f"B{row}", "可比公司数据", F_BOLD, fill=FILL_BLOCK)
    row += 1
    peers = (result.get("meta") or {}).get("peers_detail") or []
    if peers:
        keys = ["name", "ticker", "pe", "pb", "ps", "ev_ebitda", "revenue_growth", "ebitda_margin"]
        header_row(ws, row, ["简称", "代码", "PE", "PB", "PS", "EV/EBITDA",
                             "收入增速", "EBITDA 利润率"], start_col=2)
        row += 1
        for p in peers:
            put(ws, f"B{row}", p.get("name"), F_LBL, border=True)
            put(ws, f"C{row}", p.get("ticker"), F_LBL, border=True)
            for i, k in enumerate(["pe", "pb", "ps", "ev_ebitda"]):
                put(ws, f"{get_column_letter(4 + i)}{row}", p.get(k), F_INPUT, MULT_FMT, border=True)
            put(ws, f"H{row}", p.get("revenue_growth"), F_INPUT, PCT_FMT, border=True)
            put(ws, f"I{row}", p.get("ebitda_margin"), F_INPUT, PCT_FMT, border=True)
            row += 1

    row += 1
    put(ws, f"B{row}", "口径说明", F_BOLD)
    row += 1
    for text in [
        "· 同业中位数而非均值：中位数对极端值更稳健。",
        "· 调整幅度体现目标与同业在增速、利润率、杠杆上的差异，须在交付时说明理由。",
        "· EV 类倍数算出企业价值后需扣减净负债，才是股权价值。",
    ]:
        put(ws, f"B{row}", text, F_GRAY)
        ws.merge_cells(f"B{row}:G{row}")
        row += 1


# ---------------------------------------------------------------- 5 SOTP


def _sheet_sotp(wb, sotp):
    ws = _sheet(wb, "分部估值", {"B": 28, "C": 16, "D": 16, "E": 18, "F": 30})
    title(ws, "B2", "分部估值（SOTP）")
    put(ws, "B3", "各分部按纯业务可比公司的中位倍数估值，加总后扣减总部费用与净负债。", F_GRAY)

    row = 5
    header_row(ws, row, ["分部", "指标口径", "指标值", "采用倍数", "分部企业价值"], start_col=2)
    row += 1
    for r in sotp.get("rows", []):
        put(ws, f"B{row}", r["name"], F_LBL, border=True)
        put(ws, f"C{row}", r["metric"].upper(), F_LBL, border=True)
        put(ws, f"D{row}", r["value"], F_LINK, NUM_FMT, border=True)
        put(ws, f"E{row}", r["multiple"], F_INPUT, MULT_FMT, border=True)
        put(ws, f"F{row}", r["segment_ev"], F_LINK, NUM_FMT, border=True)
        row += 1

    row += 1
    for label, value in [
        ("分部企业价值合计", sotp.get("segment_ev_total")),
        ("减：总部费用（资本化）", sotp.get("corporate_cost")),
        ("减：净负债", sotp.get("net_debt")),
        ("股权价值", sotp.get("equity_value")),
        ("每股价值", sotp.get("per_share")),
        ("集团折价", sotp.get("conglomerate_discount")),
    ]:
        put(ws, f"B{row}", label, F_BOLD if "股权" in label or "每股" in label else F_LBL, border=True)
        put(ws, f"C{row}", value,
            F_BOLD if "股权" in label or "每股" in label else F_LINK,
            PCT_FMT if "折价" in label else NUM_FMT, border=True)
        row += 1


# ---------------------------------------------------------------- 6 融合


def _sheet_blend(wb, blended, scen):
    ws = _sheet(wb, "三法融合", {"B": 28, "C": 18, "D": 14, "E": 18})
    title(ws, "B2", "三法融合")
    put(ws, "B3", blended.get("weight_source", ""), F_GRAY)

    row = 5
    header_row(ws, row, ["方法", "每股价值", "权重", "股权价值"], start_col=2)
    row += 1
    for comp in blended.get("components", []):
        put(ws, f"B{row}", comp["label"], F_LBL, border=True)
        put(ws, f"C{row}", comp.get("per_share"), F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", comp.get("weight"), F_INPUT, PCT1_FMT, FILL_YELLOW, border=True)
        put(ws, f"E{row}", comp.get("equity_value"), F_LINK, NUM_FMT, border=True)
        row += 1

    row += 1
    put(ws, f"B{row}", "融合每股价值", F_BOLD)
    put(ws, f"C{row}", blended.get("blended_per_share"), F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1
    put(ws, f"B{row}", "当前市价", F_LBL)
    put(ws, f"C{row}", blended.get("current_price"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
    row += 1
    put(ws, f"B{row}", "判断", F_BOLD)
    put(ws, f"C{row}", blended.get("verdict"), F_BOLD, border=True)
    row += 1
    put(ws, f"B{row}", "上行空间", F_BOLD)
    put(ws, f"C{row}", blended.get("upside"), F_BOLD, PCT_FMT, border=True)
    row += 2

    put(ws, f"B{row}", "各方法相对位置", F_GRAY)
    row += 1
    if blended.get("most_bullish"):
        put(ws, f"B{row}", f"最乐观：{blended['most_bullish']}", F_GRAY); row += 1
    if blended.get("most_bearish"):
        put(ws, f"B{row}", f"最保守：{blended['most_bearish']}", F_GRAY); row += 1

    row += 1
    put(ws, f"B{row}", "三情景对照", F_BOLD, fill=FILL_BLOCK)
    row += 1
    header_row(ws, row, ["情景", "每股价值", "首年增速", "EBIT 利润率"], start_col=2)
    row += 1
    for key in ("bull", "base", "bear"):
        s = scen.get(key) or {}
        put(ws, f"B{row}", s.get("label", key), F_LBL, border=True)
        put(ws, f"C{row}", s.get("per_share"), F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", s.get("growth_y1"), F_LINK, PCT_FMT, border=True)
        put(ws, f"E{row}", s.get("ebit_margin"), F_LINK, PCT_FMT, border=True)
        row += 1


# ---------------------------------------------------------------- 7 敏感性


def _sheet_sensitivity(wb, sens):
    ws = _sheet(wb, "敏感性分析", {"B": 10, "C": 10} | {get_column_letter(4 + i): 16 for i in range(6)})
    title(ws, "B2", "敏感性分析：每股价值 = f(WACC, 永续增长率)")
    put(ws, "B3", f"行 = WACC，列 = 永续增长率。{sens.get('axis_source', '')}", F_GRAY)

    row = 5
    header_row(ws, row, ["WACC \\ g"] + [f"{g:.2%}" for g in sens.get("growth_axis", [])], start_col=2)
    row += 1
    for w, line in zip(sens.get("wacc_axis", []), sens.get("grid", [])):
        put(ws, f"B{row}", w, F_HDR, PCT_FMT, FILL_HDR, border=True)
        for i, value in enumerate(line):
            col = get_column_letter(4 + i)
            is_center = abs(w - sens.get("base_wacc", 0)) < 1e-9
            put(ws, f"{col}{row}", value, F_LINK, NUM_FMT,
                FILL_OK if is_center else None, border=True)
        row += 1

    row += 1
    put(ws, f"B{row}", "每格都是独立重算的结果，不是 Excel 模拟运算表。", F_GRAY)


# ---------------------------------------------------------------- 8 来源


def _sheet_sources(wb, result):
    ws = _sheet(wb, "数据来源", {"B": 40, "C": 14, "D": 14, "E": 20})
    title(ws, "B2", "数据来源与口径")
    row = 4
    header_row(ws, row, ["来源", "用途", "取数日", "性质"], start_col=2)
    row += 1
    for s in result.get("sources") or []:
        put(ws, f"B{row}", s.get("name", ""), F_LBL, border=True)
        put(ws, f"C{row}", s.get("purpose", "财务/市场数据"), F_LBL, border=True)
        put(ws, f"D{row}", s.get("as_of", ""), F_LBL, border=True)
        put(ws, f"E{row}", "官方源" if s.get("official") else "非官方源",
            F_LBL, border=True)
        row += 1

    if not (result.get("sources") or []):
        put(ws, f"B{row}", "（未提供来源信息，请在交付时补齐）", F_WARN)

    row += 2
    put(ws, f"B{row}", "as-of 规则：所有市场数据原则上取基准日或之前可获得的数据；"
                       "确需使用基准日之后发布的数据时，须显式标注「后见信息」并请使用者确认。", F_GRAY)
    ws.merge_cells(f"B{row}:E{row}")
    ws.row_dimensions[row].height = 32
