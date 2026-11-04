#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字段映射表：东方财富 / A 抽取结果 → B 引擎输入字段。

只放映射，不含逻辑。新增数据源时只改这里。

B 的字段名以 financial-diagnosis/INPUT_SCHEMA.md 为准。
注意两处历史命名差异：
  - A 用 current_assets / current_liabilities，B 用 total_current_assets / total_current_liabilities
  - A 用 cash / equity_attr / net_profit_attr，B 用 cash_and_equivalents / equity_parent / net_income_parent
本模块把两种写法都认下来，B 引擎不用改。
"""

# --------------------------------------------------------------------------- #
# 东方财富 F10 三表字段 → B 字段
# 值是一个候选列表，按顺序取第一个非空；None 表示该源没有对应科目。
# --------------------------------------------------------------------------- #
EM_TO_B = {
    # 利润表
    # 用 OPERATE_INCOME（营业收入）而不是 TOTAL_OPERATE_INCOME（营业总收入）：
    # 后者含利息收入、已赚保费等，与 OPERATE_COST（营业成本）不是同一配对口径，
    # 直接相减会把毛利率算高。茅台 2025：营业收入 1688.38 亿，营业总收入 1720.54 亿。
    "revenue":                      ["OPERATE_INCOME", "TOTAL_OPERATE_INCOME"],
    "cost_of_revenue":              ["OPERATE_COST"],
    "operating_profit":             ["OPERATE_PROFIT"],
    "pretax_profit":                ["TOTAL_PROFIT"],
    "income_tax_expense":           ["INCOME_TAX"],
    "net_income":                   ["NETPROFIT"],
    "net_income_parent":            ["PARENT_NETPROFIT"],
    "net_income_deducted":          ["DEDUCT_PARENT_NETPROFIT"],
    "selling_expense":              ["SALE_EXPENSE"],
    "admin_expense":                ["MANAGE_EXPENSE"],
    "rd_expense":                   ["RESEARCH_EXPENSE"],
    "finance_expense":              ["FINANCE_EXPENSE"],
    "interest_expense":             ["INTEREST_EXPENSE"],
    "depreciation_amortization":    ["FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE",
                                     "USERIGHT_ASSET_AMORTIZE"],
    # 资产负债表
    "cash_and_equivalents":         ["MONETARYFUNDS"],
    "accounts_receivable":          ["ACCOUNTS_RECE"],
    "notes_receivable":             ["NOTE_ACCOUNTS_RECE"],
    "contract_assets":              ["CONTRACT_ASSET"],
    "inventory":                    ["INVENTORY"],
    "total_current_assets":         ["TOTAL_CURRENT_ASSETS"],
    "fixed_assets":                 ["FIXED_ASSET"],
    "goodwill":                     ["GOODWILL"],
    "total_assets":                 ["TOTAL_ASSETS"],
    "accounts_payable":             ["ACCOUNTS_PAYABLE"],
    "total_current_liabilities":    ["TOTAL_CURRENT_LIAB"],
    "short_term_borrowings":        ["SHORT_LOAN"],
    "current_portion_lt_debt":      ["NONCURRENT_LIAB_1YEAR"],
    "long_term_borrowings":         ["LONG_LOAN"],
    "bonds_payable":                ["BOND_PAYABLE"],
    "total_liabilities":            ["TOTAL_LIABILITIES"],
    "equity_parent":                ["TOTAL_PARENT_EQUITY"],
    "total_equity":                 ["TOTAL_EQUITY"],
    # 现金流量表
    "ocf":                          ["NETCASH_OPERATE"],
    "cf_investing":                 ["NETCASH_INVEST"],
    "cf_financing":                 ["NETCASH_FINANCE"],
    "capex":                        ["CONSTRUCT_LONG_ASSET"],
    "cash_received_from_sales":     ["SALES_SERVICES"],
    "interest_paid":                ["PAY_INTEREST_COMMISSION"],
    "dividend_paid":                ["ASSIGN_DIVIDEND_PORFIT"],
    # 不映射 END_CASH_EQUIVALENTS：该字段与货币资金量级对不上（茅台 2025 报 84.73 亿，
    # 实际年末现金及现金等价物约 516 亿），来源口径不明。宁可缺，不可错。
}

# 同一 B 字段由多个源字段相加得到时列在这里（折旧摊销常拆成四项）
EM_SUM = {
    "depreciation_amortization": ["FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE",
                                  "USERIGHT_ASSET_AMORTIZE"],
}

# 东财三张表的接口名
EM_REPORTS = {
    "balance": "RPT_F10_FINANCE_GBALANCE",
    "income": "RPT_F10_FINANCE_GINCOME",
    "cashflow": "RPT_F10_FINANCE_GCASHFLOW",
}

# --------------------------------------------------------------------------- #
# A（financial-extraction）的科目键 → B 字段
# 同时兼容 canonical 键与 A 早期的旧键。
# --------------------------------------------------------------------------- #
A_TO_B = {
    # 旧键
    "net_profit": "net_income",
    "net_profit_attr": "net_income_parent",
    "net_profit_deducted": "net_income_deducted",
    "equity_attr": "equity_parent",
    "cash": "cash_and_equivalents",
    "cfo": "ocf",
    "cfi": "cf_investing",
    "cff": "cf_financing",
    "operating_cost": "cost_of_revenue",
    "rd_expense": "rd_expense",
    # canonical 键（A 新交付已改用这套）
    "current_assets": "total_current_assets",
    "current_liabilities": "total_current_liabilities",
    "net_income_excl_nonrecurring": "net_income_deducted",
    "rnd_expense": "rd_expense",
    "total_equity": "total_equity",
}

# B 输入契约里承认的全部字段，用于报告缺口
B_FIELDS = [
    "revenue", "cost_of_revenue", "operating_profit", "pretax_profit",
    "income_tax_expense", "net_income", "net_income_parent", "net_income_deducted",
    "selling_expense", "admin_expense", "rd_expense", "finance_expense",
    "interest_expense", "depreciation_amortization", "impairment_loss",
    "cash_and_equivalents", "restricted_cash", "accounts_receivable",
    "notes_receivable", "contract_assets", "inventory", "total_current_assets",
    "fixed_assets", "goodwill", "total_assets", "accounts_payable",
    "total_current_liabilities", "short_term_borrowings",
    "current_portion_lt_debt", "long_term_borrowings", "bonds_payable",
    "total_liabilities", "equity_parent", "total_equity",
    "ocf", "cf_investing", "cf_financing", "capex", "cash_received_from_sales",
    "interest_paid", "dividend_paid", "cf_cash_end", "minority_interest",
    "minority_pnl",
]

# 金额类字段（用于校验：比率类不在此列）
AMOUNT_FIELDS = set(B_FIELDS)

# 中文名，供日志与看板用；与 field_labels.json 保持一致
FIELD_CN = {
    "revenue": "营业收入", "cost_of_revenue": "营业成本",
    "operating_profit": "营业利润", "pretax_profit": "利润总额",
    "income_tax_expense": "所得税费用", "net_income": "净利润",
    "net_income_parent": "归属于母公司股东的净利润",
    "net_income_deducted": "扣非归母净利润",
    "selling_expense": "销售费用", "admin_expense": "管理费用",
    "rd_expense": "研发费用", "finance_expense": "财务费用",
    "interest_expense": "利息费用", "depreciation_amortization": "折旧与摊销",
    "cash_and_equivalents": "货币资金", "accounts_receivable": "应收账款",
    "notes_receivable": "应收票据", "contract_assets": "合同资产",
    "inventory": "存货", "total_current_assets": "流动资产合计",
    "fixed_assets": "固定资产", "goodwill": "商誉", "total_assets": "资产总计",
    "accounts_payable": "应付账款", "total_current_liabilities": "流动负债合计",
    "short_term_borrowings": "短期借款", "current_portion_lt_debt": "一年内到期的非流动负债",
    "long_term_borrowings": "长期借款", "bonds_payable": "应付债券",
    "total_liabilities": "负债合计", "equity_parent": "归属于母公司股东权益合计",
    "total_equity": "所有者权益合计", "ocf": "经营活动产生的现金流量净额",
    "cf_investing": "投资活动产生的现金流量净额",
    "cf_financing": "筹资活动产生的现金流量净额", "capex": "购建固定资产等支付的现金",
    "cash_received_from_sales": "销售商品、提供劳务收到的现金",
    "interest_paid": "分配股利、利润或偿付利息支付的现金",
    "dividend_paid": "现金分红", "cf_cash_end": "期末现金及现金等价物余额",
    "minority_interest": "少数股东权益", "minority_pnl": "少数股东损益",
}


def b_key(raw: str):
    """把 A / canonical 键翻成 B 键；已经是 B 键就原样返回。"""
    return A_TO_B.get(raw, raw)
