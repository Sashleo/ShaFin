# Calculations

Every formula ShaFin computes, defined once. The code is in `intelligence/`; the
hand-computed test vectors are in `tests/calculations/`, one file per section below.

## Ground rules

- **Figures are entered, never fetched.** Every figure is typed by the user from an annual
  report and stored as a whole number of rupees, with source `entered`.
- **Exact arithmetic.** Calculations use Python `Fraction`s on whole rupees. Nothing is
  rounded until it is displayed; display rounding is half away from zero (`intelligence/display.py`).
- **No defaults, no fallbacks.** A metric whose inputs are not all entered is not computed;
  it says `Required: <input>`. A division by zero is "not defined", never zero. No rate has
  a default: every rate is an assumption entered for the analysis, with its source and date.
- **Balance sheet figures are closing balances** of the current year, except where a formula
  says "average", which is (current + prior) / 2.
- **Company type decides the models.** Manufacturer and non-manufacturer: ratios, DuPont,
  Altman, DCF. Bank: bank ratios and P/B beside ROE and P/E; no Altman, no DCF.

## Units (`test_units.py`)

Reports state figures in one of six units:

| Unit | Rupees per unit |
|---|---|
| Rupees | 1 |
| Thousand | 1,000 |
| Lakh | 100,000 |
| Million | 1,000,000 |
| Crore | 10,000,000 |
| Billion | 1,000,000,000 |

`whole rupees = typed number x rupees per unit`, computed on integers: the typed digits
form an integer, which is multiplied by the factor and divided by 10 to the number of
decimal places. If that division leaves a remainder, the figure would need fractions of a
rupee and is refused, not rounded. `(1,234)` is read as -1,234. Counts (shares) and
percentages (CAR) are not scaled.

## Ratios: manufacturers and non-manufacturers (`test_ratios.py`)

| Metric | Formula |
|---|---|
| Gross margin | Gross profit / Revenue |
| Operating margin | Operating profit / Revenue |
| Net margin | Profit after tax / Revenue |
| Return on equity (ROE) | Profit after tax / Total equity |
| Return on assets (ROA) | Profit after tax / Total assets |
| Current ratio | Total current assets / Total current liabilities |
| Quick ratio | (Total current assets - Inventory) / Total current liabilities |
| Debt to equity | (Short-term borrowings + Long-term borrowings) / Total equity |
| Liabilities to assets | Total liabilities / Total assets |
| Equity multiplier | Total assets / Total equity |
| Interest coverage | Operating profit / Finance cost |
| Asset turnover | Revenue / Total assets |
| Days receivable | Trade debts / Revenue x 365 |
| Days inventory | Inventory / Cost of sales x 365 |
| Days payable | Trade and other payables / Cost of sales x 365 |
| Free cash flow | Net cash from operating activities - Capital expenditure |
| Earnings per share | Profit after tax / Shares outstanding |
| Revenue growth | (Revenue - prior Revenue) / prior Revenue; not defined if prior <= 0 |
| Profit after tax growth | (PAT - prior PAT) / prior PAT; not defined if prior <= 0 |

Short-term borrowings include the current portion of long-term debt; long-term borrowings
are the non-current portion. Interest coverage is not defined when finance cost is zero.

## DuPont (`test_dupont.py`)

`ROE = Net margin x Asset turnover x Equity multiplier`
`    = (PAT / Revenue) x (Revenue / Total assets) x (Total assets / Total equity)`

All three use the same closing balances as ROE, so the product equals ROE exactly; the test
checks it for 500 random sets of figures as well as the hand vector.

## Altman Z (`test_altman.py`)

Both variants share:

- X1 = (Total current assets - Total current liabilities) / Total assets
- X2 = Retained earnings / Total assets
- X3 = Operating profit (EBIT) / Total assets

**Manufacturers: the original Z.**
`Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5`
- X4 = Market value of equity / Total liabilities, where market value = share price
  (an assumption) x shares outstanding
