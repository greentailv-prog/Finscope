"""Excel 底稿渲染 —— **公式联动的底稿**，不是静态报告。

样式规范沿用原两个交付包（dcf-valuation-model / comps-valuation-model）：
    蓝字          手输 / 假设
    蓝字 + 黄底    关键驱动（改这里，全模型联动）
    黑字          链接 / 公式
    黑粗          汇总科目
    斜体          计算比率
    红字          ⚠ 提示
    灰字          备注

**核心设计：参数假设表是单一真源。**
其余各表一律用公式引用它——改了假设表里的蓝字黄底单元格，
DCF 测算、敏感性矩阵、三法融合会整链重算。这是"底稿"和"报告"的区别。

只有一处例外：说明表的结论文字是静态快照（Excel 里改假设后它不会自动更新），
表内已注明，并提示"改完假设重新导出即可刷新结论"。
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
INT_FMT = "0"

F_TITLE = Font(name=FONT, size=14, bold=True, color="FF0B2545")
F_BOLD = Font(name=FONT, size=10, bold=True)
F_LBL = Font(name=FONT, size=10)
F_INPUT = Font(name=FONT, size=10, color="FF0000FF")            # 手输
F_KEY = Font(name=FONT, size=10, color="FF0000FF", bold=True)    # 关键驱动
F_LINK = Font(name=FONT, size=10, color="FF000000")             # 公式
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
GOLD = Side(style="medium", color="FFFFC000")   # 敏感性矩阵的基准情景格
CENTER = Alignment(horizontal="center", vertical="center")

# ---------------------------------------------------------------- 参数假设表布局
# 这张表是全模型唯一的输入源，其他表按这些地址引用。
#
# **行号不写死**：每次渲染时由 _sheet_assumptions 把真实行号回填进 P。
# 曾经这里是硬编码的（years=5, growth_y1=6 …），而表头也占了第 5 行、
# 数据实际从第 6 行开始，于是整体错位一行——`参数假设!$C$6` 指到了
# "预测期年数"、`$C$5` 指到了表头文字，全模型 580 个格子报 #VALUE!。
# 下面的初值只是**占位**，保证假设表渲染完成前 paddr() 不抛 KeyError。
_P_DEFAULTS = {
    "years": 5,           # 预测期年数
    "growth_y1": 6,       # 首年收入增速
    "ebit_margin": 7,     # EBIT 利润率
    "da_pct": 8,          # 折旧摊销 / 收入
    "capex_pct": 9,       # 资本开支 / 收入
    "nwc_pct": 10,        # 营运资本变动 / 收入
    "g": 11,              # 永续增长率
    "rf": 12,             # 无风险利率
    "erp": 13,            # 股权风险溢价
    "beta": 14,           # Beta
    "ke": 15,             # 股权成本（公式）
    "kd": 16,             # 税前债务成本
    "tax": 17,            # 所得税率
    "e_ratio": 18,        # 股权占比
    "wacc": 19,           # WACC（公式）
    "base_rev": 20,       # 基准年营业收入
    "cash": 21,           # 货币资金
    "debt": 22,           # 有息负债
    "minority": 23,       # 少数股东权益
    "preferred": 24,      # 优先股
    "shares": 25,         # 股本（股）
    "price": 26,          # 当前股价
    "exit_multiple": 27,  # 退出倍数 EV/EBITDA
}
P: dict[str, int | None] = dict(_P_DEFAULTS)
PARAM_SHEET = "参数假设"
PARAM_COL = "C"


def paddr(key: str) -> str:
    """参数假设表里某个参数的绝对地址，供其他表引用。"""
    return f"{PARAM_SHEET}!${PARAM_COL}${P[key]}"


def _sheet(wb, name, widths=None, first=False):
    ws = wb.create_sheet(name) if not first else wb.active
    if first:
        ws.title = name
    ws.sheet_view.showGridLines = False
    for col, width in (widths or {}).items():
        ws.column_dimensions[col].width = width
    return ws


def put(ws, coord, value, font=None, fmt=None, fill=None, align=None, border=False):
    # 防线：openpyxl 会把以 = 开头的字符串当公式写，Excel 会判文件损坏。
    # 但**真正的公式**（我们主动构造的）需要保留——用 formula() 显式标记。
    if isinstance(value, str) and value.startswith("="):
        value = "公式：" + value[1:].lstrip()

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


def formula(ws, coord, expr, font=None, fmt=None, fill=None, align=None, border=False):
    """写公式。与 put 分开，避免被上面的防线误伤。"""
    cell = ws[coord]
    cell.value = expr
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
    out_path = Path(out_path)
    wb = openpyxl.Workbook()

    # P 是模块级字典，跨次渲染必须复位，否则上一次的 _rel_per_share /
    # _sotp_per_share 会残留下来，让「三法融合」指向本次并不存在的表。
    P.clear()
    P.update(_P_DEFAULTS)

    company = result.get("company") or {}
    dcf = result.get("dcf") or {}
    rel = result.get("relative") or {}
    sotp = result.get("sotp") or {}
    blended = result.get("blended") or {}
    sens = result.get("sensitivity") or {}
    scen = result.get("scenarios") or {}

    # 列序：先建参数假设（其他表要引用它），再建其余
    _sheet_assumptions(wb, result, dcf, first=True)
    _sheet_dcf(wb, result, dcf)
    _sheet_relative(wb, result, rel)
    # 分部估值总是出表：没有分部数据时是一张蓝字可手填的空表，
    # 这样「三种方法」在底稿里始终齐全（SOTP 数据免费源取不到）。
    _sheet_sotp(wb, sotp)
    _sheet_blend(wb, result, blended, scen)
    _sheet_sensitivity(wb, result, sens)
    _sheet_sources(wb, result)
    _sheet_summary(wb, result, company, dcf, rel, blended, scen)

    # 说明表挪到最前
    wb.move_sheet("说明", offset=-len(wb.sheetnames) + 1)

    wb.save(out_path)
    return out_path


# ---------------------------------------------------------------- 1 参数假设


def _sheet_assumptions(wb, result, dcf, first=False):
    ws = _sheet(wb, PARAM_SHEET, {"B": 32, "C": 16, "D": 46}, first=first)
    title(ws, "B2", "参数假设 —— 全模型唯一输入源")
    put(ws, "B3", "蓝字为手输假设，蓝字黄底为关键驱动。改这里，其余各表整链重算。", F_GRAY)

    wb_ = dcf.get("wacc_block") or {}
    mkt = result.get("market_data") or {}
    rows = [
        ("years", "预测期年数", dcf.get("forecast_years"), INT_FMT, F_KEY,
         "3–10 年；太长会被终值主导"),
        ("growth_y1", "首年收入增速", dcf.get("revenue_growth_y1"), PCT_FMT, F_KEY,
         dcf.get("revenue_growth_y1_source") or ""),
        ("ebit_margin", "EBIT 利润率", dcf.get("ebit_margin"), PCT_FMT, F_KEY,
         dcf.get("ebit_margin_source") or ""),
        ("da_pct", "折旧摊销 / 收入", dcf.get("da_pct"), PCT_FMT, F_INPUT,
         dcf.get("da_pct_source") or ""),
        ("capex_pct", "资本开支 / 收入", dcf.get("capex_pct"), PCT_FMT, F_INPUT,
         dcf.get("capex_pct_source") or ""),
        ("nwc_pct", "营运资本变动 / 收入", dcf.get("nwc_pct"), PCT_FMT, F_INPUT,
         dcf.get("nwc_pct_source") or ""),
        ("g", "永续增长率 g", dcf.get("terminal_growth"), PCT_FMT, F_KEY,
         f"上限 {dcf.get('terminal_growth_cap') or 0:.1%}（按长期名义 GDP）"),
        (None, None, None, None, None, None),
        ("rf", "无风险利率 rf", wb_.get("risk_free"), PCT_FMT, F_KEY,
         "基准日 10 年期国债收益率"),
        ("erp", "股权风险溢价 ERP", wb_.get("erp"), PCT_FMT, F_KEY,
         "Damodaran 国家风险溢价"),
        ("beta", "Beta", wb_.get("beta"), MULT_FMT, F_KEY, wb_.get("beta_source") or ""),
        ("kd", "税前债务成本 Kd", wb_.get("cost_of_debt"), PCT_FMT, F_INPUT,
         wb_.get("cost_of_debt_source") or ""),
        ("tax", "所得税率", wb_.get("tax_rate"), PCT_FMT, F_KEY,
         wb_.get("tax_source") or ""),
        ("e_ratio", "股权占比 E/V", wb_.get("equity_ratio"), PCT1_FMT, F_KEY,
         wb_.get("capital_source") or ""),
        (None, None, None, None, None, None),
        ("base_rev", "基准年营业收入", (dcf.get("rows") or [{}])[0].get("revenue", 0)
         / (1 + (dcf.get("revenue_growth_y1") or 0)) if dcf.get("rows") else None,
         NUM_FMT, F_INPUT, "金额按「元」填写；DCF 表用它起算"),
        ("cash", "货币资金", dcf.get("cash"), NUM_FMT, F_INPUT, ""),
        ("debt", "有息负债", dcf.get("debt"), NUM_FMT, F_INPUT, ""),
        ("minority", "少数股东权益", dcf.get("minority_interest"), NUM_FMT, F_INPUT, ""),
        ("preferred", "优先股", dcf.get("preferred_stock"), NUM_FMT, F_INPUT, ""),
        ("shares", "股本（股）", mkt.get("shares_outstanding"), NUM_FMT, F_INPUT,
         "用于把股权价值换算成每股价值"),
        ("price", "当前股价", mkt.get("price"), NUM_FMT, F_INPUT,
         "取数日收盘价；用于算上行 / 下行空间"),
        ("exit_multiple", "退出倍数 EV/EBITDA", dcf.get("exit_multiple"), MULT_FMT, F_KEY,
         dcf.get("exit_multiple_source") or ""),
    ]

    row = 5
    header_row(ws, row, ["参数", "取值", "来源 / 口径"], start_col=2)
    row += 1
    for key, label, value, fmt, font, note in rows:
        if label is None:
            row += 1
            continue
        put(ws, f"B{row}", label, font, border=True)
        put(ws, f"C{row}", value, font, fmt,
            FILL_YELLOW if font is F_KEY else None, border=True)
        put(ws, f"D{row}", note or "", F_GRAY, border=True)
        P[key] = row          # 回填真实行号——全模型其他表都靠 paddr() 定位
        row += 1

    # 缺关键输入时给出明确提示，而不是让下游公式悄悄空掉
    missing = [label for key, label, value, *_ in rows
               if key in ("shares", "price") and value in (None, 0)]
    if missing:
        put(ws, f"B{row}", f"⚠ 未取到 {'、'.join(missing)}，每股价值与上/下行空间算不出来，"
                           "请手工填入 C 列对应格。", F_WARN)
        row += 1

    # 两个公式行：股权成本与 WACC —— 单一来源，其他表引用它们
    fin_row = row + 1
    put(ws, f"B{fin_row}", "股权成本 Ke", F_BOLD, fill=FILL_BLOCK)
    formula(ws, f"C{fin_row}", f"={paddr('rf')}+{paddr('beta')}*{paddr('erp')}",
            F_LINK, PCT_FMT, border=True)
    put(ws, f"D{fin_row}", "公式：rf + β × ERP", F_GRAY, border=True)

    wacc_row = fin_row + 1
    put(ws, f"B{wacc_row}", "WACC", F_BOLD, fill=FILL_BLOCK)
    formula(ws, f"C{wacc_row}",
            f"={paddr('e_ratio')}*C{fin_row}"
            f"+(1-{paddr('e_ratio')})*{paddr('kd')}*(1-{paddr('tax')})",
            F_BOLD, PCT_FMT, FILL_OK, border=True)
    put(ws, f"D{wacc_row}", "公式：E/V×Ke + (1−E/V)×Kd×(1−税率)", F_GRAY, border=True)

    # 把 WACC 的实际单元格记进 P，供其他表引用
    P["ke"] = fin_row
    P["wacc"] = wacc_row
    put(ws, f"B{wacc_row + 2}",
        "改这里 → DCF 测算、敏感性矩阵、三法融合会整链重算。"
        "「说明」表的结论文字是导出时的快照，改完假设请重新导出。", F_GRAY)


# ---------------------------------------------------------------- 2 DCF测算


def _sheet_dcf(wb, result, dcf):
    ws = _sheet(wb, "DCF测算", {"B": 30, "C": 16}
                | {get_column_letter(3 + i): 15 for i in range(10)})
    title(ws, "B2", "DCF 测算（FCFF 口径，全表公式联动）")
    put(ws, "B3", "本表所有数字都是公式，引用「参数假设」表。改假设即可联动。", F_GRAY)

    rows_data = dcf.get("rows") or []
    n = len(rows_data)
    if not n:
        put(ws, "B5", "（未生成 DCF：缺少历史收入数据）", F_WARN)
        return

    FIRST = 3                      # C 列起是逐年数据
    years = [f"第 {i + 1} 年" for i in range(n)]

    row = 5
    header = ["项目"] + years
    header_row(ws, row, header, start_col=2)
    row += 1

    def cell(i):
        return f"{get_column_letter(FIRST + i)}{row}"

    def cell_at(r, i):
        return f"{get_column_letter(FIRST + i)}{r}"

    # 收入增速：从首年线性衰减到永续 g
    g_row = row
    put(ws, f"B{g_row}", "收入增速", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i),
                f"={paddr('growth_y1')}+({paddr('g')}-{paddr('growth_y1')})"
                f"*{i}/({paddr('years')}-1)",
                F_LINK, PCT_FMT, border=True)
    row += 1

    rev_row = row
    put(ws, f"B{rev_row}", "营业收入", F_LINK, border=True)
    for i in range(n):
        prev = paddr("base_rev") if i == 0 else cell_at(rev_row, i - 1)
        formula(ws, cell(i), f"={prev}*(1+{cell_at(g_row, i)})",
                F_LINK, NUM_FMT, border=True)
    row += 1

    ebit_row = row
    put(ws, f"B{ebit_row}", "EBIT", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('ebit_margin')}",
                F_LINK, NUM_FMT, border=True)
    row += 1

    tax_row = row
    put(ws, f"B{tax_row}", "减：现金所得税", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(ebit_row, i)}*{paddr('tax')}",
                F_LINK, NUM_FMT, border=True)
    row += 1

    nopat_row = row
    put(ws, f"B{nopat_row}", "NOPAT", F_BOLD, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(ebit_row, i)}-{cell_at(tax_row, i)}",
                F_BOLD, NUM_FMT, border=True)
    row += 1

    da_row = row
    put(ws, f"B{da_row}", "加：折旧摊销", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('da_pct')}",
                F_LINK, NUM_FMT, border=True)
    row += 1

    capex_row = row
    put(ws, f"B{capex_row}", "减：资本开支", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('capex_pct')}",
                F_LINK, NUM_FMT, border=True)
    row += 1

    nwc_row = row
    put(ws, f"B{nwc_row}", "减：营运资本增加", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('nwc_pct')}",
                F_LINK, NUM_FMT, border=True)
    row += 1

    fcff_row = row
    put(ws, f"B{fcff_row}", "自由现金流 FCFF", F_BOLD, border=True)
    for i in range(n):
        formula(ws, cell(i),
                f"={cell_at(nopat_row, i)}+{cell_at(da_row, i)}"
                f"-{cell_at(capex_row, i)}-{cell_at(nwc_row, i)}",
                F_BOLD, NUM_FMT, border=True)
    row += 1

    df_row = row
    put(ws, f"B{df_row}", "折现系数（期中折现）", F_RATIO, border=True)
    for i in range(n):
        formula(ws, cell(i), f"=1/(1+{paddr('wacc')})^({i}+0.5)",
                F_RATIO, MULT_FMT, border=True)
    row += 1

    pv_row = row
    put(ws, f"B{pv_row}", "现金流现值", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(fcff_row, i)}*{cell_at(df_row, i)}",
                F_LINK, NUM_FMT, border=True)
    row += 2

    # ---- 汇总区（全部公式）----
    first_c, last_c = get_column_letter(FIRST), get_column_letter(FIRST + n - 1)
    summary_start = row
    items = [
        ("详细预测期现值合计", f"=SUM({first_c}{pv_row}:{last_c}{pv_row})", F_LBL, NUM_FMT),
        ("终值 · Gordon 永续法",
         f"={last_c}{fcff_row}*(1+{paddr('g')})/({paddr('wacc')}-{paddr('g')})", F_LBL, NUM_FMT),
        ("终值 · 退出倍数法",
         f"=({last_c}{ebit_row}+{last_c}{da_row})*{paddr('exit_multiple')}", F_LBL, NUM_FMT),
        ("终值取中点", None, F_BOLD, NUM_FMT),
        ("终值现值", None, F_LBL, NUM_FMT),
        ("企业价值 EV", None, F_BOLD, NUM_FMT),
        ("加：货币资金", f"={paddr('cash')}", F_LBL, NUM_FMT),
        ("减：有息负债", f"={paddr('debt')}", F_LBL, NUM_FMT),
        ("减：少数股东权益", f"={paddr('minority')}", F_LBL, NUM_FMT),
        ("减：优先股", f"={paddr('preferred')}", F_LBL, NUM_FMT),
        ("股权价值", None, F_BOLD, NUM_FMT),
        ("股本（股）", f"={paddr('shares')}", F_LBL, NUM_FMT),
        ("每股价值", None, F_BOLD, NUM_FMT),
        ("当前股价", f"={paddr('price')}", F_LBL, NUM_FMT),
        ("上行 / 下行空间", None, F_BOLD, PCT_FMT),
        ("终值占企业价值比例", None, F_RATIO, PCT_FMT),
    ]
    # 先把 items 里自带 expr 的行直接写掉（标签 + 公式），下面再用 w() 覆盖
    # 那几项要引用前文行号的公式。
    # 早先这里只写了 B 列标签，items 里的 expr 被整批丢弃 —— Gordon 终值、
    # 退出倍数终值、加货币资金等都成了空格，下游 AVERAGE(C19:C20) 取两个空格
    # 直接 #DIV/0!，把整条「终值现值 → 企业价值 → 每股价值」链带崩。
    for idx, (label, expr, font, fmt) in enumerate(items):
        put(ws, f"B{summary_start + idx}", label, font, border=True)
        if expr:
            formula(ws, f"C{summary_start + idx}", expr, font, fmt, border=True)

    # 逐个写公式（保持可读，不循环套循环）
    rowmap = {label: summary_start + i for i, (label, _, _, _) in enumerate(items)}
    fmtmap = {label: fmt for label, _, _, fmt in items}
    fontmap = {label: font for label, _, font, _ in items}

    def w(label, expr, font=None):
        formula(ws, f"C{rowmap[label]}", expr, font or fontmap[label], fmtmap[label], border=True)

    gordon_r = rowmap["终值 · Gordon 永续法"]
    exit_r = rowmap["终值 · 退出倍数法"]
    tv_r = rowmap["终值取中点"]
    pvtv_r = rowmap["终值现值"]
    ev_r = rowmap["企业价值 EV"]
    eq_r = rowmap["股权价值"]
    per_r = rowmap["每股价值"]

    w("终值取中点", f"=AVERAGE(C{gordon_r}:C{exit_r})")
    w("终值现值", f"=C{tv_r}/(1+{paddr('wacc')})^{paddr('years')}")
    w("企业价值 EV", f"=C{rowmap['详细预测期现值合计']}+C{pvtv_r}")
    w("股权价值", f"=C{ev_r}+C{rowmap['加：货币资金']}-C{rowmap['减：有息负债']}"
                   f"-C{rowmap['减：少数股东权益']}-C{rowmap['减：优先股']}")
    w("每股价值", f"=IFERROR(C{eq_r}/C{rowmap['股本（股）']},\"\")")
    w("上行 / 下行空间", f"=IFERROR(C{per_r}/C{rowmap['当前股价']}-1,\"\")")
    w("终值占企业价值比例", f"=IFERROR(C{pvtv_r}/C{ev_r},\"\")")

    # 记下每股价值地址，供三法融合引用
    P["_dcf_per_share"] = f"'DCF测算'!$C${per_r}"

    put(ws, f"B{rowmap['终值占企业价值比例'] + 2}",
        "提示：终值占比超过 85% 说明这个模型实质上是在押倍数扩张；"
        "Gordon 与退出倍数偏离超过 30% 时应回头核对折现率假设。", F_GRAY)


# ---------------------------------------------------------------- 3 相对估值


def _sheet_relative(wb, result, rel):
    ws = _sheet(wb, "相对估值", {"B": 22, "C": 14, "D": 14, "E": 14, "F": 16, "G": 20, "H": 22})
    title(ws, "B2", "相对估值（可比公司法，公式联动）")
    put(ws, "B3", "各选用倍数取同业中位数，再按目标与同业的差异做调整。倍数列是蓝字手输。", F_GRAY)

    # 可比公司明细：优先取相对估值块自己带出来的（引擎的输出），
    # 其次兼容 meta.peers_detail（早期版本的字段名，已不再生产）。
    peers = ((result.get("relative") or {}).get("peers_detail")
             or (result.get("meta") or {}).get("peers_detail") or [])
    if not peers:
        put(ws, "B5", "（本次未提供可比公司，相对估值未启用）", F_WARN)
        put(ws, "B6", "如需启用：在界面里用 AI 推荐可比公司，或直接编辑本表补上。", F_GRAY)
        P["_rel_per_share"] = None
        return

    first = 6
    header_row(ws, first, ["简称", "代码", "PE", "PB", "PS", "EV/EBITDA", "收入增速", "EBITDA利润率"])
    r = first + 1
    row_start = r
    for p in peers:
        put(ws, f"B{r}", p.get("name", ""), F_LBL, border=True)
        put(ws, f"C{r}", p.get("ticker", ""), F_LBL, border=True)
        for i, k in enumerate(["pe", "pb", "ps", "ev_ebitda"]):
            put(ws, f"{get_column_letter(4 + i)}{r}", p.get(k), F_INPUT, MULT_FMT, border=True)
        put(ws, f"H{r}", p.get("revenue_growth"), F_INPUT, PCT_FMT, border=True)
        put(ws, f"I{r}", p.get("ebitda_margin"), F_INPUT, PCT_FMT, border=True)
        r += 1
    row_end = r - 1

    # 中位数行（公式）
    med_row = r
    put(ws, f"B{med_row}", "同业中位数", F_BOLD, fill=FILL_BLOCK)
    for col in "DEFG":
        formula(ws, f"{col}{med_row}", f"=IFERROR(MEDIAN({col}{row_start}:{col}{row_end}),\"\")",
                F_LINK, MULT_FMT, fill=FILL_BLOCK, border=True)
    r += 2

    # 标的指标（手输）
    base = result.get("relative", {}).get("results") or []
    metric_map = {x["multiple"]: x for x in base}
    r += 1
    put(ws, f"B{r}", "标的指标", F_BOLD, fill=FILL_BLOCK); r += 1
    metric_cells = {}
    for key, label in [("pe", "基准年净利润"), ("pb", "基准年净资产"),
                       ("ps", "基准年营业收入"), ("ev_ebitda", "基准年 EBITDA")]:
        info = metric_map.get(key)
        val = info.get("metric_value") if info else None
        put(ws, f"B{r}", label, F_LBL, border=True)
        put(ws, f"C{r}", val, F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
        metric_cells[key] = f"$C${r}"
        r += 1

    net_debt_row = r
    put(ws, f"B{r}", "净负债", F_LBL, border=True)
    formula(ws, f"C{r}", f"={paddr('debt')}-{paddr('cash')}", F_LINK, NUM_FMT, border=True)
    r += 2

    # 隐含股权价值（公式）
    put(ws, f"B{r}", "隐含股权价值", F_BOLD, fill=FILL_BLOCK); r += 1
    implied_rows = {}
    for key, label, ev_based in [
        ("pe", "PE 法", False), ("pb", "PB 法", False),
        ("ps", "PS 法", False), ("ev_ebitda", "EV/EBITDA 法", True),
    ]:
        if key not in metric_cells:
            continue
        col = get_column_letter(4 + ["pe", "pb", "ps", "ev_ebitda"].index(key))
        put(ws, f"B{r}", label, F_LBL, border=True)
        if ev_based:
            formula(ws, f"C{r}",
                    f"=IFERROR({col}{med_row}*{metric_cells[key]}-$C${net_debt_row},\"\")",
                    F_LINK, NUM_FMT, border=True)
        else:
            formula(ws, f"C{r}", f"=IFERROR({col}{med_row}*{metric_cells[key]},\"\")",
                    F_LINK, NUM_FMT, border=True)
        implied_rows[key] = r
        r += 1

    concl_row = r
    put(ws, f"B{concl_row}", "各法隐含股权价值（中位）", F_BOLD, border=True)
    if implied_rows:
        refs = ",".join(f"C{x}" for x in implied_rows.values())
        formula(ws, f"C{concl_row}", f"=MEDIAN({refs})", F_BOLD, NUM_FMT, FILL_OK, border=True)
    r += 1
    put(ws, f"B{r}", "隐含每股价值", F_BOLD, border=True)
    formula(ws, f"C{r}", f"=IFERROR(C{concl_row}/{paddr('shares')},\"\")",
            F_BOLD, NUM_FMT, border=True)
    P["_rel_per_share"] = f"'相对估值'!$C${r}"
    r += 2

    put(ws, f"B{r}", "口径说明", F_BOLD); r += 1
    for text in [
        "· 同业中位数而非均值：中位数对极端值更稳健。",
        "· EV 类倍数算出企业价值后要扣减净负债，才是股权价值。",
        "· 目标与同业在增速/利润率/杠杆上差异明显时，应调整倍数并说明理由。",
    ]:
        put(ws, f"B{r}", text, F_GRAY)
        ws.merge_cells(f"B{r}:H{r}")
        r += 1


# ---------------------------------------------------------------- 4 分部估值


def _sheet_sotp(wb, sotp):
    ws = _sheet(wb, "分部估值", {"B": 26, "C": 14, "D": 18, "E": 14, "F": 20})
    title(ws, "B2", "分部估值（SOTP，公式联动）")
    put(ws, "B3", "各分部按纯业务可比公司的中位倍数估值，加总后扣减总部费用与净负债。", F_GRAY)

    segs = list(sotp.get("rows") or [])
    # 免费数据源拿不到分部拆分，没有数据时也出这张表：给几行蓝字可填行，
    # 填上「指标值 × 可比倍数」就自动算出分部每股价值并联动到三法融合。
    if not segs:
        put(ws, "B4", "⚠ 本次未取到分部财务数据（免费源不提供分部拆分）。"
                      "请在下面蓝字格手工填入各分部的指标值与可比倍数，表内会自动算出结果。",
            F_WARN)
        ws.merge_cells("B4:F4")
        ws.row_dimensions[4].height = 28
        segs = [{"name": "", "metric": "ebitda", "value": None, "multiple": None}
                for _ in range(3)]

    row = 6 if not sotp.get("rows") else 5
    header_row(ws, row, ["分部", "指标口径", "指标值", "采用倍数", "分部企业价值"])
    row += 1
    first_data = row
    for s in segs:
        put(ws, f"B{row}", s.get("name") or "", F_INPUT, border=True)
        put(ws, f"C{row}", (s.get("metric") or "ebitda").upper(), F_LBL, border=True)
        put(ws, f"D{row}", s.get("value"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
        put(ws, f"E{row}", s.get("multiple"), F_INPUT, MULT_FMT, FILL_YELLOW, border=True)
        formula(ws, f"F{row}", f"=IFERROR(D{row}*E{row},0)", F_LINK, NUM_FMT, border=True)
        row += 1
    last_data = row - 1

    row += 1
    total_row = row
    put(ws, f"B{row}", "分部企业价值合计", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=SUM(F{first_data}:F{last_data})", F_BOLD, NUM_FMT, border=True)
    row += 1

    cost_row = row
    put(ws, f"B{row}", "减：总部费用（资本化）", F_LBL, border=True)
    put(ws, f"C{row}", sotp.get("corporate_cost"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
    row += 1

    nd_row = row
    put(ws, f"B{row}", "减：净负债", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('debt')}-{paddr('cash')}", F_LINK, NUM_FMT, border=True)
    row += 1

    eq_row = row
    put(ws, f"B{row}", "股权价值", F_BOLD, border=True)
    # 分部数据为空时合计为 0，此时整块留空——否则会算出「0 − 净负债」这种
    # 看起来像结论、实际是垃圾的数，再被三法融合当成一个方法算进去。
    formula(ws, f"C{row}",
            f"=IF(C{total_row}=0,\"\",C{total_row}-C{cost_row}-C{nd_row})",
            F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1

    put(ws, f"B{row}", "每股价值", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IFERROR(C{eq_row}/{paddr('shares')},\"\")", F_BOLD, NUM_FMT, border=True)
    P["_sotp_per_share"] = f"'分部估值'!$C${row}"


# ---------------------------------------------------------------- 5 三法融合


def _sheet_blend(wb, result, blended, scen):
    ws = _sheet(wb, "三法融合", {"B": 24, "C": 18, "D": 12, "E": 20, "F": 26})
    title(ws, "B2", "三法融合（权重可改，公式联动）")
    put(ws, "B3", "权重是蓝字黄底，改它会改融合结果；各方法的每股价值从对应工作表引用，不手输。", F_GRAY)

    row = 5
    header_row(ws, row, ["方法", "每股价值", "权重", "股权价值", "来源"])
    row += 1

    refs = [
        ("dcf", "DCF 收益法", P.get("_dcf_per_share"), "DCF测算"),
        ("relative", "相对估值（市场法）", P.get("_rel_per_share"), "相对估值"),
        ("sotp", "分部估值（SOTP）", P.get("_sotp_per_share"), "分部估值"),
    ]
    # 权重直接用引擎实际采用的那组（blended.components），不再在前端另设默认值——
    # 否则表里写着的权重和融合结果对不上，使用者改了假设也看不出为什么。
    engine_w = {c.get("key"): (c.get("weight") or 0.0)
                for c in (blended.get("components") or [])}

    first_row = row
    used = []
    for key, label, ref, sheet in refs:
        if not ref:
            continue
        put(ws, f"B{row}", label, F_LBL, border=True)
        # N() 兜底：上游是空字符串时（例如尚无分部数据）取 0，
        # 否则文本参与 SUMPRODUCT 的乘法会让整格 #VALUE!。
        formula(ws, f"C{row}", f"=N({ref})", F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", round(engine_w.get(key, 0.0), 4), F_INPUT, PCT1_FMT,
            FILL_YELLOW, border=True)
        formula(ws, f"E{row}", f"=C{row}*{paddr('shares')}", F_LINK, NUM_FMT, border=True)
        put(ws, f"F{row}", f"引用「{sheet}」表", F_GRAY, border=True)
        used.append(row)
        row += 1
    last_row = row - 1

    if not used:
        put(ws, f"B{row}", "（三种方法都没有得出有效结果，无法融合）", F_WARN)
        return

    row += 1
    put(ws, f"B{row}", "权重合计（应为 100%）", F_RATIO, border=True)
    formula(ws, f"C{row}", f"=SUM(D{first_row}:D{last_row})", F_RATIO, PCT1_FMT, border=True)
    row += 1
    zero = [label for key, label, ref, _ in refs if ref and not engine_w.get(key)]
    if zero:
        put(ws, f"B{row}", f"注：{'、'.join(zero)} 的权重为 0，本次未计入融合"
                           "（多半是该方法的输入还不完整，比如分部数据没填）。"
                           "把数据补齐后，请手工把这一行权重调起来。", F_GRAY)
        ws.merge_cells(f"B{row}:F{row}")
        ws.row_dimensions[row].height = 26
        row += 1
    put(ws, f"B{row}", "融合每股价值", F_BOLD, border=True)
    formula(ws, f"C{row}",
            f"=IFERROR(SUMPRODUCT(C{first_row}:C{last_row},D{first_row}:D{last_row})"
            f"/SUM(D{first_row}:D{last_row}),\"\")",
            F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1
    put(ws, f"B{row}", "当前股价", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('price')}", F_LINK, NUM_FMT, border=True)
    price_row = row
    row += 1
    put(ws, f"B{row}", "上行 / 下行空间", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IFERROR(C{row - 2}/C{price_row}-1,\"\")", F_BOLD, PCT_FMT, border=True)
    row += 2

    # 三情景（静态说明，因为情景是不同假设下的重算）
    if scen.get("bull"):
        put(ws, f"B{row}", "三情景对照（不同假设下的重算结果）", F_BOLD, fill=FILL_BLOCK)
        row += 1
        header_row(ws, row, ["情景", "每股价值", "首年增速", "EBIT 利润率", "WACC"])
        row += 1
        for key in ("bull", "base", "bear"):
            s = scen.get(key) or {}
            put(ws, f"B{row}", s.get("label", key), F_LBL, border=True)
            put(ws, f"C{row}", s.get("per_share"), F_LINK, NUM_FMT, border=True)
            put(ws, f"D{row}", s.get("growth_y1"), F_LINK, PCT_FMT, border=True)
            put(ws, f"E{row}", s.get("ebit_margin"), F_LINK, PCT_FMT, border=True)
            put(ws, f"F{row}", s.get("wacc"), F_LINK, PCT_FMT, border=True)
            row += 1
        put(ws, f"B{row + 1}",
            "注：情景是在不同假设下的重算结果，改本表权重不会改变它们。", F_GRAY)


# ---------------------------------------------------------------- 6 敏感性


def _sheet_sensitivity(wb, result, sens):
    ws = _sheet(wb, "敏感性分析", {"B": 10, "C": 10}
                | {get_column_letter(4 + i): 16 for i in range(6)})
    title(ws, "B2", "敏感性分析：每股价值 = f(WACC, 永续增长率)")
    if not sens.get("grid"):
        put(ws, "B4", "（未生成敏感性矩阵）", F_WARN)
        return

    wacc_axis = sens.get("wacc_axis") or []
    g_axis = sens.get("growth_axis") or []
    n = len(g_axis)
    nw = len(wacc_axis)
    if not (wacc_axis and g_axis):
        return

    put(ws, "B3", "行 = WACC，列 = 永续增长率。每格引用下方辅助重算区，不是模拟运算表。", F_GRAY)

    # 矩阵头：列是 g（手输，黄底）
    row = 5
    header_row(ws, row, ["WACC \\ g"] + [""] * n, start_col=2)
    for j, g in enumerate(g_axis):
        put(ws, f"{get_column_letter(4 + j)}{row}", g, F_KEY, PCT_FMT, FILL_YELLOW, CENTER, border=True)
    row += 1
    first_grid_row = row

    # 辅助区紧跟在矩阵 + 说明之后。位置在写矩阵公式**之前**就定得出来，
    # 这样矩阵格可以直接引用辅助格——早先这里是 IFERROR(_dcf_per_share_at(...))，
    # 而 Excel 里根本没有这个函数，整张矩阵 525 格全是 #NAME?。
    BLOCK = 7                     # 每个格子占 7 行（6 行重算 + 1 行间隔）
    SHARE_ROW_OFFSET = 5          # 块内第 6 行是「每股价值」
    helper_title_row = first_grid_row + nw + 2
    helper_top = helper_title_row + 1

    def helper_ref(i: int, j: int) -> str:
        return f"$C${helper_top + (i * n + j) * BLOCK + SHARE_ROW_OFFSET}"

    base_w = sens.get("base_wacc")
    base_g = sens.get("base_growth")
    base_i = base_j = None
    for i, w in enumerate(wacc_axis):
        put(ws, f"B{row}", w, F_KEY, PCT_FMT, FILL_YELLOW, None, border=True)
        if base_w is not None and abs(w - base_w) < 1e-12:
            base_i = i
        for j in range(n):
            col = get_column_letter(4 + j)
            if base_g is not None and abs(g_axis[j] - base_g) < 1e-12:
                base_j = j
            formula(ws, f"{col}{row}", f"=IFERROR({helper_ref(i, j)},\"\")",
                    F_LINK, NUM_FMT, border=True)
        row += 1
    last_grid_row = row - 1

    # 基准格描金框
    if base_i is not None and base_j is not None:
        cell = ws.cell(row=first_grid_row + base_i, column=4 + base_j)
        cell.border = Border(left=GOLD, right=GOLD, top=GOLD, bottom=GOLD)

    row += 1
    put(ws, f"B{row}", "金色框是基准情景；数值越陡说明估值越依赖这两个假设。", F_GRAY)
    row += 2

    # ---- 辅助重算区（不隐藏：隐藏列会被 Excel 的 SpecialCells 跳过，排错时看不见）----
    put(ws, f"B{row}", "辅助重算区（每格独立重算 DCF；矩阵引用的是这里的「每股价值」格）", F_GRAY)
    for i in range(nw):
        for j in range(n):
            _sensitivity_helper(ws, helper_top + (i * n + j) * BLOCK,
                               wacc_axis[i], g_axis[j], result)


def _sensitivity_helper(ws, top, wacc, g, result):
    """为敏感性格子写一小块重算：收入路径 → FCFF → 现值 → 终值 → 每股。"""
    dcf = result.get("dcf") or {}
    rows_data = dcf.get("rows") or []
    n = len(rows_data) or 5
    FIRST = 3

    ws.cell(row=top, column=2, value=f"WACC={wacc:.4%}  g={g:.4%}").font = F_GRAY
    ws.cell(row=top, column=3, value=wacc).font = F_GRAY
    ws.cell(row=top, column=4, value=g).font = F_GRAY

    g_row = top + 1
    rev_row = top + 2
    fcff_row = top + 3
    pv_row = top + 4

    for i in range(n):
        col = get_column_letter(FIRST + i)
        # 增速路径：首年增速线性衰减到永续 g。g 固定在块首 $D${top}，
        # 早先这里写的是 {col}{top}（随列变化）——第 0 列取到的是 WACC、
        # 第 1 列取到 g、再往后取到空格，整条路径都是错的，敏感性矩阵
        # 中心格因此比基准 DCF 低了 5%。
        ws[f"{col}{g_row}"] = (
            f"={paddr('growth_y1')}+($D${top}-{paddr('growth_y1')})*{i}/({paddr('years')}-1)")
        prev = paddr("base_rev") if i == 0 else f"{get_column_letter(FIRST + i - 1)}{rev_row}"
        ws[f"{col}{rev_row}"] = f"={prev}*(1+{col}{g_row})"
        ws[f"{col}{fcff_row}"] = (
            f"={col}{rev_row}*{paddr('ebit_margin')}*(1-{paddr('tax')})"
            f"+{col}{rev_row}*{paddr('da_pct')}"
            f"-{col}{rev_row}*{paddr('capex_pct')}"
            f"-{col}{rev_row}*{paddr('nwc_pct')}")
        ws[f"{col}{pv_row}"] = (
            f"={col}{fcff_row}/(1+$C${top})^({i}+0.5)")

    last_fcff = f"{get_column_letter(FIRST + n - 1)}{fcff_row}"
    last_rev = f"{get_column_letter(FIRST + n - 1)}{rev_row}"
    pv_sum = f"SUM({get_column_letter(FIRST)}{pv_row}:{get_column_letter(FIRST + n - 1)}{pv_row})"
    tv = (f"({last_fcff}*(1+$D${top})/($C${top}-$D${top})"
          f"+({last_rev}*{paddr('ebit_margin')}+{last_rev}*{paddr('da_pct')})"
          f"*{paddr('exit_multiple')})/2")
    pv_tv = f"({tv})/(1+$C${top})^{paddr('years')}"

    # 用 IFERROR 包住：shares 缺失会除零、WACC≤g 时终值公式也会除零，
    # 这些格子必须是空串而不是错误值，否则 Excel 一重算就满屏 #DIV/0!。
    ws.cell(row=top + 5, column=3,
            value=f"=IFERROR(({pv_sum}+{pv_tv}+{paddr('cash')}-{paddr('debt')}"
                  f"-{paddr('minority')}-{paddr('preferred')})/{paddr('shares')},\"\")").font = F_GRAY
    # 返回「每股价值」所在行：_sheet_sensitivity 靠它提前算出矩阵格的引用地址
    return top + 5


# ---------------------------------------------------------------- 7 来源


def _sheet_sources(wb, result):
    ws = _sheet(wb, "数据来源", {"B": 40, "C": 14, "D": 14, "E": 18})
    title(ws, "B2", "数据来源与口径")
    row = 4
    header_row(ws, row, ["来源", "用途", "取数日", "性质"])
    row += 1
    for s in result.get("sources") or []:
        put(ws, f"B{row}", s.get("name", ""), F_LBL, border=True)
        put(ws, f"C{row}", s.get("purpose", "财务/市场数据"), F_LBL, border=True)
        put(ws, f"D{row}", s.get("as_of", ""), F_LBL, border=True)
        put(ws, f"E{row}", "官方源" if s.get("official") else "非官方源", F_LBL, border=True)
        row += 1
    if not (result.get("sources") or []):
        put(ws, f"B{row}", "（未提供来源信息，请在交付时补齐）", F_WARN)
    row += 2
    put(ws, f"B{row}", "as-of 规则：所有市场数据原则上取基准日或之前可获得的数据；"
                       "确需使用基准日之后发布的数据时，须显式标注「后见信息」并请使用者确认。", F_GRAY)
    ws.merge_cells(f"B{row}:E{row}")
    ws.row_dimensions[row].height = 32


# ---------------------------------------------------------------- 8 说明


def _sheet_summary(wb, result, company, dcf, rel, blended, scen):
    ws = _sheet(wb, "说明", {"B": 30, "C": 20, "D": 16, "E": 16, "F": 44})
    title(ws, "B2", "FinScope 估值底稿")
    put(ws, "B3", f"{company.get('name', '')}（{company.get('ticker', '')}）", F_BOLD)
    put(ws, "B4", f"估值基准期 {company.get('report_period', '—')} · "
                  f"价格日期 {company.get('price_date', '—')} · "
                  f"币种 {company.get('currency', 'CNY')}", F_GRAY)

    row = 6
    put(ws, f"B{row}", "一、结论（导出时的快照）", F_BOLD, fill=FILL_BLOCK); row += 1
    if blended.get("ok"):
        for label, value, fmt in [
            ("融合每股价值", blended.get("blended_per_share"), NUM_FMT),
            ("当前市价", blended.get("current_price"), NUM_FMT),
            ("上行 / 下行空间", blended.get("upside"), PCT_FMT),
        ]:
            put(ws, f"B{row}", label, F_BOLD if label == "融合每股价值" else F_LBL, border=True)
            put(ws, f"C{row}", value,
                F_BOLD if label == "融合每股价值" else F_LINK, fmt,
                FILL_OK if label == "融合每股价值" else None, border=True)
            row += 1
        put(ws, f"B{row}", "估值判断", F_BOLD, border=True)
        put(ws, f"C{row}", blended.get("verdict"), F_BOLD, border=True)
        row += 1
        put(ws, f"B{row}", "权重口径", F_LBL, border=True)
        put(ws, f"C{row}", blended.get("weight_source"), F_GRAY, border=True)
        row += 2
    put(ws, f"B{row}", "注：本页是导出时的快照。改「参数假设」表后，"
                       "DCF测算 / 三法融合 / 敏感性分析会联动，但本页文字不会自动更新——"
                       "重新导出即可刷新。", F_GRAY)
    ws.merge_cells(f"B{row}:F{row}")
    ws.row_dimensions[row].height = 30
    row += 2

    put(ws, f"B{row}", "二、工作表清单", F_BOLD, fill=FILL_BLOCK); row += 1
    for name, desc in [
        ("参数假设", "全模型唯一输入源。改这里的蓝字黄底，其余表整链重算"),
        ("DCF测算", "FCFF 逐年测算，全部公式引用参数假设表"),
        ("相对估值", "可比公司倍数表 + 隐含价值，倍数可手改"),
        ("分部估值", "有分部数据时才生成（本次%s）" % ("已生成" if (result.get("sotp") or {}).get("ok") else "未生成")),
        ("三法融合", "各方法每股价值加权（权重可改）"),
        ("敏感性分析", "WACC × 永续增长率矩阵，每格独立公式重算"),
        ("数据来源", "每个数字的出处与取数日期"),
    ]:
        put(ws, f"B{row}", name, F_LBL, border=True)
        put(ws, f"C{row}", desc, F_GRAY, border=True)
        ws.merge_cells(f"C{row}:F{row}")
        row += 1
    row += 1

    if scen.get("bull"):
        put(ws, f"B{row}", "三、三情景", F_BOLD, fill=FILL_BLOCK); row += 1
        header_row(ws, row, ["情景", "每股价值", "首年增速", "EBIT 利润率", "WACC"])
        row += 1
        for key in ("bull", "base", "bear"):
            s = scen.get(key) or {}
            put(ws, f"B{row}", s.get("label", key), F_LBL, border=True)
            put(ws, f"C{row}", s.get("per_share"), F_LINK, NUM_FMT, border=True)
            put(ws, f"D{row}", s.get("growth_y1"), F_LINK, PCT_FMT, border=True)
            put(ws, f"E{row}", s.get("ebit_margin"), F_LINK, PCT_FMT, border=True)
            put(ws, f"F{row}", s.get("wacc"), F_LINK, PCT_FMT, border=True)
            row += 1
        row += 1

    warnings = result.get("warnings") or []
    if warnings:
        put(ws, f"B{row}", "四、模型提示（交付前请逐条回应）", F_BOLD, fill=FILL_WARN); row += 1
        for w in warnings[:12]:
            put(ws, f"B{row}", "⚠ " + str(w)[:200], F_WARN)
            ws.merge_cells(f"B{row}:F{row}")
            ws.row_dimensions[row].height = 26
            row += 1
        row += 1

    put(ws, f"B{row}", "五、口径与免责", F_BOLD, fill=FILL_BLOCK); row += 1
    for text in [
        "· 金额单位为报表原始货币的「元」，勿与「万元」「亿元」混用。",
        "· 蓝字为手输/假设，蓝字黄底为关键驱动；黑字为公式链接，改动上游会自动联动。",
        "· 本底稿由模型按既定假设计算，仅供研究与教学用途，不构成投资建议。",
    ]:
        put(ws, f"B{row}", text, F_GRAY)
        ws.merge_cells(f"B{row}:F{row}")
        row += 1
