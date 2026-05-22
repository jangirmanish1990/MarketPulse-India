"""FY25 evaluation dataset — 12 real Indian quarterly results."""

from __future__ import annotations

DATASET_NAME = "marketpulse-india-fy25"

EVAL_EXAMPLES: list[dict] = [
    {
        "nse_symbol": "INFY",
        "sector": "IT",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Infosys Q4 FY25 Results: Revenue Rs 40925 crore, up 7.9 percent YoY. "
            "Net Profit Rs 7973 crore, up 11.7 percent YoY. EBIT margin 21.1 percent. "
            "FY26 revenue guidance 0-3 percent in USD terms. Final dividend Rs 22 per share."
        ),
        "expected_revenue_cr": 40925.0,
        "expected_pat_cr": 7973.0,
        "nifty_1w_change_pct": 1.2,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "TCS",
        "sector": "IT",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "TCS Q4 FY25 Results: Revenue Rs 63437 crore, up 5.3 percent YoY. "
            "Net Profit Rs 12224 crore, up 4.5 percent YoY. EBIT margin 24.5 percent. "
            "Final dividend Rs 30 per share plus special dividend Rs 66 per share."
        ),
        "expected_revenue_cr": 63437.0,
        "expected_pat_cr": 12224.0,
        "nifty_1w_change_pct": 1.2,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "HDFCBANK",
        "sector": "Banking",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "HDFC Bank Q4 FY25 Results: Net Interest Income Rs 32070 crore, up 10.3 percent YoY. "
            "Net Profit Rs 17616 crore, up 6.7 percent YoY. Gross NPA 1.33 percent, "
            "Net NPA 0.43 percent. CASA ratio 34.1 percent."
        ),
        "expected_revenue_cr": 32070.0,
        "expected_pat_cr": 17616.0,
        "nifty_1w_change_pct": 2.5,
        "expected_signal": "BUY",
    },
    {
        "nse_symbol": "RELIANCE",
        "sector": "Conglomerate",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Reliance Industries Q4 FY25 Results: Revenue Rs 263789 crore, up 8.8 percent YoY. "
            "Net Profit Rs 19407 crore, up 6.4 percent YoY. Jio ARPU Rs 206.2. "
            "Retail revenue Rs 93750 crore. Dividend Rs 5.50 per share."
        ),
        "expected_revenue_cr": 263789.0,
        "expected_pat_cr": 19407.0,
        "nifty_1w_change_pct": 0.3,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "WIPRO",
        "sector": "IT",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Wipro Q4 FY25 Results: IT Services Revenue USD 2635 million, down 1.2 percent YoY. "
            "Net Profit Rs 3570 crore, up 26 percent YoY. EBIT margin 17.5 percent. "
            "Q1 FY26 revenue guidance USD 2645-2697 million. Dividend Rs 6 per share."
        ),
        "expected_revenue_cr": 21962.0,
        "expected_pat_cr": 3570.0,
        "nifty_1w_change_pct": -3.1,
        "expected_signal": "SELL",
    },
    {
        "nse_symbol": "BAJFINANCE",
        "sector": "NBFC",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Bajaj Finance Q4 FY25 Results: Net Interest Income Rs 9802 crore, up 22 percent YoY. "
            "Net Profit Rs 4546 crore, up 19 percent YoY. AUM Rs 415000 crore. "
            "Gross NPA 1.09 percent, Net NPA 0.46 percent. New loans booked 12.7 million."
        ),
        "expected_revenue_cr": 9802.0,
        "expected_pat_cr": 4546.0,
        "nifty_1w_change_pct": 3.8,
        "expected_signal": "BUY",
    },
    {
        "nse_symbol": "TITAN",
        "sector": "Consumer",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Titan Company Q4 FY25 Results: Revenue Rs 13596 crore, up 25.1 percent YoY. "
            "Net Profit Rs 770 crore, up 4.1 percent YoY. Jewellery EBIT margin 10.8 percent. "
            "Watches segment revenue Rs 1043 crore. Added 61 new Tanishq stores."
        ),
        "expected_revenue_cr": 13596.0,
        "expected_pat_cr": 770.0,
        "nifty_1w_change_pct": 1.5,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "NESTLEIND",
        "sector": "FMCG",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Nestle India Q1 CY2025 Results: Revenue Rs 5405 crore, up 2.9 percent YoY. "
            "Net Profit Rs 933 crore, up 7.4 percent YoY. EBITDA margin 24.2 percent. "
            "Volume growth 2.5 percent domestic. Interim dividend Rs 8.50 per share."
        ),
        "expected_revenue_cr": 5405.0,
        "expected_pat_cr": 933.0,
        "nifty_1w_change_pct": -0.5,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "SUNPHARMA",
        "sector": "Pharma",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Sun Pharmaceutical Q4 FY25 Results: Revenue Rs 14201 crore, up 9.5 percent YoY. "
            "Net Profit Rs 2975 crore, up 12.2 percent YoY. US specialty revenue USD 363 million. "
            "India formulations revenue Rs 4870 crore, up 14.3 percent. R and D spend 7.2 percent of sales."
        ),
        "expected_revenue_cr": 14201.0,
        "expected_pat_cr": 2975.0,
        "nifty_1w_change_pct": 2.1,
        "expected_signal": "BUY",
    },
    {
        "nse_symbol": "AXISBANK",
        "sector": "Banking",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Axis Bank Q4 FY25 Results: Net Interest Income Rs 13811 crore, up 5.6 percent YoY. "
            "Net Profit Rs 7118 crore, up 5.2 percent YoY. Gross NPA 1.28 percent. "
            "Net NPA 0.33 percent. CASA ratio 42.7 percent. Capital adequacy 16.65 percent."
        ),
        "expected_revenue_cr": 13811.0,
        "expected_pat_cr": 7118.0,
        "nifty_1w_change_pct": 2.5,
        "expected_signal": "BUY",
    },
    {
        "nse_symbol": "HCLTECH",
        "sector": "IT",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "HCL Technologies Q4 FY25 Results: Revenue Rs 30246 crore, up 7.7 percent YoY. "
            "Net Profit Rs 4307 crore, up 11.1 percent YoY. EBIT margin 18.1 percent. "
            "FY26 revenue guidance 4.5-6.5 percent in constant currency. Dividend Rs 18 per share."
        ),
        "expected_revenue_cr": 30246.0,
        "expected_pat_cr": 4307.0,
        "nifty_1w_change_pct": 0.8,
        "expected_signal": "HOLD",
    },
    {
        "nse_symbol": "KOTAKBANK",
        "sector": "Banking",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Kotak Mahindra Bank Q4 FY25 Results: Net Interest Income Rs 7284 crore, up 3.1 percent YoY. "
            "Net Profit Rs 3552 crore, down 14 percent YoY due to one-time items. "
            "Gross NPA 1.42 percent. NIM 4.97 percent. Customer assets grew 15 percent YoY."
        ),
        "expected_revenue_cr": 7284.0,
        "expected_pat_cr": 3552.0,
        "nifty_1w_change_pct": -3.5,
        "expected_signal": "SELL",
    },
]
