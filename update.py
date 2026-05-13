#!/usr/bin/env python3
"""
Investment Portfolio Dashboard Generator v2

Required packages:
    pip install yfinance requests

Usage:
    python update.py          → fetches latest prices, generates portfolio.html
    Double-click portfolio.html to open in browser.
"""

import json
import re
import sys
from datetime import datetime

# ─── Asset definitions ────────────────────────────────────────────────────────

US_BROKERS = ["Firstrade", "複委託"]

US_STOCKS = [
    {"symbol": "GOOGL", "name": "GOOGL"},
    {"symbol": "MSFT",  "name": "MSFT"},
    {"symbol": "NVDA",  "name": "NVDA"},
    {"symbol": "VTI",   "name": "VTI"},
    {"symbol": "CRCL",  "name": "CRCL"},
    {"symbol": "QQQ",   "name": "QQQ"},
]

TW_BROKERS = ["元大證券"]

TW_STOCKS = [
    {"symbol": "0050.TW",   "name": "元大台灣50 (0050)"},
    {"symbol": "006208.TW", "name": "富邦優質高息 (006208)"},
    {"symbol": "2330.TW",   "name": "台積電 (2330)"},
    {"symbol": "2886.TW",   "name": "兆豐金融 (2886)"},
]

FUNDS = [
    {"name": "元大基金"},
    {"name": "鉅亨基金"},
]

EXCHANGES = ["Binance", "OKX", "Bitget", "派網", "OKX WEB3.0", "Bitget Wallet", "Phantom"]

CRYPTO = [
    {"symbol": "BTC",   "coingecko_id": "bitcoin",            "note": ""},
    {"symbol": "ETH",   "coingecko_id": "ethereum",           "note": ""},
    {"symbol": "WBETH", "coingecko_id": "wrapped-beacon-eth", "note": ""},
    {"symbol": "BETH",  "coingecko_id": None,                 "note": "※以 ETH 價格替代"},
    {"symbol": "USDT",  "coingecko_id": "tether",             "note": ""},
    {"symbol": "USDC",  "coingecko_id": "usd-coin",           "note": ""},
    {"symbol": "BNB",   "coingecko_id": "binancecoin",        "note": ""},
    {"symbol": "SOL",   "coingecko_id": "solana",             "note": ""},
    {"symbol": "BNSOL", "coingecko_id": "binance-staked-sol", "note": ""},
]

