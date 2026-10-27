#!/usr/bin/env python3
"""数据面板自动刷新：拉真实数据 → 重写 README 的 DATA 标记区 → 数字有变化才提交。
连击口径与 metrics 卡对齐（计到昨天为止的连续链）。"""
import json, os, re, subprocess, urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone

TOK = os.environ["GH_TOKEN"]
BT = chr(96)

def get(url, q=None):
    h = {"Authorization": f"token {TOK}", "Accept": "application/vnd.github+json"}
    if q:
        h["Content-Type"] = "application/json"
        data = json.dumps({"query": q}).encode()
        return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h)))
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=h)))

# ---- 1. 贡献日历（近一年）----
gq = '{ user(login: "LLL-404") { contributionsCollection { contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }'
days = [d for w in get("https://api.github.com/graphql", gq)["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
total = sum(d["contributionCount"] for d in days)
cnt = {d["date"]: d["contributionCount"] for d in days}
best = tmp = 0
for d in days:
    tmp = tmp + 1 if d["contributionCount"] > 0 else 0
    best = max(best, tmp)
today = date.fromisoformat(days[-1]["date"])
cur, probe = 0, today - timedelta(days=1)   # 连击=到昨天为止的连续链（与 metrics 卡同口径）
while cnt.get(probe.isoformat(), 0) > 0:
    cur += 1
    probe -= timedelta(days=1)

# ---- 2. 公开仓库与语言分布 ----
repos = get("https://api.github.com/users/LLL-404/repos?per_page=100&sort=pushed")
lang = Counter()
for r in repos:
    try:
        for k, v in get(r["languages_url"]).items():
            lang[k] += v
    except Exception:
        pass
tot = sum(lang.values())
langs = [(k, round(v * 100 / tot)) for k, v in lang.most_common(5) if v / tot >= 0.005]

# ---- 3. 提交时段（PushEvent，UTC+8）----
hours = Counter()
for e in get("https://api.github.com/users/LLL-404/events/public?per_page=100"):
    if e["type"] == "PushEvent":
        h8 = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8))).hour
        hours[h8] += 1
clusters = []
for h in sorted(hours):
    if (h - 1) % 24 not in hours:            # 簇起点
        end = h
        while (end + 1) % 24 in hours:
            end += 1
        clusters.append((h, end, sum(hours[x] for x in range(h, end + 1))))
clusters.sort(key=lambda c: -c[2])
def adj(start):
    return "上午" if 5 <= start < 11 else "午间" if 11 <= start < 14 else "午后" if 14 <= start < 18 else "夜间" if 18 <= start < 23 else "深夜"
def chip(c):
    a, b, n = c
    span = f"{a}–{b} 时" if a != b else f"{a} 时"
    return f"{adj(a)} {BT}{span}{BT}"
slots = " · ".join(chip(c) for c in clusters[:2])

# ---- 4. 生成面板块 ----
block = f"""| ⚡ 累计贡献 | 🔥 连击 | 📦 公开仓库 |
|:---:|:---:|:---:|
| **{total}** | **{cur} 天** · 最长 **{best} 天** | **{len(repos)}** |

🧭 **语言分布**　{("　".join(f"{BT}{k} {v}%{BT}" for k, v in langs))}

🕐 **提交作息**（UTC+8，近期）　{slots}
"""

# ---- 5. 替换 README 标记区，变了才提交 ----
readme = open("README.md", encoding="utf-8").read()
new = re.sub(r"<!-- DATA:BEGIN · CI 每小时自动刷新，手改会被覆盖 -->.*?<!-- DATA:END -->",
             lambda _: "<!-- DATA:BEGIN · CI 每小时自动刷新，手改会被覆盖 -->\n\n" + block + "\n<!-- DATA:END -->",
             readme, flags=re.S)
assert new != readme or "DATA:BEGIN" in readme
if new == readme:
    print("面板无变化，跳过提交")
    raise SystemExit(0)
open("README.md", "w", encoding="utf-8").write(new)
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
subprocess.run(["git", "add", "README.md"], check=True)
subprocess.run(["git", "commit", "-m", "data: auto refresh panel [skip ci]"], check=True)
subprocess.run(["git", "push"], check=True)
print(f"面板已刷新: 贡献{total} 连击{cur}/{best} 仓库{len(repos)}")
