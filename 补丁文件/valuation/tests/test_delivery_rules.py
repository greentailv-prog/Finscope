"""D 终期 C1–C4 + P1 的回归测试。

运行：python -m valuation.tests.test_delivery_rules
"""
from __future__ import annotations

import unittest
from pathlib import Path

from valuation import run
from valuation.core import defaults
from valuation.tests.sample_inputs import bank_payload, maotai_payload
from valuation.tests.build_synthetic_example import payload as synthetic_payload

VALUATION = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = VALUATION.parent


class DeliveryRuleTests(unittest.TestCase):
    def test_bank_gate_is_partial_and_limited(self):
        gate = defaults.industry_gate("银行Ⅱ")
        self.assertEqual(gate["support"], "limited")
        self.assertFalse(gate["standard_fcff_supported"])

        r = run(bank_payload(), fetch=False, export_excel=False)
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["industry_support"], "limited")
        self.assertEqual(r["gate_reason"], "standard_fcff_unsupported; ddm_used")
        self.assertFalse(r["dcf"].get("ok"))
        self.assertTrue(r["ddm"]["ok"])
        self.assertGreater(r["ddm"]["per_share"], 0)
        self.assertIsNotNone(r["blended"]["blended_per_share"])

    def test_real_estate_stays_unsupported(self):
        gate = defaults.industry_gate("房地产")
        self.assertEqual(gate["support"], "unsupported")
        self.assertFalse(gate["standard_fcff_supported"])
        reit = defaults.industry_gate("REITs")
        self.assertEqual(reit["support"], "unsupported")

    def test_no_price_keeps_equity_but_no_per_share(self):
        r = run(maotai_payload(None), fetch=False, export_excel=False)
        self.assertTrue(r["dcf"]["ok"])
        self.assertIsNone(r["dcf"]["per_share"])
        self.assertGreater(r["dcf"]["equity_value"], 0)
        self.assertIsNone(r["blended"]["blended_per_share"])
        self.assertIsNotNone(r["blended"]["blended_equity_value"])
        for key in ("bull", "base", "bear"):
            self.assertIsNone(r["scenarios"][key]["per_share"])
        grid = r["sensitivity"]["wacc_g"]["matrix"]
        self.assertEqual(len(grid), 5)
        self.assertTrue(all(v is None for row in grid for v in row))
        self.assertTrue(any("未获取到实时行情" in w for w in r["warnings"]))

    def test_with_price_has_sensitivity_and_monotonic_scenarios(self):
        r = run(maotai_payload(1480.0), fetch=False, export_excel=False)
        self.assertIsNotNone(r["dcf"]["per_share"])
        grid = r["sensitivity"]["wacc_g"]["matrix"]
        self.assertEqual((len(grid), len(grid[0])), (5, 5))
        self.assertGreaterEqual(sum(1 for row in grid for v in row if v is not None), 20)
        sc = r["scenarios"]
        self.assertGreaterEqual(sc["bull"]["per_share"], sc["base"]["per_share"])
        self.assertGreaterEqual(sc["base"]["per_share"], sc["bear"]["per_share"])

    def test_driver_path_has_sensitivity_and_scenarios(self):
        r = run(synthetic_payload(), fetch=False, export_excel=False)
        self.assertTrue(r["dcf"]["ok"])
        self.assertEqual(len(r["sensitivity"]["wacc_g"]["matrix"]), 5)
        self.assertGreaterEqual(
            sum(1 for row in r["sensitivity"]["wacc_g"]["matrix"] for v in row if v is not None), 20)
        self.assertIsNone(r["sensitivity"].get("growth_margin"))
        sc = r["scenarios"]
        self.assertEqual(sc.get("scenario_basis"), "driver_rows_scaled")
        self.assertGreaterEqual(sc["bull"]["per_share"], sc["base"]["per_share"])
        self.assertGreaterEqual(sc["base"]["per_share"], sc["bear"]["per_share"])
        allowed = {"history", "management", "industry", "model"}
        self.assertTrue(all(a["source_type"] in allowed for a in r["assumptions"]))

    def test_excel_path_is_relative_and_file_exists(self):
        r = run(maotai_payload(1480.0), fetch=False, export_excel=True)
        path = r.get("excel_path") or ""
        self.assertTrue(path)
        self.assertFalse(Path(path).is_absolute(), path)
        self.assertTrue((PACKAGE_ROOT / path).exists(), path)
        self.assertIn(r.get("excel_format"), ("professional_18_sheets", "legacy_12_sheets"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