BANKS = ["中信", "聯邦", "LINE BANK", "中華郵政", "元大", "永豐"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def idk(s):
    """Convert symbol to safe HTML ID key (same rule as JS idk())."""
    return re.sub(r'[^a-zA-Z0-9]', '_', s)

def fmt_price(price, currency):
    """Render a static price cell for Python-generated HTML."""
    if price is None:
        return '<span class="na">N/A</span>'
    if currency == "USD":
        if price >= 1000:
            return f'${price:,.2f}'
        elif price >= 1:
            return f'${price:.4f}'
        else:
            return f'${price:.6f}'
    elif currency == "TWD":
        return f'NT${price:,.2f}'
    return str(price)

def inp(id_, ls_key, w=82, ph="0"):
    """Return an HTML number input element string."""
    return (
        f'<input type="number" id="{id_}" data-ls="{ls_key}" '
        f'step="any" min="0" placeholder="{ph}" '
        f'style="width:{w}px" class="qi" oninput="onInput(this)">'
    )

# ─── Price fetching ───────────────────────────────────────────────────────────

def fetch_yf(symbol):
    """Fetch latest close price from Yahoo Finance. Returns float or None."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        p = getattr(t.fast_info, "last_price", None)
        return float(p) if p else None
    except Exception as e:
        print(f"  [warn] {symbol}: {e}")
        return None


def fetch_coingecko(coin_ids):
    """Fetch USD prices from CoinGecko free API. Returns {id: price}."""
    valid = [c for c in coin_ids if c]
    if not valid:
        return {}
    try:
        import requests
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(valid), "vs_currencies": "usd"},
            headers={"accept": "application/json", "User-Agent": "portfolio-tracker/2.0"},
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        return {cid: d[cid]["usd"] for cid in valid if cid in d}
    except Exception as e:
        print(f"  [warn] CoinGecko: {e}")
        return {}

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        import yfinance  # noqa
        import requests  # noqa
    except ImportError as e:
        print(f"Missing dependency: {e}\nPlease run: pip install yfinance requests")
        sys.exit(1)

    print("Fetching prices...")

    print("  US stocks...")
    for a in US_STOCKS:
        a["price"] = fetch_yf(a["symbol"])
        a["currency"] = "USD"

    print("  Taiwan stocks...")
    for a in TW_STOCKS:
        a["price"] = fetch_yf(a["symbol"])
        a["currency"] = "TWD"

    print("  Exchange rates...")
    twd_usd = fetch_yf("TWDUSD=X")
    jpy_usd = fetch_yf("JPYUSD=X")
    if twd_usd is None:
        twd_usd = 0.031
        print("  [warn] Using fallback TWD/USD = 0.031")
    if jpy_usd is None:
        jpy_usd = 0.0067
        print("  [warn] Using fallback JPY/USD = 0.0067")

    print("  Crypto (CoinGecko)...")
    cg_ids = [c["coingecko_id"] for c in CRYPTO if c["coingecko_id"]]
    cg = fetch_coingecko(cg_ids)
    eth_price = cg.get("ethereum")
    for a in CRYPTO:
        cid = a["coingecko_id"]
        a["price"] = eth_price if cid is None else cg.get(cid)
        a["currency"] = "USD"

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "update_time": update_time,
        "exchange_rates": {"TWDUSD": twd_usd, "JPYUSD": jpy_usd},
        "us_brokers":  US_BROKERS,
        "us_stocks":   US_STOCKS,
        "tw_brokers":  TW_BROKERS,
        "tw_stocks":   TW_STOCKS,
        "funds":       FUNDS,
        "exchanges":   EXCHANGES,
        "crypto":      CRYPTO,
        "banks":       BANKS,
    }

    html = build_html(data)
    with open("portfolio.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone! portfolio.html updated at {update_time}")
    print("Double-click portfolio.html to open in your browser.")

# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
  background: #eef2f7;
  color: #1a202c;
  padding: 20px 16px 60px;
  font-size: 14px;
}
.container { max-width: 1400px; margin: 0 auto; }

/* ── Page header ── */
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 24px; flex-wrap: wrap; gap: 10px;
}
.page-title { font-size: 1.5rem; font-weight: 800; color: #1a202c; }
.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.update-time { font-size: 0.78rem; color: #718096; background: white;
  padding: 4px 12px; border-radius: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.rates { font-size: 0.78rem; color: #4a5568; background: white;
  padding: 4px 12px; border-radius: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }

/* ── Section cards ── */
.card {
  background: white; border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.07);
  margin-bottom: 18px; overflow: hidden;
}
.card-hd {
  padding: 11px 20px; color: white; font-weight: 700; font-size: 0.95rem;
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
}
.card-hd.us     { background: linear-gradient(135deg,#1c3d6b,#2980b9); }
.card-hd.tw     { background: linear-gradient(135deg,#7b2020,#c0392b); }
.card-hd.funds  { background: linear-gradient(135deg,#4a1f8a,#7b52c8); }
.card-hd.crypto { background: linear-gradient(135deg,#1a4a2e,#27ae60); }
.card-hd.banks  { background: linear-gradient(135deg,#5a4010,#d4a017); }
.sub-badge {
  font-size: 0.82rem; background: rgba(255,255,255,0.18);
  padding: 3px 10px; border-radius: 10px; white-space: nowrap;
}

/* ── Tables ── */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
thead th {
  background: #f8fafc; padding: 7px 10px; text-align: right;
  font-size: 0.72rem; font-weight: 700; color: #718096;
  text-transform: uppercase; letter-spacing: 0.05em;
  border-bottom: 2px solid #e2e8f0; white-space: nowrap;
}
thead th:first-child, thead th.lft { text-align: left; }
thead th.broker-span { background: #edf2f7; color: #4a5568; text-align: center;
  border-bottom: 1px solid #e2e8f0; }
tbody td {
  padding: 8px 10px; text-align: right; border-bottom: 1px solid #f0f4f8;
  white-space: nowrap; vertical-align: middle;
}
tbody td:first-child { text-align: left; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: #f7fafd; }
tfoot td {
  padding: 8px 12px; font-weight: 700; color: #2b6cb0;
  background: #ebf8ff; border-top: 2px solid #bee3f8;
  text-align: right; white-space: nowrap;
}
tfoot td:first-child { text-align: left; }

/* ── Asset names ── */
.aname { font-weight: 600; color: #1a202c; }
.anote { font-size: 0.68rem; color: #a0aec0; display: block; margin-top: 1px; }
.na { color: #e53e3e; font-style: italic; }

/* ── Inputs ── */
.qi {
  padding: 4px 7px; border: 1.5px solid #e2e8f0; border-radius: 6px;
  text-align: right; font-size: 0.82rem; color: #2d3748; background: #fafafa;
  transition: border-color 0.12s, box-shadow 0.12s;
  -moz-appearance: textfield;
}
.qi::-webkit-inner-spin-button, .qi::-webkit-outer-spin-button { -webkit-appearance: none; }
.qi:focus { outline: none; border-color: #4299e1; background: white;
  box-shadow: 0 0 0 3px rgba(66,153,225,0.15); }
.qi.hv { border-color: #90cdf4; background: #ebf8ff; }
.cost-inp { border-color: #d6bcfa; background: #faf5ff; }
.cost-inp.hv { border-color: #b794f4; background: #faf5ff; }
.cost-inp:focus { border-color: #805ad5; box-shadow: 0 0 0 3px rgba(128,90,213,0.15); }

/* ── Value / P&L cells ── */
.val { font-family: 'SFMono-Regular', Consolas, monospace; color: #2d3748; }
.twd { font-family: 'SFMono-Regular', Consolas, monospace; color: #2d3748; }
.pnl-pos { color: #276749; font-weight: 700; }
.pnl-neg { color: #c53030; font-weight: 700; }
.price-col { font-family: 'SFMono-Regular', Consolas, monospace; color: #4a5568; }
.totqty { font-family: 'SFMono-Regular', Consolas, monospace; color: #1a202c; font-weight: 600; }

/* ── Grand total bar ── */
.grand-bar {
  background: linear-gradient(135deg,#1a202c,#2d3748); border-radius: 12px;
  padding: 20px 28px; display: flex; justify-content: space-between; align-items: center;
  box-shadow: 0 4px 20px rgba(0,0,0,0.18); flex-wrap: wrap; gap: 16px;
}
.grand-sections { display: flex; gap: 28px; flex-wrap: wrap; align-items: center; }
.grand-item { text-align: center; }
.grand-item-label { font-size: 0.72rem; color: #a0aec0; margin-bottom: 2px; }
.grand-item-val { font-size: 0.92rem; font-weight: 700; color: #e2e8f0;
  font-family: 'SFMono-Regular', Consolas, monospace; }
.grand-divider { width: 1px; height: 36px; background: rgba(255,255,255,0.15); }
.grand-total-block { text-align: right; }
.grand-total-label { font-size: 0.82rem; color: #a0aec0; margin-bottom: 4px; }
.grand-total-val { font-size: 1.8rem; font-weight: 800; color: #68d391;
  font-family: 'SFMono-Regular', Consolas, monospace; }
"""

# ─── JS ───────────────────────────────────────────────────────────────────────

JS = r"""
// ── Same idk() as Python side ────────────────────────────────────────────────
function idk(s) { return s.replace(/[^a-zA-Z0-9]/g, '_'); }

// ── localStorage ─────────────────────────────────────────────────────────────
var LS = 'pf2_';
function lsGet(key) {
  var v = localStorage.getItem(LS + key);
  return v !== null ? parseFloat(v) : 0;
}
function lsSave(el) {
  var key = el.dataset.ls;
  if (!key) return;
  var v = parseFloat(el.value);
  if (isNaN(v) || v <= 0) localStorage.removeItem(LS + key);
  else localStorage.setItem(LS + key, String(v));
}
function restore() {
  document.querySelectorAll('input[data-ls]').forEach(function(el) {
    var v = lsGet(el.dataset.ls);
    if (v > 0) { el.value = v; el.classList.add('hv'); }
  });
}
function onInput(el) {
  lsSave(el);
  var v = parseFloat(el.value);
  if (v > 0) el.classList.add('hv');
  else el.classList.remove('hv');
  calc();
}

// ── Formatting ───────────────────────────────────────────────────────────────
function setEl(id, html) {
  var el = document.getElementById(id);
  if (el) el.innerHTML = html;
}
function fn(v, d) {
  return v.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
}
function fUSD(v) { return v === 0 ? '-' : '$ ' + fn(v, 2); }
function fTWD(v) { return v === 0 ? '-' : 'NT$ ' + fn(Math.round(v), 0); }
function fQty(v) {
  if (v === 0) return '-';
  if (v % 1 === 0) return v.toLocaleString('en-US');
  return parseFloat(v.toPrecision(8)).toLocaleString('en-US', {maximumSignificantDigits: 8});
}
function fPnl(pct) {
  var cls = pct >= 0 ? 'pnl-pos' : 'pnl-neg';
  var sign = pct >= 0 ? '+' : '';
  return '<span class="' + cls + '">' + sign + fn(pct, 2) + '%</span>';
}
function naSpan() { return '<span class="na">N/A</span>'; }
function fBadge(v_twd) {
  return 'NT$ ' + fn(Math.round(v_twd), 0);
}

// ── Main calculation ─────────────────────────────────────────────────────────
function calc() {
  var r = DATA.exchange_rates;
  var usdToTwd = 1 / r.TWDUSD;        // 1 USD → TWD
  var jpyToTwd = r.JPYUSD / r.TWDUSD; // 1 JPY → TWD

  var subUsTwd = 0, subTwTwd = 0, subFundsTwd = 0, subCryptoTwd = 0, subCashTwd = 0;

  // ── US Stocks ──────────────────────────────────────────────────────────────
  DATA.us_stocks.forEach(function(s) {
    var k = idk(s.symbol);
    var price = s.price; // USD
    var totalQty = 0, totalUSD = 0;

    DATA.us_brokers.forEach(function(_, bi) {
      var qty = lsGet('sq_' + k + '_' + bi);
      totalQty += qty;
      var v = (price !== null && qty > 0) ? price * qty : null;
      setEl('sv_' + k + '_' + bi, v !== null ? fUSD(v) : (qty > 0 ? naSpan() : '-'));
      if (v !== null) totalUSD += v;
    });

    setEl('sv_' + k + '_tot', totalUSD > 0 ? fUSD(totalUSD) : '-');

    var cost = lsGet('sc_' + k);
    if (price !== null && cost > 0) {
      setEl('spl_' + k, fPnl((price - cost) / cost * 100));
    } else {
      setEl('spl_' + k, '-');
    }

    subUsTwd += totalUSD * usdToTwd;
  });
  setEl('sub_us',   fBadge(subUsTwd));
  setEl('sub_us_f', fBadge(subUsTwd));

  // ── TW Stocks ──────────────────────────────────────────────────────────────
  DATA.tw_stocks.forEach(function(s) {
    var k = idk(s.symbol);
    var price = s.price; // TWD
    var totalQty = 0, totalTWD = 0;

    DATA.tw_brokers.forEach(function(_, bi) {
      var qty = lsGet('tq_' + k + '_' + bi);
      totalQty += qty;
      var v = (price !== null && qty > 0) ? price * qty : null;
      setEl('tv_' + k + '_' + bi, v !== null ? fTWD(v) : (qty > 0 ? naSpan() : '-'));
      if (v !== null) totalTWD += v;
    });

    setEl('tv_' + k + '_tot', totalTWD > 0 ? fTWD(totalTWD) : '-');

    var cost = lsGet('tc_' + k);
    if (price !== null && cost > 0) {
      setEl('tpl_' + k, fPnl((price - cost) / cost * 100));
    } else {
      setEl('tpl_' + k, '-');
    }

    subTwTwd += totalTWD;
  });
  setEl('sub_tw',   fBadge(subTwTwd));
  setEl('sub_tw_f', fBadge(subTwTwd));

  // ── Funds ──────────────────────────────────────────────────────────────────
  DATA.funds.forEach(function(_, fi) {
    subFundsTwd += lsGet('fv_' + fi);
  });
  setEl('sub_funds',   fBadge(subFundsTwd));
  setEl('sub_funds_f', fBadge(subFundsTwd));

  // ── Crypto ─────────────────────────────────────────────────────────────────
  DATA.crypto.forEach(function(c) {
    var sym = c.symbol;
    var price = c.price; // USD
    var totalQty = 0;

    DATA.exchanges.forEach(function(_, ei) {
      totalQty += lsGet('cq_' + sym + '_' + ei);
    });

    setEl('ctq_' + sym, totalQty > 0 ? fQty(totalQty) : '-');

    var totalUSD = (price !== null && totalQty > 0) ? price * totalQty : null;
    setEl('ctv_' + sym, totalUSD !== null ? fUSD(totalUSD) : (totalQty > 0 ? naSpan() : '-'));

    var cost = lsGet('cc_' + sym);
    if (price !== null && cost > 0) {
      setEl('cpl_' + sym, fPnl((price - cost) / cost * 100));
    } else {
      setEl('cpl_' + sym, '-');
    }

    if (totalUSD !== null) subCryptoTwd += totalUSD * usdToTwd;
  });
  setEl('sub_crypto',   fBadge(subCryptoTwd));
  setEl('sub_crypto_f', fBadge(subCryptoTwd));

  // ── Banks ──────────────────────────────────────────────────────────────────
  var bankTwd = 0;
  DATA.banks.forEach(function(_, bi) {
    var act = lsGet('bd_' + bi + '_0');
    var dep = lsGet('bd_' + bi + '_1');
    var sub = act + dep;
    setEl('bs_' + bi, sub > 0 ? fTWD(sub) : '-');
    bankTwd += sub;
  });

  // ── Foreign currency ───────────────────────────────────────────────────────
  var usdAmt = lsGet('fx_USD');
  var jpyAmt = lsGet('fx_JPY');
  var usdTwd = usdAmt * usdToTwd;
  var jpyTwd = jpyAmt * jpyToTwd;
  setEl('fxt_USD', usdTwd > 0 ? fTWD(usdTwd) : '-');
  setEl('fxt_JPY', jpyTwd > 0 ? fTWD(jpyTwd) : '-');

  subCashTwd = bankTwd + usdTwd + jpyTwd;
  setEl('sub_banks',   fBadge(subCashTwd));
  setEl('sub_banks_f', fBadge(subCashTwd));

  // ── Grand total ────────────────────────────────────────────────────────────
  var grand = subUsTwd + subTwTwd + subFundsTwd + subCryptoTwd + subCashTwd;

  setEl('bar_us',     fTWD(subUsTwd));
  setEl('bar_tw',     fTWD(subTwTwd));
  setEl('bar_funds',  fTWD(subFundsTwd));
  setEl('bar_crypto', fTWD(subCryptoTwd));
  setEl('bar_cash',   fTWD(subCashTwd));
  setEl('grand_total', 'NT$ ' + fn(Math.round(grand), 0));
}

document.addEventListener('DOMContentLoaded', function() {
  restore();
  calc();
});
"""

# ─── HTML builders ────────────────────────────────────────────────────────────

def build_header_html(data):
    r = data["exchange_rates"]
    usd_twd = 1 / r["TWDUSD"]
    jpy_twd = r["JPYUSD"] / r["TWDUSD"]
    return (
        '<div class="page-header">'
        '<div class="page-title">&#x1F4CA; 投資記帳面板</div>'
        '<div class="header-right">'
        f'<div class="update-time">&#x1F559; 最後更新：{data["update_time"]}</div>'
        f'<div class="rates">1 USD = {usd_twd:.2f} TWD &nbsp;|&nbsp; 1 JPY = {jpy_twd:.4f} TWD</div>'
        '</div>'
        '</div>\n'
    )


def build_us_section(data):
    brokers = data["us_brokers"]
    stocks  = data["us_stocks"]

    # thead: row 1 has broker group headers + fixed cols; row 2 has qty/val per broker
    th_row1 = '<tr>'
    th_row1 += '<th class="lft" rowspan="2">標的</th>'
    for br in brokers:
        th_row1 += f'<th class="broker-span" colspan="2">{br}</th>'
    th_row1 += '<th rowspan="2">合計 (USD)</th>'
    th_row1 += '<th rowspan="2">現價 (USD)</th>'
    th_row1 += '<th rowspan="2">成本 (USD)</th>'
    th_row1 += '<th rowspan="2">損益</th>'
    th_row1 += '</tr>'

    th_row2 = '<tr>'
    for _ in brokers:
        th_row2 += '<th>數量</th><th>總值</th>'
    th_row2 += '</tr>'

    thead = '<thead>' + th_row1 + th_row2 + '</thead>'

    rows = ''
    for s in stocks:
        sym = s['symbol']
        k   = idk(sym)
        price_html = fmt_price(s['price'], 'USD')
        note_html  = ''

        row = f'<tr><td class="aname">{sym}{note_html}</td>'
        for bi in range(len(brokers)):
            row += f'<td>{inp(f"sq_{k}_{bi}", f"sq_{k}_{bi}", w=78)}</td>'
            row += f'<td class="val" id="sv_{k}_{bi}">-</td>'
        row += f'<td class="val" id="sv_{k}_tot">-</td>'
        row += f'<td class="price-col">{price_html}</td>'
        row += f'<td>{inp(f"sc_{k}", f"sc_{k}", w=82, ph="成本")}</td>'
        row += f'<td id="spl_{k}">-</td>'
        row += '</tr>\n'
        rows += row

    # cols: name(1) + brokers×2 + total(1) + price(1) + cost(1) + pnl(1)
    n_fixed_cols = 3 + len(brokers) * 2
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_fixed_cols}" style="text-align:right">美股小計（TWD）</td>'
        f'<td colspan="2"><strong id="sub_us_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = thead + '<tbody>' + rows + '</tbody>' + tfoot
    return (
        '<div class="card">'
        '<div class="card-hd us">'
        '<span>&#x1F1FA;&#x1F1F8; 美股</span>'
        '<span class="sub-badge" id="sub_us">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        '</div>\n'
    )


