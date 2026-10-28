"""
Profit bridge: the components sum exactly to the change in profit after tax.

Non-bank vector:
| figure            | current   | prior   |
|-------------------|-----------|---------|
| revenue           | 1,000,000 | 800,000 |
| cost of sales     |   600,000 | 500,000 |
| operating profit  |   150,000 | 100,000 |
| finance cost      |    30,000 |  25,000 |
| taxation          |    36,000 |  15,000 |
| profit after tax  |    84,000 |  60,000 |
Operating costs = (revenue - cost of sales) - operating profit: 250,000 and 200,000.
Other = PAT - (operating profit - finance cost - tax): 0 and 0.
| component        | working                    | change    |
|------------------|----------------------------|-----------|
| Revenue          | 1,000,000 - 800,000        | +200,000  |
| Cost of sales    | -(600,000 - 500,000)       | -100,000  |
| Operating costs  | -(250,000 - 200,000)       |  -50,000  |
| Finance cost     | -(30,000 - 25,000)         |   -5,000  |
| Taxation         | -(36,000 - 15,000)         |  -21,000  |
| Other items      | 0 - 0                      |        0  |
| total            | = 84,000 - 60,000          |  +24,000  |

Vector with other income of 10,000 in the current year (tax 39,000, PAT 91,000):
Other = 91,000 - (150,000 - 30,000 - 39,000) = 10,000; total = 91,000 - 60,000 = 31,000:
+200,000 - 100,000 - 50,000 - 5,000 - 24,000 + 10,000 = 31,000.

Bank vector:
| figure               | current | prior |
|----------------------|---------|-------|
| net mark-up income   |   500   |  400  |
| non mark-up income   |   200   |  150  |
| operating expenses   |   300   |  250  |
| provisions           |    50   |   40  |
| profit before tax    |   360   |  260  |
| profit after tax     |   216   |  156  |
Other = PBT - (NMI + NMII - opex - provisions): 10 and 0. Tax = PBT - PAT: 144 and 104.
+100 + 50 - 50 - 10 + 10 - 40 = 60 = 216 - 156.
"""

import random

from intelligence.bridge import compute_bridge

CUR = {"revenue": 1_000_000, "cost_of_sales": 600_000, "operating_profit": 150_000,
       "finance_cost": 30_000, "tax_expense": 36_000, "profit_after_tax": 84_000}
PRIOR = {"revenue": 800_000, "cost_of_sales": 500_000, "operating_profit": 100_000,
         "finance_cost": 25_000, "tax_expense": 15_000, "profit_after_tax": 60_000}


def test_non_bank_components():
    b = compute_bridge("manufacturer", CUR, PRIOR)
    assert b.components == [("Revenue", 200_000), ("Cost of sales", -100_000),
                            ("Operating costs", -50_000), ("Finance cost", -5_000),
                            ("Taxation", -21_000), ("Other items", 0)]
    assert b.total == 24_000 == b.end - b.start


def test_other_items_carry_what_the_chain_leaves_out():
    cur = dict(CUR, tax_expense=39_000, profit_after_tax=91_000)
    b = compute_bridge("non_manufacturer", cur, PRIOR)
    assert dict(b.components)["Other items"] == 10_000
    assert dict(b.components)["Taxation"] == -24_000
    assert b.total == 31_000 == b.end - b.start


def test_bank_components():
    cur = {"net_markup_income": 500, "non_markup_income": 200, "operating_expenses": 300,
           "provisions": 50, "profit_before_tax": 360, "profit_after_tax": 216}
    prior = {"net_markup_income": 400, "non_markup_income": 150, "operating_expenses": 250,
             "provisions": 40, "profit_before_tax": 260, "profit_after_tax": 156}
    b = compute_bridge("bank", cur, prior)
    assert b.components == [("Net mark-up income", 100), ("Non mark-up income", 50),
                            ("Operating expenses", -50), ("Provisions", -10),
                            ("Other items", 10), ("Taxation", -40)]
    assert b.total == 60 == b.end - b.start


def test_sums_exactly_for_any_entered_figures():
    rng = random.Random(1028)

    def figures(keys):
        return {k: rng.randint(-10**15, 10**15) for k in keys}

    for company_type, keys in (
        ("manufacturer", CUR.keys()),
        ("bank", ("net_markup_income", "non_markup_income", "operating_expenses", "provisions",
                  "profit_before_tax", "profit_after_tax")),
    ):
        for _ in range(1_000):
            cur, prior = figures(keys), figures(keys)
            b = compute_bridge(company_type, cur, prior)
            assert b.total == cur["profit_after_tax"] - prior["profit_after_tax"]
            assert all(isinstance(v, int) for _, v in b.components)


def test_needs_both_years():
    b = compute_bridge("manufacturer", CUR, {})
    assert b.components == [] and "Revenue (net sales) (prior)" in b.missing
