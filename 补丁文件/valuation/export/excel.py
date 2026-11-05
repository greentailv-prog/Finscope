"""Excel 估值底稿（公式联动）。

工作表：
  说明 / 参数假设 / DCF测算 / 相对估值 / 分部估值 / 三法融合 /
  敏感性-WACC×g / 敏感性-增速×利润率 / 假设台账 / 数据来源 / 行业门槛与规则

样式沿用 dcf-valuation-model / comps-valuation-model：
  蓝字=手输/假设，蓝字黄底=关键驱动，黑字=公式，红字=⚠，灰字=备注。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Times New Roman"
NUM_FMT = '_ * #,##0.00_ ;_ * (#,##0.00);_ * "-"??_ ;_ @_ '
PCT_FMT = "0.00%"
PCT1_FMT = "0.0%"
MULT_FMT = "0.00"
INT_FMT = "0"

F_TITLE = Font(name=FONT, size=14, bold=True, color="FF0B2545")
F_BOLD = Font(name=FONT, size=10, bold=True)
F_LBL = Font(name=FONT, size=10)
F_INPUT = Font(name=FONT, size=10, color="FF0000FF")
F_KEY = Font(name=FONT, size=10, color="FF0000FF", bold=True)
F_LINK = Font(name=FONT, size=10, color="FF000000")
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
GOLD = Side(style="medium", color="FFFFC000")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
WRAP = Alignment(vertical="top", wrap_text=True)

PARAM_SHEET = "参数假设"
P: dict[str, int] = {}


def _sheet(wb, name, widths=None, first=False):
    ws = wb.create_sheet(name) if not first else wb.active
    if first:
        ws.title = name
    ws.sheet_view.showGridLines = False
    for col, width in (widths or {}).items():
        ws.column_dimensions[col].width = width
    return ws


def put(ws, coord, value, font=None, fmt=None, fill=None, align=None, border=False):
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


def paddr(key: str) -> str:
    return f"'{PARAM_SHEET}'!$C${P[key]}"


def _source_line(result: dict) -> str:
    srcs = result.get("sources") or []
    if not srcs:
        return "数据来源：未提供"
    names = "；".join(f"{s.get('name')}（{s.get('as_of')}）" for s in srcs[:4])
    return f"数据来源：{names}"


def render(result: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    P.clear()

    company = result.get("company") or {}
    dcf = result.get("dcf") or {}
    comps = result.get("comps") or result.get("relative") or {}
    sotp = result.get("sotp") or {}
    ddm = result.get("ddm") or {}
    blended = result.get("blended") or {}
    scen = result.get("scenarios") or {}
    sens = result.get("sensitivity") or {}

    _sheet_assumptions(wb, result, dcf, first=True)
    _sheet_dcf(wb, result, dcf)
    _sheet_comps(wb, result, comps)
    _sheet_sotp(wb, result, sotp)
    _sheet_ddm(wb, result, ddm)
    _sheet_blend(wb, result, blended, scen)
    _sheet_sensitivity(wb, result, sens)
    _sheet_ledger(wb, result)
    _sheet_sources(wb, result)
    _sheet_rules(wb, result)
    _sheet_summary(wb, result, company, dcf, comps, sotp, ddm, blended, scen)

    # 7.9：每张表第一行写数据来源和生成时间。
    # artifact_tool 版写 A2；openpyxl 兼容版标题在 B2，A1 空着，直接写 A1。
    source = _source_line(result)
    stamp = f"{source} | 生成时间：{datetime.now():%Y-%m-%d %H:%M}"
    for ws in wb.worksheets:
        if ws["A1"].value in (None, ""):
            cell = ws["A1"]
            cell.value = stamp
            cell.font = F_GRAY
            cell.alignment = Alignment(vertical="center")

    wb.move_sheet("说明", offset=-len(wb.sheetnames) + 1)
    wb.save(out_path)
    return out_path


# ---------------------------------------------------------------- 参数假设


def _sheet_assumptions(wb, result, dcf, first=False):
    ws = _sheet(wb, PARAM_SHEET, {"B": 30, "C": 16, "D": 52}, first=first)
    title(ws, "B2", "参数假设 —— 全模型唯一输入源")
    put(ws, "B3", "蓝字为手输/规则生成的假设，蓝字黄底为关键驱动。改这里，DCF 与融合表会联动。", F_GRAY)

    wb_ = dcf.get("wacc_block") or {}
    mkt = result.get("market_data") or {}
    rows = [
        ("years", "预测期年数", dcf.get("forecast_years"), INT_FMT, F_KEY, "3–10 年"),
        ("growth_y1", "首年收入增速", dcf.get("revenue_growth_y1"), PCT_FMT, F_KEY, "由历史 CAGR/用户输入/规则合成"),
        ("ebit_margin", "EBIT 利润率", dcf.get("ebit_margin"), PCT_FMT, F_KEY, "近三年中位数或用户指定"),
        ("da_pct", "折旧摊销 / 收入", dcf.get("da_pct"), PCT_FMT, F_INPUT, "近三年中位数或规则估算"),
        ("capex_pct", "资本开支 / 收入", dcf.get("capex_pct"), PCT_FMT, F_INPUT, "近三年中位数或规则估算"),
        ("nwc_pct", "营运资本增加 / 收入", dcf.get("nwc_pct"), PCT_FMT, F_INPUT, "近三年中位数或规则估算"),
        ("g", "永续增长率 g", dcf.get("terminal_growth"), PCT_FMT, F_KEY, f"上限 {dcf.get('terminal_growth_cap') or 0:.1%}"),
        (None, None, None, None, None, None),
        ("rf", "无风险利率 rf", wb_.get("risk_free"), PCT_FMT, F_KEY, wb_.get("risk_free_source") or ""),
        ("erp", "股权风险溢价 ERP", wb_.get("erp"), PCT_FMT, F_KEY, wb_.get("erp_source") or ""),
        ("beta", "Beta", wb_.get("beta"), MULT_FMT, F_KEY, wb_.get("beta_source") or ""),
        ("size_premium", "规模溢价", wb_.get("size_premium"), PCT_FMT, F_INPUT, ""),
        ("kd", "税前债务成本 Kd", wb_.get("cost_of_debt"), PCT_FMT, F_INPUT, wb_.get("cost_of_debt_source") or ""),
        ("tax", "所得税率", wb_.get("tax_rate"), PCT_FMT, F_KEY, "近三年有效税率中位数，夹在 15%–30%"),
        ("d_ratio", "D/(D+E)", wb_.get("debt_ratio"), PCT1_FMT, F_KEY, wb_.get("capital_source") or ""),
        (None, None, None, None, None, None),
        ("base_rev", "基准年营业收入", dcf.get("base_revenue"), NUM_FMT, F_INPUT, "元；DCF 起算点"),
        ("cash", "货币资金", dcf.get("cash"), NUM_FMT, F_INPUT, ""),
        ("debt", "有息负债", dcf.get("debt"), NUM_FMT, F_INPUT, ""),
        ("minority", "少数股东权益", dcf.get("minority_interest"), NUM_FMT, F_INPUT, ""),
        ("preferred", "优先股", dcf.get("preferred_stock"), NUM_FMT, F_INPUT, ""),
        ("shares", "股本（股）", mkt.get("shares_outstanding"), NUM_FMT, F_INPUT, ""),
        ("price", "当前股价", mkt.get("price"), NUM_FMT, F_INPUT, ""),
        ("exit_multiple", "退出倍数 EV/EBITDA", dcf.get("exit_multiple"), MULT_FMT, F_KEY, dcf.get("exit_multiple_source") or ""),
        ("roic", "长期 ROIC", dcf.get("terminal_roic"), PCT_FMT, F_INPUT, "终值再投资率 = g / ROIC"),
    ]

    row = 5
    header_row(ws, row, ["参数", "取值", "来源 / 口径"], start_col=2)
    row += 1
    for key, label, value, fmt, font, note in rows:
        if label is None:
            row += 1
            continue
        put(ws, f"B{row}", label, font, border=True)
        put(ws, f"C{row}", value, font, fmt, FILL_YELLOW if font is F_KEY else None, border=True)
        put(ws, f"D{row}", note or "", F_GRAY, border=True)
        P[key] = row
        row += 1

    ke_row = row + 1
    put(ws, f"B{ke_row}", "股权成本 Ke", F_BOLD, fill=FILL_BLOCK, border=True)
    formula(ws, f"C{ke_row}", f"={paddr('rf')}+{paddr('beta')}*{paddr('erp')}+{paddr('size_premium')}",
            F_LINK, PCT_FMT, border=True)
    put(ws, f"D{ke_row}", "公式：rf + β×ERP + 规模溢价", F_GRAY, border=True)
    P["ke"] = ke_row

    wacc_capm_row = ke_row + 1
    put(ws, f"B{wacc_capm_row}", "WACC（CAPM 口径）", F_BOLD, fill=FILL_BLOCK, border=True)
    formula(ws, f"C{wacc_capm_row}",
            f"=(1-{paddr('d_ratio')})*C{ke_row}+{paddr('d_ratio')}*{paddr('kd')}*(1-{paddr('tax')})",
            F_LINK, PCT_FMT, border=True)
    put(ws, f"D{wacc_capm_row}", "公式：(1−D/(D+E))×Ke + D/(D+E)×Kd×(1−税率)", F_GRAY, border=True)
    P["wacc_capm"] = wacc_capm_row

    wacc_adj_row = wacc_capm_row + 1
    used_wacc = dcf.get("wacc")
    capm_wacc = dcf.get("wacc_capm") or used_wacc
    adjustment = (used_wacc - capm_wacc) if (used_wacc is not None and capm_wacc is not None) else 0.0
    put(ws, f"B{wacc_adj_row}", "WACC 市场校准", F_KEY, border=True)
    put(ws, f"C{wacc_adj_row}", adjustment, F_INPUT, PCT_FMT, FILL_YELLOW, border=True)
    put(ws, f"D{wacc_adj_row}", dcf.get("wacc_source") or "CAPM 与市场隐含折现率的校准项", F_GRAY,
        border=True)
    P["wacc_adjust"] = wacc_adj_row

    wacc_row = wacc_adj_row + 1
    put(ws, f"B{wacc_row}", "WACC（采用）", F_BOLD, fill=FILL_BLOCK, border=True)
    formula(ws, f"C{wacc_row}", f"=C{wacc_capm_row}+C{wacc_adj_row}",
            F_BOLD, PCT_FMT, FILL_OK, border=True)
    put(ws, f"D{wacc_row}", "公式：CAPM WACC + 市场校准项；DCF 表引用本行", F_GRAY, border=True)
    P["wacc"] = wacc_row

    put(ws, f"B{wacc_row + 2}",
        "提示：本表是单一真源。改蓝字黄底格后，DCF 与三法融合会联动；"
        "敏感性矩阵与情景是引擎逐格重算的静态结果，需重新导出刷新。", F_GRAY)


# ---------------------------------------------------------------- DCF


def _sheet_dcf(wb, result, dcf):
    ws = _sheet(wb, "DCF测算", {"B": 30, "C": 24}
                | {get_column_letter(3 + i): 20 for i in range(12)})
    title(ws, "B2", "DCF 测算（FCFF 口径，公式联动）")
    put(ws, "B3", "本表引用「参数假设」；期中折现，终值默认 Gordon 与退出倍数取中点。", F_GRAY)
    rows_data = dcf.get("rows") or []
    n = len(rows_data)
    if not n:
        put(ws, "B5", "（未生成 DCF）", F_WARN)
        return

    FIRST = 3
    row = 5
    header_row(ws, row, ["项目"] + [str(r.get("year") or f"Y{i + 1}") for i, r in enumerate(rows_data)],
               start_col=2)
    row += 1

    def cell(i, r=None):
        return f"{get_column_letter(FIRST + i)}{r or row}"

    def cell_at(r, i):
        return f"{get_column_letter(FIRST + i)}{r}"

    g_row = row
    put(ws, f"B{g_row}", "收入增速", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={paddr('growth_y1')}+({paddr('g')}-{paddr('growth_y1')})*{i}/({paddr('years')}-1)",
                F_LINK, PCT_FMT, border=True)
    row += 1

    rev_row = row
    put(ws, f"B{rev_row}", "营业收入", F_LINK, border=True)
    for i in range(n):
        prev = paddr("base_rev") if i == 0 else cell_at(rev_row, i - 1)
        formula(ws, cell(i), f"={prev}*(1+{cell_at(g_row, i)})", F_LINK, NUM_FMT, border=True)
    row += 1

    ebit_row = row
    put(ws, f"B{ebit_row}", "EBIT", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('ebit_margin')}", F_LINK, NUM_FMT, border=True)
    row += 1

    tax_row = row
    put(ws, f"B{tax_row}", "减：现金所得税", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(ebit_row, i)}*{paddr('tax')}", F_LINK, NUM_FMT, border=True)
    row += 1

    nopat_row = row
    put(ws, f"B{nopat_row}", "NOPAT", F_BOLD, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(ebit_row, i)}-{cell_at(tax_row, i)}", F_BOLD, NUM_FMT, border=True)
    row += 1

    da_row = row
    put(ws, f"B{da_row}", "加：折旧摊销", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('da_pct')}", F_LINK, NUM_FMT, border=True)
    row += 1

    capex_row = row
    put(ws, f"B{capex_row}", "减：资本开支", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('capex_pct')}", F_LINK, NUM_FMT, border=True)
    row += 1

    nwc_row = row
    put(ws, f"B{nwc_row}", "减：营运资本增加", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(rev_row, i)}*{paddr('nwc_pct')}", F_LINK, NUM_FMT, border=True)
    row += 1

    fcff_row = row
    put(ws, f"B{fcff_row}", "自由现金流 FCFF", F_BOLD, border=True)
    for i in range(n):
        formula(ws, cell(i),
                f"={cell_at(nopat_row, i)}+{cell_at(da_row, i)}-{cell_at(capex_row, i)}-{cell_at(nwc_row, i)}",
                F_BOLD, NUM_FMT, border=True)
    row += 1

    df_row = row
    put(ws, f"B{df_row}", "折现系数（期中）", F_RATIO, border=True)
    for i in range(n):
        formula(ws, cell(i), f"=1/(1+{paddr('wacc')})^({i}+0.5)", F_RATIO, MULT_FMT, border=True)
    row += 1

    pv_row = row
    put(ws, f"B{pv_row}", "现金流现值", F_LINK, border=True)
    for i in range(n):
        formula(ws, cell(i), f"={cell_at(fcff_row, i)}*{cell_at(df_row, i)}", F_LINK, NUM_FMT, border=True)
    row += 2

    first_c, last_c = get_column_letter(FIRST), get_column_letter(FIRST + n - 1)
    summary = row
    items = [
        ("详细预测期现值合计", f"=SUM({first_c}{pv_row}:{last_c}{pv_row})", F_LBL, NUM_FMT),
        ("终值 · Gordon 永续法", f"={last_c}{fcff_row}*(1+{paddr('g')})/({paddr('wacc')}-{paddr('g')})", F_LBL, NUM_FMT),
        ("终值 · 退出倍数法", f"=({last_c}{ebit_row}+{last_c}{da_row})*{paddr('exit_multiple')}", F_LBL, NUM_FMT),
        ("终值 · ROIC 再投资法",
         f"=({last_c}{nopat_row})*(1+{paddr('g')})*(1-{paddr('g')}/{paddr('roic')})/({paddr('wacc')}-{paddr('g')})",
         F_LBL, NUM_FMT),
        ("终值取中点（Gordon 与退出倍数）", None, F_BOLD, NUM_FMT),
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
        ("上行/下行空间", None, F_BOLD, PCT_FMT),
        ("终值占企业价值比例", None, F_RATIO, PCT_FMT),
    ]
    for idx, (label, expr, font, fmt) in enumerate(items):
        put(ws, f"B{summary + idx}", label, font, border=True)
        if expr:
            formula(ws, f"C{summary + idx}", expr, font, fmt, border=True)
    rmap = {label: summary + i for i, (label, *_rest) in enumerate(items)}
    fmtmap = {label: fmt for label, _, _, fmt in items}

    def w(label, expr, font=None):
        formula(ws, f"C{rmap[label]}", expr, font or F_LINK, fmtmap[label], border=True)

    gordon_r = rmap["终值 · Gordon 永续法"]
    exit_r = rmap["终值 · 退出倍数法"]
    roic_r = rmap["终值 · ROIC 再投资法"]
    tv_r = rmap["终值取中点（Gordon 与退出倍数）"]
    pvtv_r = rmap["终值现值"]
    ev_r = rmap["企业价值 EV"]
    eq_r = rmap["股权价值"]
    per_r = rmap["每股价值"]
    w("终值取中点（Gordon 与退出倍数）", f"=AVERAGE(C{gordon_r}:C{exit_r})", F_BOLD)
    w("终值现值", f"=C{tv_r}/(1+{paddr('wacc')})^{paddr('years')}")
    w("企业价值 EV", f"=C{rmap['详细预测期现值合计']}+C{pvtv_r}", F_BOLD)
    w("股权价值", f"=C{ev_r}+C{rmap['加：货币资金']}-C{rmap['减：有息负债']}"
                   f"-C{rmap['减：少数股东权益']}-C{rmap['减：优先股']}", F_BOLD)
    w("每股价值", f"=IFERROR(C{eq_r}/C{rmap['股本（股）']},\"\")", F_BOLD)
    w("上行/下行空间", f"=IFERROR(C{per_r}/C{rmap['当前股价']}-1,\"\")")
    w("终值占企业价值比例", f"=IFERROR(C{pvtv_r}/C{ev_r},\"\")")
    P["_dcf_per_share"] = f"'DCF测算'!$C${per_r}"

    put(ws, f"B{rmap['终值占企业价值比例'] + 2}",
        "口径：期中折现；终值默认 Gordon 与退出倍数取中点，ROIC 法仅作交叉校验。", F_GRAY)


# ---------------------------------------------------------------- 相对估值


def _sheet_comps(wb, result, comps):
    ws = _sheet(wb, "相对估值", {"B": 22, "C": 24}
                | {get_column_letter(i): 12 for i in range(4, 14)} | {"N": 34}
                | {c: 12 for c in "PQRSTUVW"})
    title(ws, "B2", "相对估值（Comps，公式联动）")
    put(ws, "B3", "同业中位数由上方样本计算；倍数列是蓝字可手改；隐含价值与结论是公式。", F_GRAY)

    peers = comps.get("peer_companies") or []
    if not peers:
        put(ws, "B5", "（本次未取得可比公司样本）", F_WARN)
        P["_comps_per_share"] = None
        return

    row = 5
    headers = ["简称", "代码", "PE", "PB", "PS", "PCF", "PEG", "EV/收入", "EV/EBITDA",
               "EV/EBIT", "收入增速", "EBIT 利润率", "选取理由"]
    header_row(ws, row, headers, start_col=2)
    row += 1
    first = row
    for p in peers:
        put(ws, f"B{row}", p.get("name", ""), F_LBL, border=True)
        put(ws, f"C{row}", p.get("ticker", ""), F_LBL, border=True)
        for i, key in enumerate(["pe", "pb", "ps", "pcf", "peg", "ev_revenue", "ev_ebitda", "ev_ebit"]):
            put(ws, f"{get_column_letter(4 + i)}{row}", p.get(key), F_INPUT, MULT_FMT, border=True)
        put(ws, f"L{row}", p.get("revenue_growth"), F_INPUT, PCT_FMT, border=True)
        put(ws, f"M{row}", p.get("ebit_margin"), F_INPUT, PCT_FMT, border=True)
        put(ws, f"N{row}", p.get("selection_reason", ""), F_GRAY, align=WRAP, border=True)
        # 辅助统计区：按引擎的异常值规则筛选后参与中位数（PE>100、EV/收入>50 剔除）
        helper = {
            "P": f"=IF(AND(ISNUMBER(D{row}),D{row}>0,D{row}<=100),D{row},\"\")",
            "Q": f"=IF(AND(ISNUMBER(E{row}),E{row}>0),E{row},\"\")",
            "R": f"=IF(AND(ISNUMBER(F{row}),F{row}>0),F{row},\"\")",
            "S": f"=IF(AND(ISNUMBER(G{row}),G{row}>0),G{row},\"\")",
            "T": f"=IF(AND(ISNUMBER(H{row}),H{row}>0),H{row},\"\")",
            "U": f"=IF(AND(ISNUMBER(I{row}),I{row}>0,I{row}<=50),I{row},\"\")",
            "V": f"=IF(AND(ISNUMBER(J{row}),J{row}>0),J{row},\"\")",
            "W": f"=IF(AND(ISNUMBER(K{row}),K{row}>0),K{row},\"\")",
        }
        for col, expr in helper.items():
            formula(ws, f"{col}{row}", expr, F_GRAY, MULT_FMT)
        row += 1
    last = row - 1

    for col, label in zip("PQRSTUVW", ["PE统计", "PB统计", "PS统计", "PCF统计", "PEG统计",
                                       "EV/收入统计", "EV/EBITDA统计", "EV/EBIT统计"]):
        put(ws, f"{col}5", label, F_GRAY)
    med_row = row
    put(ws, f"B{med_row}", "同业中位数", F_BOLD, fill=FILL_BLOCK, border=True)
    for col, helper_col in zip("DEFGHIJK", "PQRSTUVW"):
        formula(ws, f"{col}{med_row}",
                f"=IFERROR(MEDIAN({helper_col}{first}:{helper_col}{last}),\"\")",
                F_LINK, MULT_FMT, fill=FILL_BLOCK, border=True)
    formula(ws, f"L{med_row}", f"=IFERROR(MEDIAN(L{first}:L{last}),\"\")", F_LINK, PCT_FMT,
            fill=FILL_BLOCK, border=True)
    formula(ws, f"M{med_row}", f"=IFERROR(MEDIAN(M{first}:M{last}),\"\")", F_LINK, PCT_FMT,
            fill=FILL_BLOCK, border=True)
    row += 1

    # 调整比例与采用倍数：与引擎的 adjustment 保持一致
    adjustments = {r.get("multiple"): (r.get("adjustment") or 0.0)
                   for r in (comps.get("results") or [])}
    col_key = {"D": "pe", "E": "pb", "F": "ps", "G": "pcf", "H": "peg",
               "I": "ev_revenue", "J": "ev_ebitda", "K": "ev_ebit"}
    adjust_row = row
    put(ws, f"B{row}", "倍数调整比例", F_LBL, fill=FILL_BLOCK, border=True)
    for col in col_key:
        put(ws, f"{col}{row}", adjustments.get(col_key[col], 0.0), F_INPUT, PCT_FMT,
            FILL_YELLOW, border=True)
    row += 1
    applied_row = row
    put(ws, f"B{row}", "采用倍数（中位×(1+调整)）", F_BOLD, fill=FILL_BLOCK, border=True)
    for col in col_key:
        formula(ws, f"{col}{row}", f"=IFERROR({col}{med_row}*(1+{col}{adjust_row}),\"\")",
                F_BOLD, MULT_FMT, border=True)
    row += 2

    # 目标指标
    tm = comps.get("target_multiples") or {}
    put(ws, f"B{row}", "目标公司指标", F_BOLD, fill=FILL_BLOCK)
    row += 1
    metric_rows = {}
    for label, key in [("净利润", "net_income"), ("净资产", "equity"), ("营业收入", "revenue"),
                       ("经营现金流", "cfo"), ("EBITDA", "ebitda"), ("EBIT", "ebit")]:
        put(ws, f"B{row}", label, F_LBL, border=True)
        # 从任一 result 的 metric_value 取；没有就用 target_multiples 推算
        metric_rows[key] = row
        put(ws, f"C{row}", None, F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
        row += 1
    # 用 results 里的 metric_value 回填
    for r in comps.get("results") or []:
        key = r.get("metric_basis")
        if key in metric_rows:
            put(ws, f"C{metric_rows[key]}", r.get("metric_value"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)

    nd_row = row
    put(ws, f"B{row}", "净负债", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('debt')}-{paddr('cash')}", F_LINK, NUM_FMT, border=True)
    row += 1
    mi_row = row
    put(ws, f"B{row}", "少数股东权益", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('minority')}", F_LINK, NUM_FMT, border=True)
    row += 1
    pref_row = row
    put(ws, f"B{row}", "优先股", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('preferred')}", F_LINK, NUM_FMT, border=True)
    row += 1
    growth_row = row
    put(ws, f"B{row}", "预期增速（PEG 用，收入增速近似）", F_LBL, border=True)
    put(ws, f"C{row}", comps.get("target_growth"), F_INPUT, PCT_FMT, FILL_YELLOW, border=True)
    row += 2

    # 隐含股权价值
    put(ws, f"B{row}", "各倍数隐含股权价值", F_BOLD, fill=FILL_BLOCK)
    row += 1
    used = comps.get("results") or []
    implied_rows = []
    for r in used:
        key = r.get("multiple")
        col = {"pe": "D", "pb": "E", "ps": "F", "pcf": "G", "peg": "H",
               "ev_revenue": "I", "ev_ebitda": "J", "ev_ebit": "K"}.get(key)
        if not col:
            continue
        put(ws, f"B{row}", r.get("label") or key, F_LBL, border=True)
        base_cell = f"$C${metric_rows.get(r.get('metric_basis'), 0)}" if r.get("metric_basis") in metric_rows else None
        if key == "peg":
            formula(ws, f"C{row}",
                    f"=IFERROR({col}{applied_row}*$C${growth_row}*100*{base_cell},\"\")",
                    F_LINK, NUM_FMT, border=True)
        elif key.startswith("ev_"):
            formula(ws, f"C{row}",
                    f"=IFERROR({col}{applied_row}*{base_cell}-$C${nd_row}-$C${mi_row}-$C${pref_row},\"\")",
                    F_LINK, NUM_FMT, border=True)
        else:
            formula(ws, f"C{row}", f"=IFERROR({col}{applied_row}*{base_cell},\"\")", F_LINK, NUM_FMT, border=True)
        implied_rows.append(row)
        row += 1

    concl_row = row
    put(ws, f"B{concl_row}", "隐含股权价值（中位）", F_BOLD, border=True)
    if implied_rows:
        refs = ",".join(f"C{x}" for x in implied_rows)
        formula(ws, f"C{concl_row}", f"=MEDIAN({refs})", F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1
    put(ws, f"B{row}", "隐含每股价值", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IFERROR(C{concl_row}/{paddr('shares')},\"\")", F_BOLD, NUM_FMT, border=True)
    P["_comps_per_share"] = f"'相对估值'!$C${row}"
    row += 2

    put(ws, f"B{row}", "倍数选择说明", F_BOLD)
    row += 1
    for block in comps.get("decisions") or []:
        for d in block.get("decisions") or []:
            put(ws, f"B{row}", f"{d.get('label')}：{'采用' if d.get('used') else '不采用'}；{d.get('reason')}",
                F_GRAY)
            ws.merge_cells(f"B{row}:N{row}")
            row += 1
    put(ws, f"B{row + 1}", "判断：" + (comps.get("judgment") or ""), F_LBL, align=WRAP)
    ws.merge_cells(f"B{row + 1}:N{row + 1}")
    ws.row_dimensions[row + 1].height = 32


# ---------------------------------------------------------------- SOTP


def _sheet_sotp(wb, result, sotp):
    ws = _sheet(wb, "分部估值", {"B": 24, "C": 22, "D": 20, "E": 14, "F": 24, "G": 26})
    title(ws, "B2", "分部估值（SOTP，公式联动）")
    put(ws, "B3", "分部收入来自年报「主营构成」；优先用 EV/EBITDA，缺失时用 EV/Revenue。", F_GRAY)
    rows = sotp.get("rows") or []
    if not rows:
        put(ws, "B5", "（未取得分部数据）", F_WARN)
        P["_sotp_per_share"] = None
        return

    row = 5
    header_row(ws, row, ["分部", "指标口径", "指标值", "采用倍数", "分部企业价值", "同业"], start_col=2)
    row += 1
    first = row
    for s in rows:
        put(ws, f"B{row}", s.get("name", ""), F_LBL, border=True)
        put(ws, f"C{row}", (s.get("multiple_type") or "").upper(), F_LBL, border=True)
        put(ws, f"D{row}", s.get("value"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
        put(ws, f"E{row}", s.get("multiple"), F_INPUT, MULT_FMT, FILL_YELLOW, border=True)
        formula(ws, f"F{row}", f"=IFERROR(D{row}*E{row},0)", F_LINK, NUM_FMT, border=True)
        put(ws, f"G{row}", "、".join(s.get("peer_names") or []), F_GRAY, border=True)
        row += 1
    last = row - 1

    row += 1
    total_row = row
    put(ws, f"B{row}", "分部企业价值合计", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=SUM(F{first}:F{last})", F_BOLD, NUM_FMT, border=True)
    row += 1
    cost_row = row
    put(ws, f"B{row}", "减：总部费用（资本化）", F_LBL, border=True)
    put(ws, f"C{row}", sotp.get("corporate_cost"), F_INPUT, NUM_FMT, FILL_YELLOW, border=True)
    row += 1
    nd_row = row
    put(ws, f"B{row}", "减：净负债", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('debt')}-{paddr('cash')}", F_LINK, NUM_FMT, border=True)
    row += 1
    mi_row = row
    put(ws, f"B{row}", "减：少数股东权益", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('minority')}", F_LINK, NUM_FMT, border=True)
    row += 1
    eq_row = row
    put(ws, f"B{row}", "股权价值", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IF(C{total_row}=0,\"\",C{total_row}-C{cost_row}-C{nd_row}-C{mi_row})",
            F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1
    put(ws, f"B{row}", "每股价值", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IFERROR(C{eq_row}/{paddr('shares')},\"\")", F_BOLD, NUM_FMT, border=True)
    P["_sotp_per_share"] = f"'分部估值'!$C${row}"
    row += 2
    put(ws, f"B{row}", f"分部收入覆盖：{sotp.get('revenue_coverage', 0):.1%}；"
                       f"分摊规则：{sotp.get('allocation_rule', '')}", F_GRAY)


# ---------------------------------------------------------------- DDM


def _sheet_ddm(wb, result, ddm):
    ws = _sheet(wb, "DDM测算", {"B": 28, "C": 18, "D": 46})
    title(ws, "B2", "金融行业绝对估值替代：DDM / 剩余收益")
    if not ddm.get("ok"):
        put(ws, "B4", f"（未启用：{ddm.get('error') or '不适用'}）", F_WARN)
        P["_ddm_per_share"] = None
        return
    rows = [
        ("净利润", ddm.get("net_income"), NUM_FMT, "元"),
        ("账面净资产", ddm.get("book_equity"), NUM_FMT, "元"),
        ("ROE", ddm.get("roe"), PCT_FMT, "净利润 / 净资产"),
        ("分红率", ddm.get("payout_ratio"), PCT_FMT, ddm.get("payout_source") or ""),
        ("增长率 g", ddm.get("growth"), PCT_FMT, ""),
        ("CAPM 股权成本 Ke", ddm.get("cost_of_equity_capm"), PCT_FMT, ""),
        ("市场隐含 Ke", ddm.get("implied_cost_of_equity"), PCT_FMT, ""),
        ("采用 Ke", ddm.get("cost_of_equity"), PCT_FMT, "CAPM 与市场隐含值校准"),
        ("稳定增长 DDM 股权价值", ddm.get("ddm_value"), NUM_FMT, "元"),
        ("剩余收益 RI 股权价值", ddm.get("ri_value"), NUM_FMT, "元"),
        ("股权价值（两者中位）", ddm.get("equity_value"), NUM_FMT, "元"),
    ]
    row = 4
    for label, value, fmt, note in rows:
        put(ws, f"B{row}", label, F_LBL, border=True)
        put(ws, f"C{row}", value, F_INPUT, fmt, border=True)
        put(ws, f"D{row}", note, F_GRAY, border=True)
        row += 1
    put(ws, f"B{row}", "每股价值", F_BOLD, border=True)
    put(ws, f"C{row}", ddm.get("per_share"), F_BOLD, NUM_FMT, FILL_OK, border=True)
    P["_ddm_per_share"] = f"'DDM测算'!$C${row}"


# ---------------------------------------------------------------- 三法融合


def _sheet_blend(wb, result, blended, scen):
    ws = _sheet(wb, "三法融合", {"B": 24, "C": 22, "D": 12, "E": 24, "F": 30})
    title(ws, "B2", "方法融合（权重可改，公式联动）")
    put(ws, "B3", "权重是蓝字黄底；各方法每股价值从对应表引用。改权重会改融合结果。", F_GRAY)

    row = 5
    header_row(ws, row, ["方法", "每股价值", "权重", "股权价值", "来源"], start_col=2)
    row += 1
    refs = [
        ("dcf", "DCF（收益法）", P.get("_dcf_per_share"), "DCF测算"),
        ("comps", "Comps（相对估值）", P.get("_comps_per_share"), "相对估值"),
        ("sotp", "SOTP（分部估值）", P.get("_sotp_per_share"), "分部估值"),
        ("ddm", "DDM/剩余收益", P.get("_ddm_per_share"), "DDM测算"),
    ]
    engine_w = {c.get("key"): (c.get("weight") or 0.0) for c in (blended.get("components") or [])}
    first_row = row
    used = []
    for key, label, ref, sheet in refs:
        if not ref:
            continue
        put(ws, f"B{row}", label, F_LBL, border=True)
        formula(ws, f"C{row}", f"=N({ref})", F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", round(engine_w.get(key, 0.0), 4), F_INPUT, PCT1_FMT, FILL_YELLOW, border=True)
        formula(ws, f"E{row}", f"=C{row}*{paddr('shares')}", F_LINK, NUM_FMT, border=True)
        put(ws, f"F{row}", f"引用「{sheet}」表", F_GRAY, border=True)
        used.append(row)
        row += 1
    if not used:
        put(ws, f"B{row}", "（没有可用方法）", F_WARN)
        return
    last_row = row - 1
    row += 1
    put(ws, f"B{row}", "权重合计", F_RATIO, border=True)
    formula(ws, f"C{row}", f"=SUM(D{first_row}:D{last_row})", F_RATIO, PCT1_FMT, border=True)
    row += 1
    put(ws, f"B{row}", "融合每股价值", F_BOLD, border=True)
    formula(ws, f"C{row}",
            f"=IFERROR(SUMPRODUCT(C{first_row}:C{last_row},D{first_row}:D{last_row})"
            f"/SUM(D{first_row}:D{last_row}),\"\")", F_BOLD, NUM_FMT, FILL_OK, border=True)
    row += 1
    put(ws, f"B{row}", "当前股价", F_LBL, border=True)
    formula(ws, f"C{row}", f"={paddr('price')}", F_LINK, NUM_FMT, border=True)
    price_row = row
    row += 1
    put(ws, f"B{row}", "上行/下行空间", F_BOLD, border=True)
    formula(ws, f"C{row}", f"=IFERROR(C{row - 2}/C{price_row}-1,\"\")", F_BOLD, PCT_FMT, border=True)
    row += 2

    if scen.get("base"):
        put(ws, f"B{row}", "三情景（引擎重算，静态）", F_BOLD, fill=FILL_BLOCK)
        row += 1
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
        put(ws, f"B{row + 1}", "注：情景是不同假设下的独立重算，改本表权重不会改变它们。", F_GRAY)


# ---------------------------------------------------------------- 敏感性


def _sheet_sensitivity(wb, result, sens):
    wg = sens.get("wacc_g") or {}
    ws = _sheet(wb, "敏感性-WACC×g", {"B": 14} | {get_column_letter(3 + i): 16 for i in range(6)})
    title(ws, "B2", "敏感性：每股价值 = f(WACC, 永续增长率)")
    if not wg.get("grid"):
        put(ws, "B4", "（未生成）", F_WARN)
    else:
        put(ws, "B3", "引擎逐格重算；基准格金色边框。改假设后请重新导出。", F_GRAY)
        row = 5
        put(ws, "B5", "WACC \\ g", F_HDR, fill=FILL_HDR, align=CENTER, border=True)
        for j, g in enumerate(wg["growth_axis"]):
            put(ws, f"{get_column_letter(3 + j)}{row}", g, F_KEY, PCT_FMT, FILL_YELLOW, CENTER, border=True)
        row += 1
        base = wg.get("base_index") or {}
        for i, w in enumerate(wg["wacc_axis"]):
            put(ws, f"B{row}", w, F_KEY, PCT_FMT, FILL_YELLOW, border=True)
            for j, v in enumerate(wg["grid"][i]):
                cell = put(ws, f"{get_column_letter(3 + j)}{row}", v, F_LINK, NUM_FMT, border=True)
                if base.get("x") == j and base.get("y") == i:
                    cell.border = Border(left=GOLD, right=GOLD, top=GOLD, bottom=GOLD)
            row += 1
        row += 1
        put(ws, f"B{row}", f"基准：WACC {wg.get('base_wacc', 0):.2%}，g {wg.get('base_growth', 0):.2%}", F_GRAY)

    gm = sens.get("growth_margin") or {}
    ws2 = _sheet(wb, "敏感性-增速×利润率", {"B": 14} | {get_column_letter(3 + i): 16 for i in range(6)})
    title(ws2, "B2", "敏感性：每股价值 = f(首年增速, EBIT 利润率)")
    if not gm.get("grid"):
        put(ws2, "B4", "（未生成）", F_WARN)
        return
    put(ws2, "B3", "引擎逐格重算；WACC 与 g 固定在基准值。", F_GRAY)
    row = 5
    put(ws2, "B5", "利润率 \\ 增速", F_HDR, fill=FILL_HDR, align=CENTER, border=True)
    for j, g in enumerate(gm["growth_axis"]):
        put(ws2, f"{get_column_letter(3 + j)}{row}", g, F_KEY, PCT_FMT, FILL_YELLOW, CENTER, border=True)
    row += 1
    base = gm.get("base_index") or {}
    for i, m in enumerate(gm["margin_axis"]):
        put(ws2, f"B{row}", m, F_KEY, PCT_FMT, FILL_YELLOW, border=True)
        for j, v in enumerate(gm["grid"][i]):
            cell = put(ws2, f"{get_column_letter(3 + j)}{row}", v, F_LINK, NUM_FMT, border=True)
            if base.get("x") == j and base.get("y") == i:
                cell.border = Border(left=GOLD, right=GOLD, top=GOLD, bottom=GOLD)
        row += 1


# ---------------------------------------------------------------- 台账 / 来源 / 规则


def _sheet_ledger(wb, result):
    ws = _sheet(wb, "假设台账", {"B": 28, "C": 18, "D": 10, "E": 14, "F": 56, "G": 10, "H": 10})
    title(ws, "B2", "假设台账")
    put(ws, "B3", "每条假设均标注来源类型、依据、置信度与是否可覆盖；展示层不另编数字。", F_GRAY)
    row = 5
    header_row(ws, row, ["假设", "取值", "单位", "来源类型", "来源/依据", "置信度", "可覆盖"], start_col=2)
    row += 1
    for a in result.get("assumptions") or []:
        put(ws, f"B{row}", a.get("name"), F_LBL, border=True)
        put(ws, f"C{row}", a.get("value"), F_LINK, border=True)
        put(ws, f"D{row}", a.get("unit"), F_LBL, border=True)
        put(ws, f"E{row}", a.get("source_type"), F_LBL, border=True)
        put(ws, f"F{row}", a.get("source"), F_GRAY, align=WRAP, border=True)
        put(ws, f"G{row}", a.get("confidence"), F_LBL, None, None, CENTER, border=True)
        put(ws, f"H{row}", "是" if a.get("overridable") else "否", F_LBL, None, None, CENTER, border=True)
        row += 1


def _sheet_sources(wb, result):
    ws = _sheet(wb, "数据来源", {"B": 44, "C": 20, "D": 14, "E": 12, "F": 40})
    title(ws, "B2", "数据来源与口径")
    row = 4
    header_row(ws, row, ["来源", "用途", "取数日", "性质", "备注"], start_col=2)
    row += 1
    for s in result.get("sources") or []:
        put(ws, f"B{row}", s.get("name"), F_LBL, align=WRAP, border=True)
        put(ws, f"C{row}", s.get("purpose"), F_LBL, border=True)
        put(ws, f"D{row}", s.get("as_of"), F_LBL, border=True)
        put(ws, f"E{row}", "官方源" if s.get("official") else "非官方源", F_LBL, border=True)
        put(ws, f"F{row}", s.get("note", ""), F_GRAY, align=WRAP, border=True)
        row += 1
    put(ws, f"B{row + 1}", "as-of 规则：市场数据原则上取基准日或之前可获得的数据；"
                          "确需使用基准日后数据时须标注「后见信息」。", F_GRAY)


def _sheet_rules(wb, result):
    ws = _sheet(wb, "行业门槛与规则", {"B": 26, "C": 20, "D": 70})
    title(ws, "B2", "行业门槛、方法可靠性与规则轨迹")
    row = 4
    put(ws, f"B{row}", "估值状态", F_BOLD); put(ws, f"C{row}", result.get("status")); row += 1
    put(ws, f"B{row}", "行业支持", F_BOLD); put(ws, f"C{row}", result.get("industry_support")); row += 1
    gate = result.get("industry_gate") or {}
    put(ws, f"B{row}", "行业门槛说明", F_BOLD); put(ws, f"C{row}", gate.get("reason", ""), F_LBL, align=WRAP); row += 2

    put(ws, f"B{row}", "方法可靠性", F_BOLD, fill=FILL_BLOCK); row += 1
    header_row(ws, row, ["方法", "评分", "等级", "扣分项"], start_col=2); row += 1
    for key, rel in (result.get("reliabilities") or {}).items():
        put(ws, f"B{row}", key, F_LBL, border=True)
        put(ws, f"C{row}", rel.get("score"), F_LINK, border=True)
        put(ws, f"D{row}", rel.get("level"), F_LBL, border=True)
        put(ws, f"E{row}", "；".join(f"{d.get('reason')}（-{d.get('points')}）"
                                     for d in rel.get("deductions") or []), F_GRAY, align=WRAP, border=True)
        row += 1
    row += 1
    put(ws, f"B{row}", "权重规则", F_BOLD, fill=FILL_BLOCK); row += 1
    for t in (result.get("blended") or {}).get("trace") or []:
        put(ws, f"B{row}", t.get("method") or "—", F_LBL, border=True)
        put(ws, f"C{row}", t.get("weight"), F_LINK, PCT1_FMT, border=True)
        put(ws, f"D{row}", t.get("rule"), F_GRAY, align=WRAP, border=True)
        row += 1
    row += 1
    put(ws, f"B{row}", "门槛与提示", F_BOLD, fill=FILL_BLOCK); row += 1
    for g in result.get("gates") or []:
        put(ws, f"B{row}", g.get("severity"), F_WARN if g.get("severity") in ("warn", "block") else F_LBL,
            border=True)
        put(ws, f"C{row}", g.get("code"), F_LBL, border=True)
        put(ws, f"D{row}", g.get("message"), F_GRAY, align=WRAP, border=True)
        row += 1


def _sheet_summary(wb, result, company, dcf, comps, sotp, ddm, blended, scen):
    ws = _sheet(wb, "说明", {"B": 30, "C": 22, "D": 16, "E": 16, "F": 52})
    title(ws, "B2", "FinScope 估值底稿 v2")
    put(ws, "B3", f"{company.get('name', '')}（{company.get('ticker', '')}）", F_BOLD)
    put(ws, "B4", f"基准期 {company.get('report_period', '—')} · 价格日期 "
                  f"{result.get('market_data', {}).get('price_date', '—')} · "
                  f"币种 {company.get('currency', 'CNY')} · 状态 {result.get('status')}", F_GRAY)
    put(ws, "B5", _source_line(result), F_GRAY)

    row = 7
    put(ws, f"B{row}", "一、结论（导出时快照）", F_BOLD, fill=FILL_BLOCK); row += 1
    if blended.get("ok"):
        for label, value, fmt in [
            ("融合每股价值", blended.get("blended_per_share"), NUM_FMT),
            ("当前市价", blended.get("current_price"), NUM_FMT),
            ("上行/下行空间", blended.get("upside"), PCT_FMT),
            ("估值判断", blended.get("verdict"), None),
            ("综合置信度", blended.get("confidence"), None),
        ]:
            put(ws, f"B{row}", label, F_LBL, border=True)
            put(ws, f"C{row}", value, F_BOLD if label == "融合每股价值" else F_LINK, fmt,
                FILL_OK if label == "融合每股价值" else None, border=True)
            row += 1
    else:
        put(ws, f"B{row}", f"（未形成融合结论：{blended.get('error')}）", F_WARN)
        row += 1

    row += 1
    put(ws, f"B{row}", "二、方法结果", F_BOLD, fill=FILL_BLOCK); row += 1
    header_row(ws, row, ["方法", "每股价值", "权重", "可靠性", "说明"], start_col=2); row += 1
    weights = blended.get("weights") or {}
    rel = result.get("reliabilities") or {}
    for key, label, ps in [
        ("dcf", "DCF", dcf.get("per_share") if dcf.get("ok") else None),
        ("comps", "Comps", comps.get("implied_per_share") if comps.get("ok") else None),
        ("sotp", "SOTP", sotp.get("per_share") if sotp.get("ok") else None),
        ("ddm", "DDM", ddm.get("per_share") if ddm.get("ok") else None),
    ]:
        if ps is None:
            continue
        put(ws, f"B{row}", label, F_LBL, border=True)
        put(ws, f"C{row}", ps, F_LINK, NUM_FMT, border=True)
        put(ws, f"D{row}", weights.get(key), F_LINK, PCT1_FMT, border=True)
        put(ws, f"E{row}", rel.get(key, {}).get("score"), F_LINK, border=True)
        put(ws, f"F{row}", rel.get(key, {}).get("level"), F_GRAY, border=True)
        row += 1

    row += 1
    put(ws, f"B{row}", "三、关键提示", F_BOLD, fill=FILL_BLOCK); row += 1
    for w in (result.get("warnings") or [])[:12]:
        put(ws, f"B{row}", f"⚠ {str(w)[:180]}", F_WARN if "⚠" in str(w) else F_GRAY)
        ws.merge_cells(f"B{row}:F{row}")
        row += 1

    row += 1
    put(ws, f"B{row}", "四、使用说明", F_BOLD, fill=FILL_BLOCK); row += 1
    for text in [
        "· 蓝字：手输/假设；蓝字黄底：关键驱动；黑字：公式；红字：提示。",
        "· 「参数假设」是单一真源，改假设后 DCF 与三法融合会联动；敏感性矩阵与情景需重新导出刷新。",
        "· 本底稿由引擎先算一遍，再把结果写成公式底稿；两边口径一致（期中折现）。",
        result.get("disclaimer") or "仅供研究与教学用途，不构成投资建议。",
    ]:
        put(ws, f"B{row}", text, F_GRAY, align=WRAP)
        ws.merge_cells(f"B{row}:F{row}")
        ws.row_dimensions[row].height = 28
        row += 1