def build_tw_section(data):
    brokers = data["tw_brokers"]
    stocks  = data["tw_stocks"]

    th_row1 = '<tr>'
    th_row1 += '<th class="lft" rowspan="2">標的</th>'
    for br in brokers:
        th_row1 += f'<th class="broker-span" colspan="2">{br}</th>'
    th_row1 += '<th rowspan="2">合計 (TWD)</th>'
    th_row1 += '<th rowspan="2">現價 (TWD)</th>'
    th_row1 += '<th rowspan="2">成本 (TWD)</th>'
    th_row1 += '<th rowspan="2">損益</th>'
    th_row1 += '</tr>'

    th_row2 = '<tr>'
    for _ in brokers:
        th_row2 += '<th>數量</th><th>總值</th>'
    th_row2 += '</tr>'

    thead = '<thead>' + th_row1 + th_row2 + '</thead>'

    rows = ''
    for s in stocks:
        sym = s['symbol']
        k   = idk(sym)
        price_html = fmt_price(s['price'], 'TWD')

        row = f'<tr><td class="aname">{s["name"]}</td>'
        for bi in range(len(brokers)):
            row += f'<td>{inp(f"tq_{k}_{bi}", f"tq_{k}_{bi}", w=78)}</td>'
            row += f'<td class="twd" id="tv_{k}_{bi}">-</td>'
        row += f'<td class="twd" id="tv_{k}_tot">-</td>'
        row += f'<td class="price-col">{price_html}</td>'
        row += f'<td>{inp(f"tc_{k}", f"tc_{k}", w=82, ph="成本")}</td>'
        row += f'<td id="tpl_{k}">-</td>'
        row += '</tr>\n'
        rows += row

    n_fixed_cols = 3 + len(brokers) * 2
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_fixed_cols}" style="text-align:right">台股小計（TWD）</td>'
        f'<td colspan="2"><strong id="sub_tw_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = thead + '<tbody>' + rows + '</tbody>' + tfoot
    return (
        '<div class="card">'
        '<div class="card-hd tw">'
        '<span>&#x1F1F9;&#x1F1FC; 台股</span>'
        '<span class="sub-badge" id="sub_tw">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        '</div>\n'
    )


