#!/usr/bin/env python3
"""
Investment Portfolio Dashboard Generator v2

Required packages:
    pip install yfinance requests

Usage:
    python update.py          → fetches latest prices, generates portfolio.html
    Double-click portfolio.html to open in browser.

Custom symbols:
    Add symbols via the browser UI, then download custom_symbols.json.
    Place it next to update.py and rerun to fetch prices.
"""

import json
import os
import re
import sys
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────

CUSTOM_FILE = "custom_symbols.json"
CACHE_FILE  = "price_cache.json"

# ─── Default asset definitions ───────────────────────────────────────────────

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

# symbols whose coingecko_id is intentionally None (use ETH price)
_CRYPTO_ETH_PROXY = {"BETH"}

BANKS = ["中信", "聯邦", "LINE BANK", "中華郵政", "元大", "永豐"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def idk(s):
    """Convert symbol to safe HTML ID key (same rule as JS idk())."""
    return re.sub(r'[^a-zA-Z0-9]', '_', s)

def fmt_price(price, currency, cache_time=None):
    """Render a static price string for Python-generated HTML.

    When cache_time is provided the value came from the price cache and a grey
    date annotation is appended below the price.
    """
    if price is None:
        return '<span class="na">N/A</span>'
    if currency == "USD":
        if price >= 1000: s = f'${price:,.2f}'
        elif price >= 1:  s = f'${price:.4f}'
        else:             s = f'${price:.6f}'
    elif currency == "TWD":
        s = f'NT${price:,.2f}'
    else:
        s = str(price)
    if cache_time:
        s += f'<span class="cache-note">快取 {cache_time[:10]}</span>'
    return s

def inp(id_, ls_key, w=82, ph="0"):
    """Return an HTML number input element string."""
    return (
        f'<input type="number" id="{id_}" data-ls="{ls_key}" '
        f'step="any" min="0" placeholder="{ph}" '
        f'style="width:{w}px" class="qi" oninput="onInput(this)">'
    )

def cost_inp(id_, ls_key, w=82):
    return (
        f'<input type="number" id="{id_}" data-ls="{ls_key}" '
        f'step="any" min="0" placeholder="成本" '
        f'style="width:{w}px" class="qi cost-inp" oninput="onInput(this)">'
    )

# ─── Price fetching ───────────────────────────────────────────────────────────

def fetch_yf(symbol, max_retries=3, delay=2):
    """Fetch latest close price from Yahoo Finance, retrying up to max_retries times.

    Returns float on success, None on all-retry failure.
    """
    import math, time
    for attempt in range(max_retries):
        try:
            import yfinance as yf
            t = yf.Ticker(symbol)
            hist = t.history(period="5d")
            if not hist.empty:
                v = float(hist["Close"].iloc[-1])
                return None if math.isnan(v) else v
            p = getattr(t.fast_info, "last_price", None)
            if p is None:
                return None
            v = float(p)
            return None if math.isnan(v) else v
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [retry {attempt + 1}/{max_retries - 1}] {symbol}: {e}")
                time.sleep(delay)
            else:
                print(f"  [warn] {symbol}: {e}")
    return None


def fetch_yf_fallback(symbols):
    """Try each symbol in order (each with full retry logic).

    Returns (price, symbol_used) for the first success, or (None, None).
    """
    for sym in symbols:
        price = fetch_yf(sym)
        if price is not None:
            return price, sym
    return None, None


def read_price_cache():
    """Read price_cache.json. Returns {symbol: {"price": float, "time": str}}."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [warn] Reading {CACHE_FILE}: {e}")
        return {}


def save_price_cache(cache):
    """Write price_cache.json."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [warn] Saving {CACHE_FILE}: {e}")


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


def find_coingecko_id(symbol):
    """Search CoinGecko for the coin ID matching a symbol. Returns id or None."""
    try:
        import requests
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": symbol},
            headers={"accept": "application/json", "User-Agent": "portfolio-tracker/2.0"},
            timeout=10,
        )
        r.raise_for_status()
        coins = r.json().get("coins", [])
        sym_u = symbol.upper()
        for coin in coins:
            if coin.get("symbol", "").upper() == sym_u:
                return coin.get("id")
        return coins[0].get("id") if coins else None
    except Exception as e:
        print(f"  [warn] CoinGecko search {symbol}: {e}")
        return None

# ─── Custom symbols (file-based bridge between browser and update.py) ─────────

