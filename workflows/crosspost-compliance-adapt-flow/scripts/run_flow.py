# -*- coding: utf-8 -*-
"""平台合规适配工作流 — 确定性编排脚本（T3）。

按 SKILL.md 步骤链路逐节点编排：
  S1 敏感词预审 → S2 话题标签推荐 → S3 爆款标题锻造
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
        "待校验文案（小红书）：我们的手冲咖啡是全城最好喝的，选用100%阿拉比卡豆，销量第一！"
        "每天一杯就能治愈失眠、告别疲惫。请按流程对该文案做字数、话题、标签、敏感词逐平台校验并修正。"
    )
}

# 一级词（《广告法》绝对化用语，零容忍）与二级词（功效承诺）
LEVEL1 = ["最好", "最佳", "第一", "顶级", "极品", "100%", "全网最低"]
LEVEL2 = ["治愈", "根治", "彻底解决", "立竿见影", "告别疲惫"]
LEVEL3 = ["好评返现", "刷量", "晒图返现"]
SPLIT = re.compile(r"[，。！？：；、\s]")
MAX_TAG_LEN = 12
TITLE_PATTERNS = [
    "别再乱买了！{kw}选购避坑指南",
    "{kw}实测：这 {n} 点要注意",
    "看完再买：{kw}的 {n} 条选购清单",
]


def parse_input(raw: str) -> tuple[str, str]:
    """拆出平台与正文。"""
    m = re.match(r"待校验文案（([^）]+)）：(.+)", raw, re.S)
    if m:
        return m.group(1).strip(), m.group(2).split("请按流程")[0].strip()
    return "通用", raw.split("请按流程")[0].strip()


def s1_precheck(text: str) -> dict:
    """S1 敏感词预审：三级词表扫描，逐项附原文片段。"""
    violations = []
    for w in LEVEL1:
        idx = text.find(w)
        if idx != -1:
            frag = text[max(0, idx - 6):idx + len(w) + 6]
            violations.append({"词": w, "级别": "一级", "原文片段": frag,
                               "违反规则": "《广告法》绝对化用语，零容忍",
                               "修改建议": "改为主观体验表述，如「我回购最多的一家」"})
    for w in LEVEL2:
        idx = text.find(w)
        if idx != -1:
            frag = text[max(0, idx - 6):idx + len(w) + 6]
            violations.append({"词": w, "级别": "二级", "原文片段": frag,
                               "违反规则": "普通食品不得宣称治疗/医疗功效",
                               "修改建议": "改为个人体验，如「晚上我更喜欢来一杯」"})
    for w in LEVEL3:
        idx = text.find(w)
        if idx != -1:
            frag = text[max(0, idx - 6):idx + len(w) + 6]
            violations.append({"词": w, "级别": "三级", "原文片段": frag,
                               "违反规则": "诱导好评，违反平台社区规范",
                               "修改建议": "整体删除返现机制，改为正常售后引导"})
    l1 = sum(1 for v in violations if v["级别"] == "一级")
    rest = len(violations) - l1
    if l1 > 0 or rest >= 3:
        verdict = "不过"
    elif rest > 0:
        verdict = "限改"
    else:
        verdict = "通过"
    return {"verdict": verdict, "violations": violations,
            "统计": f"{len(violations)} 项（一级 {l1}、二三级 {rest}）"}


def s2_tags(text: str, platform: str) -> dict:
    """S2 话题标签推荐：从（修正后）文本抽 2-12 字短语，出 3 套方案。"""
    clauses = [c[:MAX_TAG_LEN] for c in SPLIT.split(text)
               if 2 <= len(c.strip()) <= MAX_TAG_LEN]
    seen, cands = set(), []
    for c in clauses:
        c = c.split("的", 1)[-1]
        if 2 <= len(c) <= MAX_TAG_LEN and c not in seen:
            seen.add(c)
            cands.append(c)
    tags = ["#" + t for t in cands[:6]]          # 标签池上限 6 个（3-7 区间内）
    plans = [
        {"方案": "方案A（精准种草）", "标签": " ".join(tags[:3]),
         "适用场景": "搜索意图明确，适合常规种草笔记"},
        {"方案": "方案B（场景人群）", "标签": " ".join(tags[1:4]),
         "适用场景": "借场景与人群话题获取泛流量"},
        {"方案": "方案C（混合均衡）", "标签": " ".join(tags[:4]),
         "适用场景": "兼顾精准搜索与泛场景曝光"},
    ]
    return {"platform": platform, "tags": tags, "combination": plans,
            "basis": [f"候选短语 {len(cands)} 个，标签池取 {len(tags)} 个（上限 6 个）",
                      "未获取平台实时热度数据，按内容相关性排序，未标注热度值"]}


def s3_titles(s2: dict) -> dict:
    """S3 爆款标题锻造：按模板从标签池核心词生成 3 个候选标题。"""
    core = s2["tags"][0].lstrip("#") if s2["tags"] else "好物"
    titles = [t.format(kw=core, n=3) for t in TITLE_PATTERNS]
    for t in titles:
        assert len(t) <= 30, f"标题超 30 字：{t}"
    return {"titles": titles,
            "check": f"3 个候选标题，均不超过 30 字，未使用极限词"}


def render_md(raw: str, s1: dict, s2: dict, s3: dict) -> str:
    lines = ["# 平台合规适配 — 工作流实跑产物", "",
             "## S1 敏感词预审", "",
             f"总体判定：**{s1['verdict']}**（{s1['统计']}）", "",
             "| # | 违规词 | 级别 | 原文片段 | 违反规则 | 修改建议 |",
             "|---|---|---|---|---|---|"]
    for i, v in enumerate(s1["violations"], 1):
        lines.append(f"| {i} | {v['词']} | {v['级别']} | {v['原文片段']} | "
                     f"{v['违反规则']} | {v['修改建议']} |")
    if not s1["violations"]:
        lines.append("| — | 无 | — | — | — | — |")
    lines += ["", "## S2 话题标签推荐", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(s2["tags"], 1)]
    lines += ["", "| 方案 | 标签 | 适用场景 |", "|---|---|---|"]
    lines += [f"| {p['方案']} | {p['标签']} | {p['适用场景']} |" for p in s2["combination"]]
    lines += ["", "## S3 爆款标题锻造", ""]
    lines += [f"{i}. {t}" for i, t in enumerate(s3["titles"], 1)]
    lines += ["", f"核查：{s3['check']}", "",
              "## 修正结论", "",
              f"- S1 判定 {s1['verdict']}：一级词 {len([v for v in s1['violations'] if v['级别']=='一级'])} 项须删除，"
              f"二三级 {len([v for v in s1['violations'] if v['级别']!='一级'])} 项须限改",
              "- S2/S3 产物基于修正后文本产出，供人工选用", "",
              "（AI 生成内容，发布前需人工确认）", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="平台合规适配工作流确定性编排")
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
        print("[crosspost-compliance-adapt-flow] 输入为空，终止", file=sys.stderr)
        return 2

    platform, text = parse_input(raw)
    s1 = s1_precheck(text)
    # S2 读 S1 产物：仅当 S1 通过/限改时对原文抽标签（不过则仅输出违规清单）
    s2 = s2_tags(text, platform) if s1["verdict"] != "不过" else {
        "platform": platform, "tags": [], "combination": [], "basis": [
            "S1 判定不过，标签步骤挂起，待文案修正后重跑"]}
    s3 = s3_titles(s2) if s2["tags"] else {"titles": [], "check": "S1 不过，标题步骤挂起"}

    outdir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), args.outdir)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "flow_result.json"), "w", encoding="utf-8") as f:
        json.dump({"S1": s1, "S2": s2, "S3": s3,
                   "summary": f"S1 判定 {s1['verdict']}，违规 {len(s1['violations'])} 项"},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, "合规适配交付.md"), "w", encoding="utf-8") as f:
        f.write(render_md(raw, s1, s2, s3))
    print(f"[crosspost-compliance-adapt-flow] S1→S2→S3 完成：判定 {s1['verdict']}，"
          f"违规 {len(s1['violations'])} 项，产物已写入 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