def build_funds_section(data):
    funds = data["funds"]

    thead = (
        '<thead><tr>'
        '<th class="lft">基金名稱</th>'
        '<th>現值 (TWD)</th>'
        '</tr></thead>'
    )

    rows = ''
    for fi, f in enumerate(funds):
        rows += (
            f'<tr>'
            f'<td class="aname">{f["name"]}</td>'
            f'<td>{inp(f"fv_{fi}", f"fv_{fi}", w=140, ph="NT$ 金額")}</td>'
            f'</tr>\n'
        )

    tfoot = (
        '<tfoot><tr>'
        '<td style="text-align:right">基金小計（TWD）</td>'
        '<td><strong id="sub_funds_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = thead + '<tbody>' + rows + '</tbody>' + tfoot
    return (
        '<div class="card">'
        '<div class="card-hd funds">'
        '<span>&#x1F4C8; 基金</span>'
        '<span class="sub-badge" id="sub_funds">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        '</div>\n'
    )


def build_crypto_section(data):
    exchanges = data["exchanges"]
    crypto    = data["crypto"]

    # thead: single row
    thead = '<thead><tr>'
    thead += '<th class="lft">幣種</th>'
    for ex in exchanges:
        thead += f'<th>{ex}</th>'
    thead += '<th>總數量</th>'
    thead += '<th>現價 (USD)</th>'
    thead += '<th>成本 (USD)</th>'
    thead += '<th>總值 (USD)</th>'
    thead += '<th>盈虧</th>'
    thead += '</tr></thead>'

    rows = ''
    for c in crypto:
        sym        = c['symbol']
        price_html = fmt_price(c['price'], 'USD')
        note_html  = f'<span class="anote">{c["note"]}</span>' if c.get('note') else ''

        row = f'<tr><td class="aname">{sym}{note_html}</td>'
        for ei in range(len(exchanges)):
            row += f'<td>{inp(f"cq_{sym}_{ei}", f"cq_{sym}_{ei}", w=68)}</td>'
        row += f'<td class="totqty" id="ctq_{sym}">-</td>'
        row += f'<td class="price-col">{price_html}</td>'
        row += f'<td>{inp(f"cc_{sym}", f"cc_{sym}", w=82, ph="成本")}</td>'
        row += f'<td class="val" id="ctv_{sym}">-</td>'
        row += f'<td id="cpl_{sym}">-</td>'
        row += '</tr>\n'
        rows += row

    # cols: name(1) + exchanges + total_qty(1) + price(1) + cost(1) + value(1) + pnl(1)
    # label spans all except last 2 (value + pnl)
    n_cols = 1 + len(exchanges) + 3  # name + exchanges + total_qty + price + cost
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_cols}" style="text-align:right">加密貨幣小計（TWD）</td>'
        f'<td colspan="2"><strong id="sub_crypto_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = thead + '<tbody>' + rows + '</tbody>' + tfoot
    return (
        '<div class="card">'
        '<div class="card-hd crypto">'
        '<span>&#x20BF; 加密貨幣</span>'
        '<span class="sub-badge" id="sub_crypto">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        '</div>\n'
    )