- X5 = Revenue / Total assets
- Zones: **safe above 2.99, distress below 1.81**, grey from 1.81 to 2.99 inclusive.
- Source: Altman, E. I. (1968). Financial ratios, discriminant analysis and the prediction
  of corporate bankruptcy. *The Journal of Finance*, 23(4), 589-609. The paper states the
  coefficients for X1 to X4 in percentage form (0.012, 0.014, 0.033, 0.006) and 0.999 for
  X5; with the ratios as decimals they are 1.2, 1.4, 3.3, 0.6 and 1.0.

**Non-manufacturers: Z''.**
`Z'' = 6.56 X1 + 3.26 X2 + 6.72 X3 + 1.05 X4`
- X4 = Book value of equity / Total liabilities
- Zones: **safe above 2.60, distress below 1.10**, grey from 1.10 to 2.60 inclusive.
- No constant. Adding 3.25 gives the separate emerging-market score (Altman, Hartzell and
  Peck, 1995), which has its own cut-offs; the tests check that Z'' has no constant.
- Source: Altman, E. I. (2000). *Predicting financial distress of companies: revisiting the
  Z-score and ZETA models.* Stern School of Business, New York University; also Altman and
  Hotchkiss (2006), *Corporate Financial Distress and Bankruptcy*, 3rd ed., Wiley.

Every input is required: there is no partial score. A zero total assets or total
liabilities makes the score not defined. **Banks: not applicable.** Altman's samples
excluded financial companies, and a bank's balance sheet (deposits as liabilities, loans as
assets) does not fit the ratios.

## DCF: free cash flow to the firm (`test_dcf.py`)

Non-banks only. Assumptions (all entered, each with a source and date): risk-free rate,
equity risk premium, beta, corporate tax rate, terminal growth, forecast years (1 to 15),
debt weight, revenue growth, EBIT margin, D&A % of revenue, capex % of revenue,
working-capital % of the revenue increase, and optionally the cost of debt.

| Step | Formula |
|---|---|
| Revenue, year t | Revenue_(t-1) x (1 + revenue growth); Revenue_0 = current revenue |
| EBIT, year t | Revenue_t x EBIT margin |
| NOPAT, year t | EBIT_t x (1 - tax rate) |
| D&A, year t | Revenue_t x D&A % |
| Capex, year t | Revenue_t x capex % |
| Change in working capital, year t | (Revenue_t - Revenue_(t-1)) x working-capital % |
| FCFF, year t | NOPAT_t + D&A_t - Capex_t - change in working capital_t |
| Cost of equity (CAPM) | Risk-free rate + Beta x Equity risk premium |
| Cost of debt | The entered assumption; if empty, Finance cost / average borrowings, where average borrowings = (current + prior short- and long-term borrowings) / 2. If the inputs are missing or the average is zero, the DCF does not run and names what it needs. |
| WACC | (1 - debt weight) x Cost of equity + debt weight x Cost of debt x (1 - tax rate) |
| Present value, year t | FCFF_t / (1 + WACC)^t (end-of-year discounting) |
| Terminal value (Gordon growth) | FCFF_N x (1 + g) / (WACC - g) |
| Enterprise value | Sum of present values + Terminal value / (1 + WACC)^N |
| Net debt | Short-term + long-term borrowings - Cash |
| Equity value | Enterprise value - Net debt |
| Value per share | Equity value / Shares outstanding |

Sources:

- **CAPM** (cost of equity): Sharpe, W. F. (1964). Capital asset prices: a theory of market
  equilibrium under conditions of risk. *The Journal of Finance*, 19(3), 425-442; and
  Lintner, J. (1965). The valuation of risk assets and the selection of risky investments
  in stock portfolios and capital budgets. *The Review of Economics and Statistics*, 47(1),
  13-37.
- **WACC** (with the tax shield on debt): Modigliani, F. and Miller, M. H. (1958). The cost
  of capital, corporation finance and the theory of investment. *The American Economic
  Review*, 48(3), 261-297; and Modigliani, F. and Miller, M. H. (1963). Corporate income
  taxes and the cost of capital: a correction. *The American Economic Review*, 53(3),
  433-443.
