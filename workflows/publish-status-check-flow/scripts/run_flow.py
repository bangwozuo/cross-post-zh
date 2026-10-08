# -*- coding: utf-8 -*-
"""发布状态核对工作流 — 确定性编排脚本（T3）。

按 SKILL.md 步骤链路编排：
  S1 解析应发清单与实发记录 → S2 逐条核对 → S3 漏发提醒
每步读上一步产物，--demo 时使用内置真实输入，产物写 out/。仅标准库。

用法：
  python scripts/run_flow.py --demo
  python scripts/run_flow.py --input examples/input.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEMO_INPUT = {
    "input": (
        "应发清单（2026年10月12日-10月13日）：①小红书《500ml保温杯开箱种草》计划10月12日20:30发布；"
        "②抖音《保温杯6小时实测》计划10月12日21:30发布；"
        "③小红书《办公室喝水小妙招》计划10月13日12:30发布；"
        "④公众号《秋冬通勤水杯怎么选》计划10月13日12:30发布。"
        "实发记录：10月12日20:31小红书已发布《500ml保温杯开箱种草》；"
        "10月12日21:30抖音已发布《保温杯6小时实测》；"
        "10月13日截至13:00无小红书发布记录；10月13日截至13:00无公众号发布记录。"
        "请核对漏发情况并给出提醒。"
    )
}

PLATFORMS = ["小红书", "抖音", "公众号", "B站"]
ONTIME_MIN = 30      # 计划时间 ±30 分钟内算准时
LATE_SAME_DAY = True # 当日超出窗口算迟发，跨日算漏发


def parse(raw: str) -> tuple[list[dict], list[dict]]:
    """S1：解析应发清单与实发记录。"""
    plan = []
    for pm, title, mo, d, hhmm in re.findall(
            r"(小红书|抖音|公众号|B站)《([^》]+)》计划(\d+)月(\d+)日(\d+:\d+)发布", raw):
        plan.append({"platform": pm, "title": title, "month": int(mo),
                     "day": int(d), "time": hhmm})
    actual = []
    for mo, d, hhmm, pm, title in re.findall(
            r"(\d+)月(\d+)日(\d+:\d+)(小红书|抖音|公众号|B站)已发布《([^》]+)》", raw):
        actual.append({"platform": pm, "title": title, "month": int(mo),
                       "day": int(d), "time": hhmm})
    return plan, actual


def check(plan: list[dict], actual: list[dict]) -> list[dict]:
    """S2：逐条核对（按标题+平台匹配）。"""
    def minutes(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    rows = []
    for p in plan:
        hit = next((a for a in actual
                    if a["title"] == p["title"] and a["platform"] == p["platform"]), None)
        if hit is None:
            status = "漏发"
            actual_time = "—"
        else:
            diff = abs(minutes(hit["time"]) - minutes(p["time"]))
            same_day = (hit["month"], hit["day"]) == (p["month"], p["day"])
            if same_day and diff <= ONTIME_MIN:
                status = f"准时（偏差 {diff} 分钟）"
            elif same_day and LATE_SAME_DAY:
                status = f"迟发（偏差 {diff} 分钟，超 ±{ONTIME_MIN} 分钟窗口）"
            else:
                status = "漏发（实际发布时间跨日）"
            actual_time = f'{hit["month"]}月{hit["day"]}日 {hit["time"]}'
        rows.append({"平台": p["platform"], "内容": f'《{p["title"]}》',
                     "计划时间": f'{p["month"]}月{p["day"]}日 {p["time"]}',
                     "实际时间": actual_time, "状态": status})
    return rows


def remind(rows: list[dict]) -> list[str]:
    """S3：漏发提醒（读 S2 核对产物）。"""
    tips = []
    for r in rows:
        if r["状态"].startswith("漏发"):
            tips.append(f'【漏发】{r["平台"]}{r["内容"]}（计划 {r["计划时间"]}）'
                        f'未查到发布记录：建议当日 20:00-22:00 晚间档补发，'
                        f'补发前过 sensitive-word-precheck；未经人工确认不自动发布')
        elif r["状态"].startswith("迟发"):
            tips.append(f'【迟发】{r["平台"]}{r["内容"]}：{r["状态"]}，'
                        f'复盘延迟原因，避免挤占当日同平台名额')
    if not tips:
        tips.append("全部条目按时发布，无漏发提醒")
    return tips


def render_md(rows: list[dict], tips: list[str]) -> str:
    n_late = sum(1 for r in rows if r["状态"].startswith("漏发"))
    lines = ["# 发布状态核对 — 工作流实跑产物", "",
             f"## 核对结论", "",
             f"应发 {len(rows)} 条：准时 {sum(1 for r in rows if r['状态'].startswith('准时'))} 条、"
             f"漏发 {n_late} 条、其余 "
             f"{len(rows) - n_late - sum(1 for r in rows if r['状态'].startswith('准时'))} 条。", "",
             "## 核对表", "",
             "| 平台 | 内容 | 计划时间 | 实际时间 | 状态 |", "|---|---|---|---|---|"]
    lines += [f"| {r['平台']} | {r['内容']} | {r['计划时间']} | {r['实际时间']} | {r['状态']} |"
              for r in rows]
    lines += ["", "## 漏发提醒", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(tips, 1)]
    lines += ["", "（AI 生成内容，补发动作由人工执行）", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="发布状态核对工作流确定性编排")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--input", help="输入 JSON 路径")
    ap.add_argument("--outdir", default="out")
    args = ap.parse_args()

    if args.demo or not args.input:
        data = dict(DEMO_INPUT)
    else:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    raw = str(data.get("input", "")).strip()
    if not raw:
        print("[publish-status-check-flow] 输入为空，终止", file=sys.stderr)
        return 2

    plan, actual = parse(raw)     # S1
    if not plan:
        print("[publish-status-check-flow] 未解析到应发清单（需含 平台《标题》计划X月X日HH:MM发布）",
              file=sys.stderr)
        return 2
    rows = check(plan, actual)    # S2
    tips = remind(rows)           # S3

    outdir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), args.outdir)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "flow_result.json"), "w", encoding="utf-8") as f:
        json.dump({"核对表": rows, "漏发提醒": tips,
                   "summary": f"应发 {len(rows)} 条，漏发 "
                              f"{sum(1 for r in rows if r['状态'].startswith('漏发'))} 条"},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, "发布状态核对.md"), "w", encoding="utf-8") as f:
        f.write(render_md(rows, tips))
    print(f"[publish-status-check-flow] S1→S2→S3 完成：应发 {len(rows)} 条，"
          f"产物已写入 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