def read_custom_symbols():
    """Read custom_symbols.json; return {us_stocks, tw_stocks, crypto} as string lists.

    Expected format:
        {"us_stocks": ["GEV", "AAPL"], "tw_stocks": ["00878"], "crypto": ["DOGE"]}
    TW symbols should NOT have .TW suffix in the file (update.py adds it).
    """
    if not os.path.exists(CUSTOM_FILE):
        return {"us_stocks": [], "tw_stocks": [], "crypto": []}
    try:
        with open(CUSTOM_FILE, encoding="utf-8") as f:
            d = json.load(f)
        def to_syms(lst):
            # Accept plain strings ["SYM"] or legacy dicts [{"symbol": "SYM"}]
            result = []
            for item in lst:
                if isinstance(item, str):
                    result.append(item.strip().upper())
                elif isinstance(item, dict) and item.get("symbol"):
                    result.append(item["symbol"].strip().upper())
            return [s for s in result if s]
        return {
            "us_stocks": to_syms(d.get("us_stocks", [])),
            "tw_stocks": to_syms(d.get("tw_stocks", [])),
            "crypto":    to_syms(d.get("crypto", [])),
        }
    except Exception as e:
        print(f"  [warn] Reading {CUSTOM_FILE}: {e}")
        return {"us_stocks": [], "tw_stocks": [], "crypto": []}

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        import yfinance  # noqa
        import requests  # noqa
    except ImportError as e:
        print(f"Missing dependency: {e}\nPlease run: pip install yfinance requests")
        sys.exit(1)

    print("Fetching prices...")
    price_cache = read_price_cache()
    fetch_time  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def apply_cache(assets, key_fn):
        """For assets with price=None, fill from cache; set cache_time accordingly."""
        for a in assets:
            key = key_fn(a)
            if a["price"] is not None:
                price_cache[key] = {"price": a["price"], "time": fetch_time}
                a["cache_time"] = None
            elif key in price_cache:
                a["price"]      = price_cache[key]["price"]
                a["cache_time"] = price_cache[key]["time"]
            else:
                a["cache_time"] = None

    # ── Read custom symbols and extend asset lists ──
    custom = read_custom_symbols()

    existing_us = {a["symbol"] for a in US_STOCKS}
    for sym in custom.get("us_stocks", []):
        if sym not in existing_us:
            US_STOCKS.append({"symbol": sym, "name": sym})

    existing_tw = {a["symbol"] for a in TW_STOCKS}
    for sym in custom.get("tw_stocks", []):
        # TW symbols in JSON have no .TW suffix; add it for yfinance
        full = sym if sym.endswith(".TW") else sym + ".TW"
        if full not in existing_tw:
            TW_STOCKS.append({"symbol": full, "name": sym})

    existing_crypto = {a["symbol"] for a in CRYPTO}
    for sym in custom.get("crypto", []):
        if sym not in existing_crypto:
            CRYPTO.append({"symbol": sym, "coingecko_id": None, "note": ""})

    # ── Fetch stock prices ──
    _US_FALLBACKS = {}  # reserved for symbols that need ticker alias fallbacks
    print("  US stocks...")
    for a in US_STOCKS:
        fallbacks = _US_FALLBACKS.get(a["symbol"])
        if fallbacks:
            a["price"], _ = fetch_yf_fallback(fallbacks)
        else:
            a["price"] = fetch_yf(a["symbol"])
        a["currency"] = "USD"
    apply_cache(US_STOCKS, lambda a: a["symbol"])

    print("  Taiwan stocks...")
    for a in TW_STOCKS:
        a["price"] = fetch_yf(a["symbol"])
        a["currency"] = "TWD"
    apply_cache(TW_STOCKS, lambda a: a["symbol"])

    print("  Exchange rates...")
    twd_usd = fetch_yf("TWDUSD=X")
    jpy_usd = fetch_yf("JPYUSD=X")
    if twd_usd is None:
        cached_rate = price_cache.get("TWDUSD=X")
        twd_usd = cached_rate["price"] if cached_rate else 0.031
        src = f"cache ({cached_rate['time'][:10]})" if cached_rate else "hardcoded fallback"
        print(f"  [warn] TWDUSD=X failed; using {src}: {twd_usd}")
    else:
        price_cache["TWDUSD=X"] = {"price": twd_usd, "time": fetch_time}
    if jpy_usd is None:
        cached_rate = price_cache.get("JPYUSD=X")
        jpy_usd = cached_rate["price"] if cached_rate else 0.0067
        src = f"cache ({cached_rate['time'][:10]})" if cached_rate else "hardcoded fallback"
        print(f"  [warn] JPYUSD=X failed; using {src}: {jpy_usd}")
    else:
        price_cache["JPYUSD=X"] = {"price": jpy_usd, "time": fetch_time}

    # ── Resolve CoinGecko IDs for custom crypto missing them ──
    print("  Crypto (CoinGecko)...")
    custom_crypto_syms = set(custom.get("crypto", []))
    for a in CRYPTO:
        if a["symbol"] in custom_crypto_syms and a["coingecko_id"] is None:
            print(f"    Searching CoinGecko ID for {a['symbol']}...")
            cg_id = find_coingecko_id(a["symbol"])
            if cg_id:
                a["coingecko_id"] = cg_id

    cg_ids = [a["coingecko_id"] for a in CRYPTO if a["coingecko_id"]]
    cg = fetch_coingecko(cg_ids)
    eth_price = cg.get("ethereum")
    for a in CRYPTO:
        cid = a["coingecko_id"]
        # None means: intentional ETH-proxy (BETH) or unfound custom coin
        a["price"] = eth_price if (cid is None and a["symbol"] in _CRYPTO_ETH_PROXY) \
                     else cg.get(cid) if cid else None
        a["currency"] = "USD"
    apply_cache(CRYPTO, lambda a: a["symbol"])

    save_price_cache(price_cache)

    update_time = fetch_time

    data = {
        "update_time":    update_time,
        "exchange_rates": {"TWDUSD": twd_usd, "JPYUSD": jpy_usd},
        "us_brokers":     US_BROKERS,
        "us_stocks":      US_STOCKS,
        "tw_brokers":     TW_BROKERS,
        "tw_stocks":      TW_STOCKS,
        "funds":          FUNDS,
        "exchanges":      EXCHANGES,
        "crypto":         CRYPTO,
        "banks":          BANKS,
    }

    html = build_html(data)
    with open("portfolio.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone! portfolio.html updated at {update_time}")
    print("Double-click portfolio.html to open in your browser.")
    if os.path.exists(CUSTOM_FILE):
        print(f"Custom symbols loaded from: {CUSTOM_FILE}")

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
.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.update-time { font-size: 0.78rem; color: #718096; background: white;
  padding: 4px 12px; border-radius: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.rates { font-size: 0.78rem; color: #4a5568; background: white;
  padding: 4px 12px; border-radius: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.dl-btn {
  font-size: 0.76rem; background: #ebfff4; color: #276749;
  border: 1px solid #9ae6b4; border-radius: 20px; padding: 4px 12px;
  cursor: pointer; transition: background 0.15s; display: none;
}
.dl-btn:hover { background: #c6f6d5; }

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

/* ── Asset name cells ── */
.aname-cell { text-align: left !important; }
.aname { font-weight: 600; color: #1a202c; }
.aname-sub { font-size: 0.78rem; color: #718096; font-weight: 400; }
.anote { font-size: 0.68rem; color: #a0aec0; display: block; margin-top: 1px; }
.na { color: #e53e3e; font-style: italic; }
.custom-tag {
  display: inline-block; font-size: 0.63rem; background: #ebfff4;
  color: #276749; border: 1px solid #9ae6b4; border-radius: 3px;
  padding: 0px 3px; margin-left: 4px; vertical-align: middle;
}
.needs-upd {
  font-size: 0.72rem; color: #c05621; font-style: italic; line-height: 1.4;
  text-align: center !important;
}

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
.cache-note { display: block; font-size: 0.65rem; color: #a0aec0; font-weight: 400; font-family: inherit; }
.totqty { font-family: 'SFMono-Regular', Consolas, monospace; color: #1a202c; font-weight: 600; }

/* ── Delete button (inside name cell) ── */
.del-btn {
  background: none; border: none; cursor: pointer; font-size: 0.85rem;
  color: #fc8181; padding: 0 2px 0 6px; opacity: 0.5;
  transition: opacity 0.15s; vertical-align: middle; line-height: 1;
}
tr:hover .del-btn { opacity: 1; }
.del-btn:hover { color: #e53e3e; }

/* ── Add symbol form ── */
.add-section { padding: 10px 16px 12px; border-top: 1px dashed #e2e8f0; }
.add-btn {
  background: none; border: 1.5px dashed #90cdf4; border-radius: 6px;
  color: #4299e1; font-size: 0.82rem; padding: 6px 16px; cursor: pointer;
  width: 100%; transition: all 0.15s;
}
.add-btn:hover { background: #ebf8ff; border-color: #63b3ed; }
.add-form {
  display: none; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;
}
.add-form input[type=text] {
  padding: 5px 8px; border: 1.5px solid #e2e8f0; border-radius: 6px;
  font-size: 0.82rem; color: #1a202c;
}
.add-form input[type=text]:focus { outline: none; border-color: #4299e1; }
.confirm-btn {
  background: #4299e1; color: white; border: none; border-radius: 6px;
  padding: 5px 14px; font-size: 0.82rem; cursor: pointer;
}
.confirm-btn:hover { background: #3182ce; }
.cancel-btn {
  background: none; border: 1.5px solid #e2e8f0; border-radius: 6px;
  padding: 5px 10px; font-size: 0.82rem; cursor: pointer; color: #718096;
}
.cancel-btn:hover { border-color: #cbd5e0; background: #f7fafc; }
.add-hint {
  font-size: 0.75rem; color: #718096; margin-top: 6px; line-height: 1.5;
  background: #fffbeb; border: 1px solid #f6e05e; border-radius: 6px;
  padding: 6px 10px;
}

/* ── Grand total bar ── */
.grand-bar {
  background: linear-gradient(135deg,#1a202c,#2d3748); border-radius: 12px;
  padding: 20px 28px; display: flex; justify-content: space-between; align-items: center;
  box-shadow: 0 4px 20px rgba(0,0,0,0.18); flex-wrap: wrap; gap: 16px;
}
.grand-sections { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
.grand-item { text-align: center; }
.grand-item-label { font-size: 0.72rem; color: #a0aec0; margin-bottom: 2px; }
.grand-item-val { font-size: 0.9rem; font-weight: 700; color: #e2e8f0;
  font-family: 'SFMono-Regular', Consolas, monospace; }
.pct-label { display: block; font-size: 0.68rem; color: #718096; margin-top: 2px; }
.grand-divider { width: 1px; height: 36px; background: rgba(255,255,255,0.15); }
.grand-total-block { text-align: right; }
.grand-total-label { font-size: 0.82rem; color: #a0aec0; margin-bottom: 4px; }
.grand-total-val { font-size: 1.8rem; font-weight: 800; color: #68d391;
  font-family: 'SFMono-Regular', Consolas, monospace; }
"""

# ─── JS ───────────────────────────────────────────────────────────────────────

JS = r"""
// ── idk(): mirrors Python idk() ──────────────────────────────────────────────
function idk(s) { return s.replace(/[^a-zA-Z0-9]/g, '_'); }

// ── localStorage helpers ──────────────────────────────────────────────────────
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
  else       el.classList.remove('hv');
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
function fUSD(v)   { return v === 0 ? '-' : '$ ' + fn(v, 2); }
function fTWD(v)   { return v === 0 ? '-' : 'NT$ ' + fn(Math.round(v), 0); }
function fBadge(v) { return 'NT$ ' + fn(Math.round(v), 0); }
function fQty(v) {
  if (v === 0) return '-';
  if (v % 1 === 0) return v.toLocaleString('en-US');
  return parseFloat(v.toPrecision(8)).toLocaleString('en-US', {maximumSignificantDigits: 8});
}
function fPnl(pct) {
  var cls = pct >= 0 ? 'pnl-pos' : 'pnl-neg';
  return '<span class="' + cls + '">' + (pct >= 0 ? '+' : '') + fn(pct, 2) + '%</span>';
}
function naSpan() { return '<span class="na">N/A</span>'; }

// ── Calculation: one stock/crypto row ─────────────────────────────────────────
function calcUsStock(s, usdToTwd) {
  var k = idk(s.symbol), price = s.price, totalQty = 0, totalUSD = 0;
  DATA.us_brokers.forEach(function(_, bi) {
    var qty = lsGet('sq_' + k + '_' + bi);
    totalQty += qty;
    var v = (price !== null && qty > 0) ? price * qty : null;
    setEl('sv_' + k + '_' + bi, v !== null ? fUSD(v) : (qty > 0 ? naSpan() : '-'));
    if (v !== null) totalUSD += v;
  });
  setEl('sq_' + k + '_tot', totalQty > 0 ? fQty(totalQty) : '-');
  setEl('sv_' + k + '_tot', totalUSD > 0 ? fUSD(totalUSD) : '-');
  var cost = lsGet('sc_' + k);
  setEl('spl_' + k, (price !== null && cost > 0) ? fPnl((price - cost) / cost * 100) : '-');
  return totalUSD * usdToTwd;
}
function calcTwStock(s) {
  var k = idk(s.symbol), price = s.price, totalTWD = 0;
  DATA.tw_brokers.forEach(function(_, bi) {
    var qty = lsGet('tq_' + k + '_' + bi);
    var v = (price !== null && qty > 0) ? price * qty : null;
    setEl('tv_' + k + '_' + bi, v !== null ? fTWD(v) : (qty > 0 ? naSpan() : '-'));
    if (v !== null) totalTWD += v;
  });
  setEl('tv_' + k + '_tot', totalTWD > 0 ? fTWD(totalTWD) : '-');
  var cost = lsGet('tc_' + k);
  setEl('tpl_' + k, (price !== null && cost > 0) ? fPnl((price - cost) / cost * 100) : '-');
  return totalTWD;
}
function calcCrypto(c, usdToTwd) {
  var sym = c.symbol, price = c.price, totalQty = 0;
  DATA.exchanges.forEach(function(_, ei) { totalQty += lsGet('cq_' + sym + '_' + ei); });
  setEl('ctq_' + sym, totalQty > 0 ? fQty(totalQty) : '-');
  var totalUSD = (price !== null && totalQty > 0) ? price * totalQty : null;
  setEl('ctv_' + sym, totalUSD !== null ? fUSD(totalUSD) : (totalQty > 0 ? naSpan() : '-'));
  var cost = lsGet('cc_' + sym);
  setEl('cpl_' + sym, (price !== null && cost > 0) ? fPnl((price - cost) / cost * 100) : '-');
  return totalUSD !== null ? totalUSD * usdToTwd : 0;
}

// ── Main calculation ──────────────────────────────────────────────────────────
function calc() {
  var r = DATA.exchange_rates;
  var usdToTwd = 1 / r.TWDUSD;
  var jpyToTwd = r.JPYUSD / r.TWDUSD;
  var subUsTwd = 0, subTwTwd = 0, subFundsTwd = 0, subCryptoTwd = 0, subCashTwd = 0;

  // US stocks (DATA + pending custom)
  DATA.us_stocks.forEach(function(s) { subUsTwd += calcUsStock(s, usdToTwd); });
  csGetPending('us').forEach(function(item) {
    calcUsStock({symbol: item.symbol, price: null}, usdToTwd);
  });
  setEl('sub_us',   fBadge(subUsTwd));
  setEl('sub_us_f', fBadge(subUsTwd));

  // TW stocks (DATA + pending custom)
  DATA.tw_stocks.forEach(function(s) { subTwTwd += calcTwStock(s); });
  csGetPending('tw').forEach(function(item) { calcTwStock({symbol: item.symbol, price: null}); });
  setEl('sub_tw',   fBadge(subTwTwd));
  setEl('sub_tw_f', fBadge(subTwTwd));

  // Funds
  DATA.funds.forEach(function(_, fi) { subFundsTwd += lsGet('fv_' + fi); });
  setEl('sub_funds',   fBadge(subFundsTwd));
  setEl('sub_funds_f', fBadge(subFundsTwd));

  // Crypto (DATA + pending custom)
  DATA.crypto.forEach(function(c) { subCryptoTwd += calcCrypto(c, usdToTwd); });
  csGetPending('crypto').forEach(function(item) {
    calcCrypto({symbol: item.symbol, price: null}, usdToTwd);
  });
  setEl('sub_crypto',   fBadge(subCryptoTwd));
  setEl('sub_crypto_f', fBadge(subCryptoTwd));

  // Banks
  var bankTwd = 0;
  DATA.banks.forEach(function(_, bi) {
    var sub = lsGet('bd_' + bi + '_0') + lsGet('bd_' + bi + '_1');
    setEl('bs_' + bi, sub > 0 ? fTWD(sub) : '-');
    bankTwd += sub;
  });
  var usdTwd = lsGet('fx_USD') * usdToTwd;
  var jpyTwd = lsGet('fx_JPY') * jpyToTwd;
  setEl('fxt_USD', usdTwd > 0 ? fTWD(usdTwd) : '-');
  setEl('fxt_JPY', jpyTwd > 0 ? fTWD(jpyTwd) : '-');
  subCashTwd = bankTwd + usdTwd + jpyTwd;
  setEl('sub_banks',   fBadge(subCashTwd));
  setEl('sub_banks_f', fBadge(subCashTwd));

  // Grand total + percentages
  var grand = subUsTwd + subTwTwd + subFundsTwd + subCryptoTwd + subCashTwd;
  function pct(v) { return grand > 0 ? (v / grand * 100).toFixed(1) + '%' : '—'; }
  function barVal(v) {
    return fTWD(v) + '<span class="pct-label">' + pct(v) + '</span>';
  }
  setEl('bar_us',     barVal(subUsTwd));
  setEl('bar_tw',     barVal(subTwTwd));
  setEl('bar_funds',  barVal(subFundsTwd));
  setEl('bar_crypto', barVal(subCryptoTwd));
  setEl('bar_cash',   barVal(subCashTwd));
  setEl('grand_total', 'NT$ ' + fn(Math.round(grand), 0));
}

// ── Custom symbols management ─────────────────────────────────────────────────
var CS_KEY = 'pf2_custom_';

function csGet(section) {
  try { return JSON.parse(localStorage.getItem(CS_KEY + section) || '[]'); }
  catch(e) { return []; }
}
function csSet(section, arr) { localStorage.setItem(CS_KEY + section, JSON.stringify(arr)); }

function getDataSyms(section) {
  if (section === 'us')     return DATA.us_stocks.map(function(x) { return x.symbol; });
  if (section === 'tw')     return DATA.tw_stocks.map(function(x) { return x.symbol; });
  if (section === 'crypto') return DATA.crypto.map(function(x) { return x.symbol; });
  return [];
}

// Custom symbols not yet fetched by update.py (show as "needs update")
function csGetPending(section) {
  var dataSyms = getDataSyms(section);
  return csGet(section).filter(function(x) { return dataSyms.indexOf(x.symbol) < 0; });
}

function showAddForm(section) {
  document.getElementById('add-form-' + section).style.display = 'flex';
  document.getElementById('add-btn-'  + section).style.display = 'none';
  document.getElementById('add-sym-'  + section).value = '';
  document.getElementById('add-name-' + section).value = '';
  document.getElementById('add-sym-'  + section).focus();
}
function cancelAdd(section) {
  document.getElementById('add-form-' + section).style.display = 'none';
  document.getElementById('add-btn-'  + section).style.display = '';
}
function confirmAdd(section) {
  var raw = document.getElementById('add-sym-' + section).value.trim();
  if (!raw) { alert('請輸入代號'); return; }
  var sym = raw.toUpperCase();
  if (section === 'tw' && sym.indexOf('.TW') < 0) sym += '.TW';
  var name = document.getElementById('add-name-' + section).value.trim();
  var all = getDataSyms(section).concat(csGet(section).map(function(x) { return x.symbol; }));
  if (all.indexOf(sym) >= 0) { alert('"' + sym + '" 已存在'); return; }
  var arr = csGet(section);
  arr.push({symbol: sym, name: name});
  csSet(section, arr);
  cancelAdd(section);
  renderCustomRows(section);
  updateDlBtn();
  calc();
}
function delSymbol(btn) {
  var sym     = btn.dataset.symbol;
  var section = btn.dataset.section;
  if (!confirm('確定刪除「' + sym + '」？\n相關數量及成本資料也將一併清除。')) return;
  csSet(section, csGet(section).filter(function(x) { return x.symbol !== sym; }));
  var k = idk(sym);
  if (section === 'us') {
    DATA.us_brokers.forEach(function(_, bi) { localStorage.removeItem(LS + 'sq_' + k + '_' + bi); });
    localStorage.removeItem(LS + 'sc_' + k);
  } else if (section === 'tw') {
    DATA.tw_brokers.forEach(function(_, bi) { localStorage.removeItem(LS + 'tq_' + k + '_' + bi); });
    localStorage.removeItem(LS + 'tc_' + k);
  } else if (section === 'crypto') {
    DATA.exchanges.forEach(function(_, ei) { localStorage.removeItem(LS + 'cq_' + sym + '_' + ei); });
    localStorage.removeItem(LS + 'cc_' + sym);
  }
  renderCustomRows(section);
  updateDlBtn();
  calc();
}

// Build an input element string for custom rows
function mkInp(id, w, ph, extraCls) {
  return '<input type="number" id="' + id + '" data-ls="' + id
    + '" step="any" min="0" placeholder="' + (ph || '0')
    + '" style="width:' + w + 'px" class="qi' + (extraCls || '')
    + '" oninput="onInput(this)">';
}

function renderCustomRows(section) {
  var tbody = document.getElementById('custom-' + section);
  if (!tbody) return;
  tbody.innerHTML = '';
  csGetPending(section).forEach(function(item) {
    var sym = item.symbol, k = idk(sym);
    var namePart = item.name
      ? ' <span class="aname-sub">' + item.name + '</span>' : '';
    var label = '<span class="aname">' + sym + namePart
      + ' <span class="custom-tag">自訂</span></span>'
      + '<button class="del-btn" data-section="' + section
      + '" data-symbol="' + sym + '" onclick="delSymbol(this)" title="刪除">&#x2715;</button>';
    var html = '<td class="aname-cell">' + label + '</td>';

    if (section === 'us') {
      DATA.us_brokers.forEach(function(_, bi) {
        var id = 'sq_' + k + '_' + bi;
        html += '<td>' + mkInp(id, 78, '0', '') + '</td>'
              + '<td class="val" id="sv_' + k + '_' + bi + '">-</td>';
      });
      html += '<td class="totqty" id="sq_' + k + '_tot">-</td>'
            + '<td class="val" id="sv_' + k + '_tot">-</td>'
            + '<td class="needs-upd">需重新執行<br>update.py</td>'
            + '<td>' + mkInp('sc_' + k, 82, '成本', ' cost-inp') + '</td>'
            + '<td id="spl_' + k + '">-</td>';
    } else if (section === 'tw') {
      DATA.tw_brokers.forEach(function(_, bi) {
        var id = 'tq_' + k + '_' + bi;
        html += '<td>' + mkInp(id, 78, '0', '') + '</td>'
              + '<td class="twd" id="tv_' + k + '_' + bi + '">-</td>';
      });
      html += '<td class="twd" id="tv_' + k + '_tot">-</td>'
            + '<td class="needs-upd">需重新執行<br>update.py</td>'
            + '<td>' + mkInp('tc_' + k, 82, '成本', ' cost-inp') + '</td>'
            + '<td id="tpl_' + k + '">-</td>';
    } else if (section === 'crypto') {
      DATA.exchanges.forEach(function(_, ei) {
        var id = 'cq_' + sym + '_' + ei;
        html += '<td>' + mkInp(id, 68, '0', '') + '</td>';
      });
      html += '<td class="totqty" id="ctq_' + sym + '">-</td>'
            + '<td class="needs-upd">需重新執行<br>update.py</td>'
            + '<td>' + mkInp('cc_' + sym, 82, '成本', ' cost-inp') + '</td>'
            + '<td class="val" id="ctv_' + sym + '">-</td>'
            + '<td id="cpl_' + sym + '">-</td>';
    }

    var tr = document.createElement('tr');
    tr.innerHTML = html;
    tbody.appendChild(tr);
    // Restore saved values
    tr.querySelectorAll('input[data-ls]').forEach(function(el) {
      var v = lsGet(el.dataset.ls);
      if (v > 0) { el.value = v; el.classList.add('hv'); }
    });
  });
}

function updateDlBtn() {
  var has = ['us', 'tw', 'crypto'].some(function(s) { return csGet(s).length > 0; });
  var btn = document.getElementById('dl-custom-btn');
  if (btn) btn.style.display = has ? 'inline-block' : 'none';
}

function downloadCustom() {
  var us  = csGet('us').map(function(x) { return x.symbol; });
  var tw  = csGet('tw').map(function(x) { return x.symbol.replace(/\.TW$/i, ''); });
  var cry = csGet('crypto').map(function(x) { return x.symbol; });
  var obj = {us_stocks: us, tw_stocks: tw, crypto: cry};
  var blob = new Blob([JSON.stringify(obj, null, 2)], {type: 'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'custom_symbols.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

document.addEventListener('DOMContentLoaded', function() {
  restore();
  ['us', 'tw', 'crypto'].forEach(function(s) { renderCustomRows(s); });
  updateDlBtn();
  calc();
});
"""

# ─── HTML builders ────────────────────────────────────────────────────────────

def add_form_html(section, sym_placeholder="代號"):
    """Return the add-symbol form + button + usage hint for a section."""
    return (
        '<div class="add-section">'
        f'<div class="add-form" id="add-form-{section}">'
        f'  <input type="text" id="add-sym-{section}" placeholder="{sym_placeholder}" style="width:130px">'
        f'  <input type="text" id="add-name-{section}" placeholder="顯示名稱（選填）" style="width:150px">'
        f'  <button class="confirm-btn" onclick="confirmAdd(\'{section}\')">確認新增</button>'
        f'  <button class="cancel-btn" onclick="cancelAdd(\'{section}\')">取消</button>'
        '</div>'
        f'<button class="add-btn" id="add-btn-{section}" onclick="showAddForm(\'{section}\')">'
        '&#xFF0B; 新增標的</button>'
        '<div class="add-hint">&#x26A0;&#xFE0F; 新增後請點上方『匯出自訂標的』，'
        '將 <code>custom_symbols.json</code> 儲存到記帳資料夾，'
        '再重新執行 <code>更新價格.bat</code> 即可抓取最新報價。</div>'
        '</div>\n'
    )


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
        '<button class="dl-btn" id="dl-custom-btn" onclick="downloadCustom()">'
        '&#x1F4E5; 匯出自訂標的 (custom_symbols.json)</button>'
        '</div>'
        '</div>\n'
    )


def build_us_section(data):
    brokers = data["us_brokers"]
    stocks  = data["us_stocks"]

    # thead: 2-row header
    th1 = '<tr>'
    th1 += '<th class="lft" rowspan="2">標的</th>'
    for br in brokers:
        th1 += f'<th class="broker-span" colspan="2">{br}</th>'
    th1 += '<th rowspan="2">合計股數</th>'   # ← NEW column
    th1 += '<th rowspan="2">合計 (USD)</th>'
    th1 += '<th rowspan="2">現價 (USD)</th>'
    th1 += '<th rowspan="2">成本 (USD)</th>'
    th1 += '<th rowspan="2">損益</th>'
    th1 += '</tr>'

    th2 = '<tr>'
    for _ in brokers:
        th2 += '<th>數量</th><th>總值</th>'
    th2 += '</tr>'
    thead = '<thead>' + th1 + th2 + '</thead>'

    rows = ''
    for s in stocks:
        sym = s['symbol']
        k   = idk(sym)
        row = f'<tr><td class="aname-cell"><span class="aname">{sym}</span></td>'
        for bi in range(len(brokers)):
            row += f'<td>{inp(f"sq_{k}_{bi}", f"sq_{k}_{bi}", w=78)}</td>'
            row += f'<td class="val" id="sv_{k}_{bi}">-</td>'
        row += f'<td class="totqty" id="sq_{k}_tot">-</td>'
        row += f'<td class="val" id="sv_{k}_tot">-</td>'
        row += f'<td class="price-col">{fmt_price(s["price"], "USD", s.get("cache_time"))}</td>'
        row += f'<td>{cost_inp(f"sc_{k}", f"sc_{k}")}</td>'
        row += f'<td id="spl_{k}">-</td>'
        row += '</tr>\n'
        rows += row

    # cols: name(1) + brokers×2 + 合計股數(1) + total(1) + price(1) + cost(1) + pnl(1)
    n_label = 1 + len(brokers) * 2 + 2  # spans name through 合計股數+total
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_label}" style="text-align:right">美股小計（TWD）</td>'
        f'<td colspan="3"><strong id="sub_us_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = (thead
             + '<tbody>' + rows + '</tbody>'
             + '<tbody id="custom-us"></tbody>'
             + tfoot)
    return (
        '<div class="card">'
        '<div class="card-hd us">'
        '<span>&#x1F1FA;&#x1F1F8; 美股</span>'
        '<span class="sub-badge" id="sub_us">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        + add_form_html('us', '代號 (e.g. AAPL)')
        + '</div>\n'
    )


def build_tw_section(data):
    brokers = data["tw_brokers"]
    stocks  = data["tw_stocks"]

    th1 = '<tr>'
    th1 += '<th class="lft" rowspan="2">標的</th>'
    for br in brokers:
        th1 += f'<th class="broker-span" colspan="2">{br}</th>'
    th1 += '<th rowspan="2">合計 (TWD)</th>'
    th1 += '<th rowspan="2">現價 (TWD)</th>'
    th1 += '<th rowspan="2">成本 (TWD)</th>'
    th1 += '<th rowspan="2">損益</th>'
    th1 += '</tr>'
    th2 = '<tr>'
    for _ in brokers:
        th2 += '<th>數量</th><th>總值</th>'
    th2 += '</tr>'
    thead = '<thead>' + th1 + th2 + '</thead>'

    rows = ''
    for s in stocks:
        sym = s['symbol']
        k   = idk(sym)
        row = f'<tr><td class="aname-cell"><span class="aname">{s["name"]}</span></td>'
        for bi in range(len(brokers)):
            row += f'<td>{inp(f"tq_{k}_{bi}", f"tq_{k}_{bi}", w=78)}</td>'
            row += f'<td class="twd" id="tv_{k}_{bi}">-</td>'
        row += f'<td class="twd" id="tv_{k}_tot">-</td>'
        row += f'<td class="price-col">{fmt_price(s["price"], "TWD", s.get("cache_time"))}</td>'
        row += f'<td>{cost_inp(f"tc_{k}", f"tc_{k}")}</td>'
        row += f'<td id="tpl_{k}">-</td>'
        row += '</tr>\n'
        rows += row

    n_label = 1 + len(brokers) * 2 + 1  # name + broker pairs + total
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_label}" style="text-align:right">台股小計（TWD）</td>'
        f'<td colspan="3"><strong id="sub_tw_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = (thead
             + '<tbody>' + rows + '</tbody>'
             + '<tbody id="custom-tw"></tbody>'
             + tfoot)
    return (
        '<div class="card">'
        '<div class="card-hd tw">'
        '<span>&#x1F1F9;&#x1F1FC; 台股</span>'
        '<span class="sub-badge" id="sub_tw">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        + add_form_html('tw', '代號 (e.g. 0056)')
        + '</div>\n'
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
            f'<td class="aname-cell"><span class="aname">{f["name"]}</span></td>'
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
        sym   = c['symbol']
        note  = f'<span class="anote">{c["note"]}</span>' if c.get('note') else ''
        row = f'<tr><td class="aname-cell"><span class="aname">{sym}</span>{note}</td>'
        for ei in range(len(exchanges)):
            row += f'<td>{inp(f"cq_{sym}_{ei}", f"cq_{sym}_{ei}", w=68)}</td>'
        row += f'<td class="totqty" id="ctq_{sym}">-</td>'
        row += f'<td class="price-col">{fmt_price(c["price"], "USD", c.get("cache_time"))}</td>'
        row += f'<td>{cost_inp(f"cc_{sym}", f"cc_{sym}")}</td>'
        row += f'<td class="val" id="ctv_{sym}">-</td>'
        row += f'<td id="cpl_{sym}">-</td>'
        row += '</tr>\n'
        rows += row

    # cols: name(1) + exchanges + total_qty(1) + price(1) + cost(1) + value(1) + pnl(1)
    n_label = 1 + len(exchanges) + 3  # spans before value+pnl
    tfoot = (
        '<tfoot><tr>'
        f'<td colspan="{n_label}" style="text-align:right">加密貨幣小計（TWD）</td>'
        f'<td colspan="2"><strong id="sub_crypto_f">NT$ 0</strong></td>'
        '</tr></tfoot>'
    )

    inner = (thead
             + '<tbody>' + rows + '</tbody>'
             + '<tbody id="custom-crypto"></tbody>'
             + tfoot)
    return (
        '<div class="card">'
        '<div class="card-hd crypto">'
        '<span>&#x20BF; 加密貨幣</span>'
        '<span class="sub-badge" id="sub_crypto">NT$ 0</span>'
        '</div>'
        '<div class="table-wrap"><table>' + inner + '</table></div>'
        + add_form_html('crypto', '代號 (e.g. DOGE)')
        + '</div>\n'
    )


def build_cash_section(data):
    banks = data["banks"]
    r     = data["exchange_rates"]
    usd_twd = 1 / r["TWDUSD"]
    jpy_twd = r["JPYUSD"] / r["TWDUSD"]

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
            f'<td class="aname-cell"><span class="aname">{bank}</span></td>'
            f'<td>{inp(f"bd_{bi}_0", f"bd_{bi}_0", w=120, ph="活存")}</td>'
            f'<td>{inp(f"bd_{bi}_1", f"bd_{bi}_1", w=120, ph="定存")}</td>'
            f'<td class="twd" id="bs_{bi}">-</td>'
            f'</tr>\n'
        )
    fx_rows = (
        f'<tr>'
        f'<td class="aname-cell"><span class="aname">美金 (USD)</span></td>'
        f'<td>{inp("fx_USD", "fx_USD", w=120, ph="USD 金額")}</td>'
        f'<td class="price-col">1 USD = {usd_twd:.2f} TWD</td>'
        f'<td class="twd" id="fxt_USD">-</td>'
        f'</tr>\n'
        f'<tr>'
        f'<td class="aname-cell"><span class="aname">日幣 (JPY)</span></td>'
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
        bank_thead
        + '<tbody>' + bank_rows + '</tbody>'
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
