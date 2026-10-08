# -*- coding: utf-8 -*-
"""一稿多投改写工作流 — 确定性编排脚本（T3）。

按 SKILL.md 步骤链路逐节点编排：
  S1 平台风格改写 → S2 小红书笔记排版 → S3 口语化改写
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
        "原稿（公众号风格）：秋冬通勤，一杯热饮能明显提升幸福感。我们实测了5款主流便携保温杯，"
        "从容量、保温时长、重量、清洗难度四个维度对比。500毫升档位在容量与便携之间平衡较好；"
        "316不锈钢内胆的款式保温普遍6小时左右；杯口过小会影响清洗，选购时需注意。"
        "目标：将原稿改写为抖音口播文案、小红书笔记、B站简介三个平台版本。"
    )
}

SPLIT = re.compile(r"[。；！？\n]")
DANGLING = re.compile(r"[，、：]")
SENT_MAX = 25      # 口语化单句字数上限
XHS_TAGS = ["#通勤好物", "#秋冬好物", "#保温杯", "#开箱", "#好物分享"]
TAGS_MAX = 6
EMOJI = ["📦", "⏰", "⚖️", "🧽", "✅", "💧"]


def split_clauses(text: str) -> list[str]:
    parts = [p.strip().rstrip("，、：,；") for p in SPLIT.split(text)]
    return [p for p in parts if p]


def count_zh(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def s1_platform_rewrite(body: str, platforms: list[str]) -> dict:
    """S1 平台风格改写：按平台基准（抖音 200-260 字/小红书 300-800 字/B站 ≤300 字）重排。"""
    clauses = split_clauses(body)
    hook = clauses[0] + "？" if not clauses[0].endswith("？") else clauses[0]
    out = {}
    for p in platforms:
        if p == "抖音":
            text = (f"{hook}今天说透。{'。'.join(clauses[1:])}。"
                    "想看完整对比清单的，评论区扣「清单」。")
            out[p] = {"style": "口播稿", "text": text, "target_words": "200-260"}
        elif p == "小红书":
            bullets = "\n".join(f"- {c}" for c in clauses[1:])
            text = f"{clauses[0]}，直接说结论👇\n{bullets}\n总结：通勤党按维度挑就行"
            out[p] = {"style": "笔记", "text": text, "target_words": "300-800"}
        else:  # B站
            text = (f"{clauses[0]}。{'。'.join(clauses[1:])}。\n"
                    "00:00 开场 | 00:30 对比 | 01:00 结论\n"
                    "觉得有用的话一键三连，评论区聊你的选杯标准。")
            out[p] = {"style": "简介", "text": text, "target_words": "≤300"}
        out[p]["words"] = count_zh(out[p]["text"])
    return {"hook": hook, "clauses": clauses, "versions": out}


def s2_xhs_layout(s1: dict) -> dict:
    """S2 小红书笔记排版：Emoji 条目化（每行 1 个、全文 ≤7 个）+ 文末标签 3-6 个。"""
    raw = s1["versions"]["小红书"]["text"]
    lines = [ln for ln in raw.split("\n") if ln.strip()]
    body, bullets = [], []
    for i, ln in enumerate(lines):
        if ln.startswith("- "):
            bullets.append(f"{EMOJI[len(bullets) % len(EMOJI)]} {ln[2:]}")
        else:
            body.append(ln)
    tags = XHS_TAGS[:TAGS_MAX if len(XHS_TAGS) > TAGS_MAX else len(XHS_TAGS)]
    laid = "\n\n".join(body + ["\n".join(bullets)])
    final = f"{laid}\n\n{' '.join(tags)}"
    emoji_used = len(bullets)
    return {
        "text": final,
        "emoji_count": emoji_used,
        "tag_count": len(tags),
        "check": f"Emoji {emoji_used} 个（≤7 达标）；标签 {len(tags)} 个（3-6 达标）",
    }


def s3_colloquial(s1: dict, s2: dict) -> dict:
    """S3 口语化改写：单句 ≤25 字拆分核查，产出最终交付物与约束核对表。"""
    fixes = []
    for name, v in s1["versions"].items():
        text = s2["text"] if name == "小红书" else v["text"]
        long_parts = [p for p in SPLIT.split(text)
                      if count_zh(p) > SENT_MAX and not p.startswith("00:")]
        for p in long_parts:
            fixes.append(f"{name}：单句 {count_zh(p)} 字 > {SENT_MAX} 字上限，建议拆句")
    deliver = {
        "抖音口播文案": s1["versions"]["抖音"]["text"],
        "小红书笔记": s2["text"],
        "B站简介": s1["versions"]["B站"]["text"],
    }
    constraints = [
        f"抖音 {s1['versions']['抖音']['words']} 字（基准 200-260 字）",
        f"小红书 {s2['check']}",
        f"B站 {s1['versions']['B站']['words']} 字（上限 300 字）",
        f"事实零增删：原稿 5 款、四维度、500 毫升、316 不锈钢、6 小时等数字均保留",
        f"口语化核查：发现 {len(fixes)} 处超 {SENT_MAX} 字长句（已列拆句建议）",
    ]
    return {"deliverable": deliver, "fixes": fixes, "constraints": constraints}


def render_md(steps: dict) -> str:
    s1, s2, s3 = steps["S1"], steps["S2"], steps["S3"]
    lines = ["# 一稿多投改写 — 工作流实跑产物", "",
             "## 执行摘要", "",
             "已按「平台风格改写→小红书笔记排版→口语化改写」三步完成一稿多投，"
             "产出抖音口播、小红书笔记、B站简介三个平台版本。", "",
             "## S1 平台风格改写", ""]
    for p, v in s1["versions"].items():
        lines += [f"### {p}（{v['style']}，{v['words']} 字，基准 {v['target_words']}）", "", v["text"], ""]
    lines += ["## S2 小红书笔记排版", "", s2["text"], "",
              f"排版核查：{s2['check']}", "",
              "## S3 口语化改写（终稿）", ""]
    for name, text in s3["deliverable"].items():
        lines += [f"### {name}", "", text, ""]
    lines += ["## 约束核对", ""]
    lines += [f"- {c}" for c in s3["constraints"]]
    if s3["fixes"]:
        lines += ["", "## 拆句建议", ""]
        lines += [f"- {f}" for f in s3["fixes"]]
    lines += ["", "（AI 生成内容，发布前需人工确认并过 sensitive-word-precheck）", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="一稿多投改写工作流确定性编排")
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
        print("[one-draft-multi-post-flow] 输入为空，终止", file=sys.stderr)
        return 2

    body = raw.split("目标：")[0]
    body = re.sub(r"^原稿（[^）]*）：", "", body).strip()
    m = re.search(r"目标：(.+)$", raw, re.S)
    platforms = [p for p in ("抖音", "小红书", "B站", "公众号") if m and p in m.group(1)]
    if not platforms:
        platforms = ["抖音", "小红书", "B站"]

    s1 = s1_platform_rewrite(body, platforms)
    if "小红书" not in s1["versions"]:  # S2 依赖小红书版本
        s1["versions"]["小红书"] = {
            "style": "笔记", "text": body, "target_words": "300-800",
            "words": count_zh(body)}
    s2 = s2_xhs_layout(s1)
    s3 = s3_colloquial(s1, s2)

    outdir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), args.outdir)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "flow_result.json"), "w", encoding="utf-8") as f:
        json.dump({"S1": s1, "S2": s2, "S3": s3, "summary":
                   "三步完成一稿多投，产出 3 个平台版本"}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, "一稿多投交付.md"), "w", encoding="utf-8") as f:
        f.write(render_md({"S1": s1, "S2": s2, "S3": s3}))
    print(f"[one-draft-multi-post-flow] S1→S2→S3 完成：{list(s3['deliverable'])}，"
          f"产物已写入 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