- **Gordon growth model** (terminal value): Gordon, M. J. (1959). Dividends, earnings, and
  stock prices. *The Review of Economics and Statistics*, 41(2), 99-105.

The DCF refuses to run when terminal growth is not below WACC. The sensitivity grid
recomputes the value per share for WACC -1, 0 and +1 percentage points and terminal growth
-0.5, 0 and +0.5 points, keeping the projected cash flows; cells where growth reaches WACC
show "n/a". **Banks: not applicable**: deposits are a bank's raw material rather than its
financing, so free cash flow to the firm does not describe a bank.

## Bank ratios and valuation (`test_bank.py`)

| Metric | Formula |
|---|---|
| Net interest margin (NIM) | Net mark-up income / Average earning assets. If earning assets are not entered for both years: Net mark-up income / Average total assets, and the basis is stated with the result. |
| Cost to income | Operating expenses / (Net mark-up income + Non mark-up income) |
| Return on equity | Profit after tax / Total equity |
| Return on assets | Profit after tax / Total assets |
| Advances to deposits | Gross advances / Deposits |
| CASA share | CASA deposits / Deposits (only if CASA is disclosed and entered) |
| NPL ratio | Non-performing loans / Gross advances |
| Provision coverage | Provisions held against advances / Non-performing loans |
| Equity to assets | Total equity / Total assets |
| Capital adequacy ratio | As reported by the bank, entered with its page reference; not recomputed |
| Earnings per share | Profit after tax / Shares outstanding |
| Book value per share | Total equity / Shares outstanding |
| Price to book (P/B) | Share price / Book value per share, shown beside ROE |
| Price to earnings (P/E) | Share price / Earnings per share; not defined if EPS <= 0 |

The share price is an assumption entered for the analysis, with its source and date.

## Profit bridge (`test_bridge.py`)

What changed profit after tax from the prior year to the current year. The components are
defined from identities, so they **sum exactly** to the change in profit after tax:

Non-banks:
- Operating costs = (Revenue - Cost of sales) - Operating profit
- Other items = PAT - (Operating profit - Finance cost - Taxation)
- PAT = Revenue - Cost of sales - Operating costs - Finance cost - Taxation + Other items

Banks:
- Taxation = Profit before tax - Profit after tax
- Other items = PBT - (Net mark-up income + Non mark-up income - Operating expenses - Provisions)
- PAT = Net mark-up income + Non mark-up income - Operating expenses - Provisions + Other items - Taxation

Each component is the change in its term, with the sign it has in PAT. "Other items" holds
whatever the entered statement has between those lines (other income, associates); it is
zero when the profit chain is complete.

## Statement checks (`test_checks.py`)

| Check | Identity |
|---|---|
| Balance sheet | Total assets = Total liabilities + Total equity |
| Gross profit | Gross profit = Revenue - Cost of sales |
| Profit before tax | PBT = Operating profit - Finance cost |
| Profit after tax | PAT = PBT - Taxation |
| Cash flow | Operating + investing + financing cash flows = Cash - prior Cash |
| Bank: net mark-up income | Net mark-up income = earned - expensed |
| Bank: net advances | Net advances = Gross advances - Provisions held |
| Bank: profit before tax | PBT = Net mark-up income + Non mark-up income - Operating expenses - Provisions |

A check passes when the difference is at most one unit of the analysis's reporting unit,
because published statements are rounded to that unit. Checks are reported, not enforced.
The PBT check can legitimately fail when a statement has items between operating profit
and PBT (other income, share of associates); the difference shows how much.

## Flags and health score (`test_flags.py`)

The owner's threshold table (Settings) holds, per company type, a metric, a comparison
(`>=`, `>`, `<=`, `<`), a value (percentages as percentages) and a rationale. A computed
metric that does not meet its threshold is flagged. The health score is
`10 x thresholds met / thresholds evaluated`, shown with the number evaluated; a metric
that could not be computed is not evaluated, and with none evaluated there is no score.
ShaFin writes a starting set of thresholds, with their rationale, on first start; they are
the owner's to edit or delete.
