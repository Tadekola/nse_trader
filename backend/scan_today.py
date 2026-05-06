"""Run full market scan and display recommendations."""
import urllib.request
import json

BASE = "http://localhost:8888"

# Market regime
regime = json.loads(urllib.request.urlopen(BASE + "/api/v1/market/regime", timeout=30).read())
rd = regime.get("data", regime)
regime_name = rd.get("regime", "?").upper()
regime_conf = rd.get("confidence", 0) * 100
trend = rd.get("trend_direction", "?")
print("=" * 70)
print("  MARKET REGIME: %s (confidence: %.0f%%)" % (regime_name, regime_conf))
print("  Trend: %s" % trend)
print("=" * 70)
print()

# Individual stock scan
SYMBOLS = [
    "GTCO", "ZENITHBANK", "UBA", "DANGCEM", "SEPLAT", "NESTLE", "MTNN",
    "ACCESSCORP", "FIDELITYBK", "WAPCO", "MANSARD", "OKOMUOIL", "PRESCO",
    "FCMB", "STANBIC", "BUACEMENT", "GEREGU", "WEMABANK", "OANDO", "NAHCO",
    "NB", "BUAFOODS", "AIRTELAFRI", "FIRSTHOLDCO", "UCAP", "CADBURY",
    "UNILEVER", "VITAFOAM", "TRANSCORP", "JBERGER", "CUSTODIAN",
    "ETI", "STERLINGNG", "GUINNESS", "DANGSUGAR", "NASCON", "INTBREW",
    "CONOIL", "UACN", "NGXGROUP",
]

results = []
for s in SYMBOLS:
    try:
        url = BASE + "/api/v1/recommendations/" + s
        d = json.loads(urllib.request.urlopen(url, timeout=30).read()).get("data", {})
        results.append({
            "symbol": s,
            "action": d.get("action", "?"),
            "status": d.get("status", "?"),
            "price": d.get("current_price", 0),
            "rr": d.get("risk_reward_ratio"),
            "prob": d.get("bias_probability"),
            "conf": d.get("confidence", 0),
            "reason": (d.get("primary_reason", "") or "")[:50],
        })
    except Exception as e:
        results.append({"symbol": s, "action": "ERROR", "status": str(e)[:30],
                        "price": 0, "rr": None, "prob": None, "conf": 0, "reason": ""})

# Sort: BUY/STRONG_BUY first (by confidence desc), then HOLD, then rest
def sort_key(r):
    order = {"STRONG_BUY": 0, "BUY": 1, "HOLD": 2, "SELL": 3, "STRONG_SELL": 4, "AVOID": 5}
    return (order.get(r["action"], 9), -r["conf"])

results.sort(key=sort_key)

buy_list = [r for r in results if r["action"] in ("BUY", "STRONG_BUY")]
hold_list = [r for r in results if r["action"] == "HOLD"]
sell_list = [r for r in results if r["action"] in ("SELL", "STRONG_SELL", "AVOID")]

print("SCAN RESULTS: %d stocks scanned" % len(results))
print("  BUY: %d | HOLD: %d | SELL: %d" % (len(buy_list), len(hold_list), len(sell_list)))
print()

fmt = "%-14s %-10s %-10s %10s %6s %6s %6s  %s"
print(fmt % ("Symbol", "Action", "Status", "Price", "R:R", "Prob", "Conf", "Reason"))
print("-" * 110)

for r in results:
    rr_s = "%.1f" % r["rr"] if r["rr"] is not None else "-"
    prob_s = "%d%%" % r["prob"] if r["prob"] is not None else "-"
    conf_s = "%.0f%%" % r["conf"]
    price_s = "{:,.2f}".format(r["price"]) if r["price"] else "-"
    print(fmt % (r["symbol"], r["action"], r["status"], price_s, rr_s, prob_s, conf_s, r["reason"]))

print()
if buy_list:
    print("--- BUY SIGNALS ---")
    rr_vals = [r["rr"] for r in buy_list if r["rr"] is not None]
    prob_vals = [r["prob"] for r in buy_list if r["prob"] is not None]
    if rr_vals:
        print("  R:R range: %.1f - %.1f" % (min(rr_vals), max(rr_vals)))
    if prob_vals:
        print("  Probability range: %d%% - %d%%" % (min(prob_vals), max(prob_vals)))
else:
    print("No BUY signals today. All stocks gated to HOLD (confidence < 50%%).")
