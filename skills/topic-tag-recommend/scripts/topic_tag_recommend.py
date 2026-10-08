# -*- coding: utf-8 -*-
"""话题标签推荐 — 确定性脚本（T1）。

输入读 examples/input.json（或 --input 指定 / --demo 内置数据），
按规则从 content 抽取候选标签，统计结构配比，产出三套组合方案，
写 out/topic_tags.md 与 out/topic_tags.json。仅用标准库，确定性输出。

用法：
  python scripts/topic_tag_recommend.py --demo --outdir out
  python scripts/topic_tag_recommend.py --input examples/input.json --outdir out
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEMO_INPUT = {
    "content": (
        "新入手的500ml便携保温杯开箱：316不锈钢内胆，早上灌的热水到下午还是温的，"
        "杯身能塞进通勤包侧袋，杯口大好清洗。89元入手，领了10元券。"
    ),
    "platform": "小红书",
}

# 场景词与人群词词表（命中即归桶）
SCENE_WORDS = ["通勤", "办公", "宿舍", "秋冬", "旅行", "车载", "教室", "工位", "办公室"]
CROWD_WORDS = ["打工人", "学生", "宝妈", "上班族", "新手", "通勤党", "学生党"]
STOP_CHARS = re.compile(r"[，。！？：；、\s（）()《》【】\[\]\"'“”…—\-#%．.]")

MAX_TAGS = 10      # 总标签池上限
MIN_PER_PLAN, MAX_PER_PLAN = 3, 7    # 每套方案的标签数区间
MAX_TAG_LEN = 12   # 单个标签最大字数


def load_input(args) -> dict:
    if args.demo:
        return dict(DEMO_INPUT)
    path = args.input or os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "examples", "input.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_candidates(content: str) -> list[str]:
    """把文本切成 2-12 字的短语，作为候选标签（去重保序）。"""
    clauses = [c.strip() for c in STOP_CHARS.split(content) if c.strip()]
    seen, cands = set(), []
    for c in clauses:
        if "的" in c:  # 去掉「新入手的」类前缀，保留中心语
            c = c.split("的", 1)[1]
        tag = c[:MAX_TAG_LEN]
        if 2 <= len(tag) <= MAX_TAG_LEN and tag not in seen:
            seen.add(tag)
            cands.append(tag)
    return cands


def bucket(tag: str) -> str:
    if any(w in tag for w in CROWD_WORDS):
        return "人群"
    if any(w in tag for w in SCENE_WORDS):
        return "场景"
    return "精准"


def build_plans(cands: list[str]) -> tuple[list[str], list[dict], list[str]]:
    precise = [t for t in cands if bucket(t) == "精准"]
    scene = [t for t in cands if bucket(t) == "场景"]
    crowd = [t for t in cands if bucket(t) == "人群"]

    plan_a = (precise + scene + crowd)[:min(MAX_PER_PLAN, 4)]
    plan_b = (scene + crowd + precise)[:min(MAX_PER_PLAN, 4)]
    plan_c = (precise[:2] + scene[:1] + crowd[:1] + precise[2:3])[:min(MAX_PER_PLAN, 5)]
    # 每套方案不足 3 个时用候选池按序补齐
    pool = [t for t in cands]
    for plan in (plan_a, plan_b, plan_c):
        i = 0
        while len(plan) < MIN_PER_PLAN and i < len(pool):
            if pool[i] not in plan:
                plan.append(pool[i])
            i += 1

    pool_final = list(dict.fromkeys(plan_a + plan_b + plan_c))[:MAX_TAGS]
    total = len(pool_final)
    ratio = {
        "精准": round(100 * len([t for t in pool_final if bucket(t) == "精准"]) / total),
        "场景": round(100 * len([t for t in pool_final if bucket(t) == "场景"]) / total),
        "人群": round(100 * len([t for t in pool_final if bucket(t) == "人群"]) / total),
    }
    plans = [
        {"方案": "方案A（精准种草）", "标签": " ".join("#" + t for t in plan_a),
         "适用场景": "搜索意图明确，适合常规种草笔记"},
        {"方案": "方案B（场景人群）", "标签": " ".join("#" + t for t in plan_b),
         "适用场景": "借场景与人群话题获取泛流量"},
        {"方案": "方案C（混合均衡）", "标签": " ".join("#" + t for t in plan_c),
         "适用场景": "兼顾精准搜索与泛场景曝光"},
    ]
    basis = [
        f"标签均直接对应输入文本中的实体与场景，候选池共 {len(cands)} 个短语，"
        f"最终取 {total} 个（上限 {MAX_TAGS} 个）",
        f"结构配比：精准词 {ratio['精准']}%（目标 40%-60%）、场景词 {ratio['场景']}%"
        f"（目标 20%-40%）、人群词 {ratio['人群']}%（目标 0-20%）",
        "未获取平台实时热度数据，排序仅按内容相关性，未标注任何热度值",
        f"标签均不超过 {MAX_TAG_LEN} 字，符合平台惯用短标签习惯",
    ]
    return ["#" + t for t in pool_final], plans, basis


def render_md(platform: str, tags: list[str], plans: list[dict], basis: list[str]) -> str:
    lines = [
        "# 话题标签推荐（脚本实跑产物）",
        "",
        f"- 平台：{platform}",
        f"- 标签池：{len(tags)} 个（上限 10 个）",
        "",
        "## 标签组合",
        "",
    ]
    lines += [f"{i}. {t}" for i, t in enumerate(tags, 1)]
    lines += ["", "## 组合建议", "",
              "| 方案 | 标签 | 适用场景 |", "|---|---|---|"]
    lines += [f"| {p['方案']} | {p['标签']} | {p['适用场景']} |" for p in plans]
    lines += ["", "## 依据说明", ""]
    lines += [f"{i}. {b}" for i, b in enumerate(basis, 1)]
    lines += ["", "（AI 生成内容，发布前需人工确认）", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="话题标签推荐确定性脚本")
    ap.add_argument("--demo", action="store_true", help="使用内置演示数据")
    ap.add_argument("--input", help="输入 JSON 路径（缺省读 examples/input.json）")
    ap.add_argument("--outdir", default="out", help="产物目录（缺省 out/）")
    args = ap.parse_args()

    data = load_input(args)
    content = str(data.get("content", "")).strip()
    platform = str(data.get("platform", "小红书") or "小红书")
    if not content:
        print("[topic-tag-recommend] content 为空，无法推荐标签", file=sys.stderr)
        return 2

    cands = extract_candidates(content)
    if not cands:
        print("[topic-tag-recommend] 未能从 content 抽取到候选标签", file=sys.stderr)
        return 2
    tags, plans, basis = build_plans(cands)

    outdir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), args.outdir)
    os.makedirs(outdir, exist_ok=True)

    md = render_md(platform, tags, plans, basis)
    with open(os.path.join(outdir, "topic_tags.md"), "w", encoding="utf-8") as f:
        f.write(md)
    payload = {
        "platform": platform,
        "tags": tags,
        "combination": plans,
        "basis": basis,
        "meta": {"candidates": len(cands), "pool_size": len(tags),
                 "max_tags": MAX_TAGS, "max_tag_len": MAX_TAG_LEN},
    }
    with open(os.path.join(outdir, "topic_tags.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[topic-tag-recommend] 候选 {len(cands)} 个 → 标签池 {len(tags)} 个，"
          f"3 套方案已写入 {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