def build_cash_section(data):
    banks = data["banks"]
    r     = data["exchange_rates"]
    usd_twd = 1 / r["TWDUSD"]
    jpy_twd = r["JPYUSD"] / r["TWDUSD"]

    # ── Bank deposits ──
    bank_thead = (
        '<thead><tr>'
        '<th class="lft">銀行</th>'
        '<th>活存 (TWD)</th>'
        '<th>定存 (TWD)</th>'
        '<th>小計 (TWD)</th>'
        '</tr></thead>'
    )
    bank_rows = ''
    for bi, bank in enumerate(banks):
        bank_rows += (
            f'<tr>'
            f'<td class="aname">{bank}</td>'
            f'<td>{inp(f"bd_{bi}_0", f"bd_{bi}_0", w=120, ph="活存")}</td>'
            f'<td>{inp(f"bd_{bi}_1", f"bd_{bi}_1", w=120, ph="定存")}</td>'
            f'<td class="twd" id="bs_{bi}">-</td>'
            f'</tr>\n'
        )

    # ── Foreign currency ──
    fx_thead = (
        '<thead><tr>'
        '<th class="lft">外幣</th>'
        '<th>金額</th>'
        f'<th>匯率 (→ TWD)</th>'
        '<th>折合 TWD</th>'
        '</tr></thead>'
    )
    fx_rows = (
        f'<tr>'
        f'<td class="aname">美金 (USD)</td>'
        f'<td>{inp("fx_USD", "fx_USD", w=120, ph="USD 金額")}</td>'
        f'<td class="price-col">1 USD = {usd_twd:.2f} TWD</td>'
        f'<td class="twd" id="fxt_USD">-</td>'
        f'</tr>\n'
        f'<tr>'
        f'<td class="aname">日幣 (JPY)</td>'
        f'<td>{inp("fx_JPY", "fx_JPY", w=120, ph="JPY 金額")}</td>'
        f'<td class="price-col">1 JPY = {jpy_twd:.4f} TWD</td>'
        f'<td class="twd" id="fxt_JPY">-</td>'
        f'</tr>\n'
    )

    tfoot = (
        '<tfoot><tr>'
        '<td colspan="3" style="text-align:right">資金小計（TWD）</td>'
        '<td><strong id="sub_banks_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = (
        bank_thead +
        '<tbody>' + bank_rows + '</tbody>'
        + '<tbody style="border-top:3px solid #e2e8f0">'
        + '<tr><td colspan="4" style="padding:6px 10px;background:#f8fafc;'
        + 'font-size:0.72rem;font-weight:700;color:#718096;'
        + 'text-transform:uppercase;letter-spacing:.05em">外幣</td></tr>'
        + fx_rows
        + '</tbody>'
        + tfoot
    )

    return (
        '<div class="card">'
        '<div class="card-hd banks">'
        '<span>&#x1F4B5; 資金</span>'
        '<span class="sub-badge" id="sub_banks">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        '</div>\n'
    )


