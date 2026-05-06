"""Quick QC: check score range and action distribution after decompression."""
import requests, time
time.sleep(90)
r = requests.get("http://localhost:8888/api/v1/recommendations?limit=50", timeout=60)
data = r.json()
recs = data if isinstance(data, list) else data.get("recommendations", data.get("data", []))
print(f"Total recommendations: {len(recs)}")
print(f"{'SYMBOL':<18} {'CONF':>4}  {'SCORE':>6}  {'RAW':>6}  {'RISK':<10} {'ACTION':<14}")
print("-" * 76)
scores, confs = [], []
for rec in sorted(recs, key=lambda x: x.get("confidence", 0), reverse=True):
    sym = rec.get("symbol", "?")
    conf = rec.get("confidence", 0)
    score = rec.get("composite_score") or 0
    raw = rec.get("raw_score") or 0
    risk = rec.get("risk_level", "?")
    action = rec.get("action", "?")
    confs.append(conf)
    scores.append(score)
    print(f"{sym:<18} {conf:>3.0f}%  {score:>+.3f}  {raw:>+.3f}  {risk:<10} {action:<14}")

print(f"\nScore stats: min={min(scores):.3f}  max={max(scores):.3f}  range={max(scores)-min(scores):.3f}")
print(f"Confidence stats: min={min(confs):.0f}%  max={max(confs):.0f}%  avg={sum(confs)/len(confs):.0f}%")
actions = {}
for rec in recs:
    a = rec.get("action", "?")
    actions[a] = actions.get(a, 0) + 1
print(f"\nAction distribution: {dict(sorted(actions.items()))}")
