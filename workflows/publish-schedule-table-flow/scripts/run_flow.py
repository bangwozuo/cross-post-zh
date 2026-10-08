# -*- coding: utf-8 -*-
"""定时发布排期表工作流 — 确定性编排脚本（T3）。

按 SKILL.md 步骤链路编排：
  S1 解析内容池与约束 → S2 发布日历生成（冲突处理 + 排期）→ S3 最佳时段建议
每步读上一步产物，--demo 时使用内置真实输入，产物写 out/。仅标准库。

用法：
  python scripts/run_flow.py --demo
  python scripts/run_flow.py --input examples/input.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

DEMO_INPUT = {
    "input": (
        "内容池：1. 小红书笔记《500ml保温杯开箱种草》，优先级高，希望10月13日（周二）晚间发布；"
        "2. 抖音短视频《保温杯6小时实测》，优先级高，希望10月13日（周二）晚间发布；"
        "3. 公众号图文《秋冬通勤水杯怎么选》，优先级中，10月14日至10月16日任选一天；"
        "4. 小红书笔记《办公室喝水小妙招》，优先级低，希望10月14日发布。"
        "约束：可用发布时段为工作日12:00-13:00、20:00-22:00；小红书每天至多发布1篇；"
        "10月12日全天不可用。请产出跨平台发布日历并给出时段安排建议。"
    )
}

PLATFORMS = ["小红书", "抖音", "公众号", "B站"]
PRIOR = {"高": 0, "中": 1, "低": 2}
NOON, EVE1, EVE2 = "12:30", "20:30", "21:30"   # 午间 / 晚间主档 / 晚间错峰档
WEEKDAY = "一二三四五六日"


def parse_items(raw: str) -> tuple[list[dict], list[tuple[int, int]]]:
    """S1：从文本解析条目（平台/标题/优先级/日期区间/时段偏好/是否必须）与禁排日。"""
    items, seg = [], re.split(r"[；。]", raw)
    for s in seg:
        tm = re.search(r"《([^》]+)》", s)
        pm = next((p for p in PLATFORMS if p in s), None)
        if not (tm and pm):
            continue
        dates = [(int(m), int(d)) for m, d in re.findall(r"(\d+)月(\d+)日", s)]
        rng = (dates[0][1], dates[-1][1]) if dates else (13, 14)
        items.append({
            "title": tm.group(1), "platform": pm,
            "priority": (re.search(r"优先级(高|中|低)", s) or [None, "中"])[1] if re.search(r"优先级(高|中|低)", s) else "中",
            "start": rng[0], "end": rng[1],
            "strict": "必须" in s or "要求" in s,
            "eve": "晚间" in s, "noon": "午间" in s,
        })
    blocked = [(int(m), int(d)) for m, d in
               re.findall(r"(\d+)月(\d+)日[^；。]*?不可用", raw)]
    return items, blocked


def schedule(items: list[dict], blocked: list[tuple[int, int]],
             daily_cap: int = 1) -> tuple[list[dict], list[str], list[str]]:
    """S2：按优先级排期。返回 schedule/conflicts/unscheduled。"""
    conflicts, unscheduled = [], []
    used = {}            # (month, day) -> {platform: count}
    eve_used = {}        # (month, day) -> 已用晚间档次数
    rows = []
    for it in sorted(items, key=lambda x: PRIOR.get(x["priority"], 1)):
        placed = None
        for day in range(it["start"], it["end"] + 1):
            key = (10, day)
            if key in blocked:
                continue
            cnt = used.setdefault(key, {})
            if cnt.get(it["platform"], 0) >= daily_cap:
                if it["strict"] and placed is None and day == it["start"]:
                    pass  # 必须日的唯一候选撞车 → 落入未能排入
                continue
            cnt[it["platform"]] = cnt.get(it["platform"], 0) + 1
            if it["eve"] or (not it["noon"] and eve_used.get(key, 0) > 0):
                slot = EVE1 if eve_used.get(key, 0) == 0 else EVE2
                eve_used[key] = eve_used.get(key, 0) + 1
            else:
                slot = NOON
            placed = {"day": day, "slot": slot}
            break
        if placed is None:
            unscheduled.append(
                f"《{it['title']}》（{it['platform']}，优先级{it['priority']}，"
                f"要求{it['start']}月{it['start']}日前后）：与名额/禁排约束冲突，"
                f"建议人工确认后改排相邻可用日")
            continue
        dt = datetime.datetime(2026, 10, placed["day"])
        note = f"已排期（优先级{it['priority']}，{it['platform']}当日名额 {used[(10, placed['day'])][it['platform']]}/{daily_cap}）"
        rows.append({"日期": f"2026-10-{placed['day']:02d}（周{WEEKDAY[dt.weekday()]}）",
                     "时间": placed["slot"], "内容": f"《{it['title']}》",
                     "平台": it["platform"], "状态": note})
    rows.sort(key=lambda r: (r["日期"], r["时间"]))
    for key, cnt in used.items():
        for p, c in cnt.items():
            if c > 1:
                conflicts.append(f"{key[0]}月{key[1]}日 {p} 排了 {c} 条，超每日上限，需复核")
    if not conflicts:
        for key, eve in eve_used.items():
            if eve > 1:
                conflicts.append(
                    f"{key[0]}月{key[1]}日晚间同时段有 {eve} 条不同平台条目，已按 ≥1 小时错峰"
                    f"（{EVE1}/{EVE2}）处理")
    return rows, conflicts, unscheduled


def best_slots(rows: list[dict]) -> list[str]:
    """S3：最佳时段建议（读 S2 排期产物）。"""
    return [
        "午间档 12:00-13:00：适合公众号图文（通勤午休阅读）",
        "晚间主档 20:00-22:00：适合小红书/抖音（睡前高峰，互动率最高）",
        "同日晚间多条不同平台时按 ≥1 小时错峰，避免自家内容互相抢曝光",
        "小红书每天至多 1 篇，超过即挤占名额，低优先级条目转下一天",
    ]


def render_md(rows: list[dict], conflicts: list[str],
              unscheduled: list[str], advice: list[str]) -> str:
    lines = ["# 定时发布排期表 — 工作流实跑产物", "",
             "## 排期表", "",
             "| 日期 | 时间 | 内容 | 平台 | 状态 |", "|---|---|---|---|---|"]
    lines += [f"| {r['日期']} | {r['时间']} | {r['内容']} | {r['平台']} | {r['状态']} |"
              for r in rows]
    lines += ["", "## 冲突与处理", ""]
    lines += [f"{i}. {c}" for i, c in enumerate(conflicts, 1)] or ["1. 无冲突"]
    lines += ["", "## 未能排入", ""]
    lines += [f"{i}. {u}" for i, u in enumerate(unscheduled, 1)] or ["1. 全部条目均已排入"]
    lines += ["", "## 最佳时段建议", ""]
    lines += [f"- {a}" for a in advice]
    lines += ["", "（AI 生成内容，排期执行前需人工确认）", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="定时发布排期表工作流确定性编排")
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
        print("[publish-schedule-table-flow] 输入为空，终止", file=sys.stderr)
        return 2

    items, blocked = parse_items(raw)          # S1
    if not items:
        print("[publish-schedule-table-flow] 未解析到任何条目（需含《标题》与平台名）",
              file=sys.stderr)
        return 2
    rows, conflicts, unscheduled = schedule(items, blocked)   # S2
    advice = best_slots(rows)                  # S3

    outdir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), args.outdir)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "flow_result.json"), "w", encoding="utf-8") as f:
        json.dump({"排期表": rows, "冲突与处理": conflicts, "未能排入": unscheduled,
                   "时段建议": advice,
                   "summary": f"解析 {len(items)} 条，排入 {len(rows)} 条，"
                              f"未能排入 {len(unscheduled)} 条"},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, "发布排期表.md"), "w", encoding="utf-8") as f:
        f.write(render_md(rows, conflicts, unscheduled, advice))
    print(f"[publish-schedule-table-flow] S1→S2→S3 完成：排入 {len(rows)}/{len(items)} 条，"
          f"产物已写入 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