def build_grand_html():
    return (
        '<div class="grand-bar">'
        '<div class="grand-sections">'

        '<div class="grand-item">'
        '<div class="grand-item-label">美股</div>'
        '<div class="grand-item-val" id="bar_us">NT$ 0</div>'
        '</div>'

        '<div class="grand-divider"></div>'

        '<div class="grand-item">'
        '<div class="grand-item-label">台股</div>'
        '<div class="grand-item-val" id="bar_tw">NT$ 0</div>'
        '</div>'

        '<div class="grand-divider"></div>'

        '<div class="grand-item">'
        '<div class="grand-item-label">基金</div>'
        '<div class="grand-item-val" id="bar_funds">NT$ 0</div>'
        '</div>'

        '<div class="grand-divider"></div>'

        '<div class="grand-item">'
        '<div class="grand-item-label">加密貨幣</div>'
        '<div class="grand-item-val" id="bar_crypto">NT$ 0</div>'
        '</div>'

        '<div class="grand-divider"></div>'

        '<div class="grand-item">'
        '<div class="grand-item-label">資金</div>'
        '<div class="grand-item-val" id="bar_cash">NT$ 0</div>'
        '</div>'

        '</div>'

        '<div class="grand-total-block">'
        '<div class="grand-total-label">&#x1F4B0; 總資產（TWD）</div>'
        '<div class="grand-total-val" id="grand_total">NT$ 0</div>'
        '</div>'
        '</div>\n'
    )


def build_html(data):
    prices_json = json.dumps(data, ensure_ascii=False, indent=2)

    body = (
        build_header_html(data)
        + build_us_section(data)
        + build_tw_section(data)
        + build_funds_section(data)
        + build_crypto_section(data)
        + build_cash_section(data)
        + build_grand_html()
    )

    return (
        '<!DOCTYPE html>\n<html lang="zh-TW">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>投資記帳面板</title>\n'
        '<style>\n' + CSS + '\n</style>\n'
        '</head>\n<body>\n'
        '<div class="container">\n' + body + '</div>\n'
        '<script>\nconst DATA = ' + prices_json + ';\n' + JS + '\n</script>\n'
        '</body>\n</html>\n'
    )


if __name__ == "__main__":
    main()
