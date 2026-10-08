# 平台合规适配

## 元信息

| 字段 | 值 |
|------|-----|
| ID | `de_media_05_wf02` |
| 类型 | **`composite`（复合技能）** |
| 所属员工 | 分发改写师 |
| 阶段 | `P1` |
| 复杂度 | `S` |
| 触发方式 | 事件（WF1 后自动） |
| ROI | 规避因格式/敏感词导致的限流返工 |
| 资产形态 | 提示词编排 + Python 确定性编排脚本（T3） |

> 复合技能 = 工作流。它把多个**原子技能**按业务顺序编排在一起，完成一个完整场景。

## 能力描述

把待发布文案做逐平台合规校验并修正。每步量化验收：

1. **S1 敏感词预审**：三级词表扫描；任一一词命中或二三级合计 ≥3 项判「不过」，此时下游挂起
2. **S2 话题标签推荐**：每套 3-7 个标签、单个 2-12 字、标签池 ≤10 个
3. **S3 爆款标题锻造**：3 条候选、每条 ≤30 字、不虚构卖点
4. **S4 人工确认**：不过则修正文案后从 S1 重跑

## 编排的原子技能

| # | 原子技能 | 能力 |
|---|---------|------|
| 1 | [敏感词预审](../../skills/sensitive-word-precheck/) | 三级词表发布前预审，产出「过/限改/不过」判定 |
| 2 | [话题标签推荐](../../skills/topic-tag-recommend/) | 按内容与平台推荐话题标签组合 |
| 3 | [爆款标题锻造](https://github.com/bangwozuo/topic-planner-zh/tree/main/skills/viral-title-craft/)（跨仓技能） | 按平台风格批量产出候选标题 |

## 步骤链路（DAG）

```mermaid
flowchart LR
    IN["输入"]
    S1["敏感词预审"]
    S2["话题标签推荐"]
    S3["爆款标题锻造"]
    OUT["输出"]
    IN --> S1
    S1 --> S2
    S2 --> S3
    S3 --> OUT
```

## 步骤明细

| # | 步骤 | 技能资产 | 输入 | 输出 | 失败处理 |
|---|------|---------|------|------|---------|
| 1 | 敏感词预审 | [`../../skills/sensitive-word-precheck/`](../../skills/sensitive-word-precheck/) | 上一步输出 | 敏感词预审 输出 | 记录错误并中止 |
| 2 | 话题标签推荐 | [`../../skills/topic-tag-recommend/`](../../skills/topic-tag-recommend/) | 上一步输出 | 话题标签推荐 输出 | 记录错误并中止 |
| 3 | 爆款标题锻造 | [`https://github.com/bangwozuo/topic-planner-zh/tree/main/skills/viral-title-craft/`](https://github.com/bangwozuo/topic-planner-zh/tree/main/skills/viral-title-craft/) | 上一步输出 | 爆款标题锻造 输出 | 记录错误并中止 |

## 步骤说明

字数/话题/标签/敏感词逐平台校验→修正

## 输入规格

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input` | string / object | ✅ | 工作流初始输入，由触发条件提供 |

## 输出规格

| 字段 | 类型 | 说明 |
|------|------|------|
| `summary` | string | 执行摘要 |
| `steps` | string | 分步结果 |
| `deliverable` | string | 最终交付物 |

## 错误处理

| 情况 | 处理方式 |
|------|---------|
| 输入缺失 | 提示缺少的字段，终止流程 |
| 中间步骤输出不合规 | 合规技能拦截，返回修改建议，不继续下游 |
| 提示词被平台截断 | 拆分任务，分两次处理 |

## 验收标准

- [ ] 每一步的技能资产齐全（SKILL.md / prompt.txt / schema.json）
- [ ] 步骤间输入输出字段可衔接
- [ ] 末步输出带 AI 生成标识
- [ ] 全流程有人工确认环节

## 使用步骤

### 方式一：纯提示词编排（跨平台）

1. 把 `prompt.txt` 全文粘贴为系统提示词
2. 提供待校验文案与目标平台
3. 按 S1→S2→S3→S4 顺序执行，S1 判「不过」时 S2/S3 挂起

### 方式二：带脚本（端到端产物）

```bash
python <WF_DIR>/scripts/run_flow.py --demo
python <WF_DIR>/scripts/run_flow.py --input examples/input.json --outdir out
```

脚本用三级词表逐项定位原文片段并分级判定，产物落
`out/合规适配交付.md` 与 `out/flow_result.json`。判定与违规定位一律以脚本输出为准。

### 方式三：平台编排

| 平台 | 编排方式 |
|------|---------|
| **Coze / 扣子** | 新建工作流 → 按步骤添加节点，每个节点填入对应技能的 prompt.txt |
| **Dify** | 新建 Workflow → 添加 LLM 节点链，按 DAG 顺序连接 |
| **WorkBuddy** | 新建 Skill，按步骤在指令中串联各技能提示词 |

## 边界（不做的事）

- ❌ 不出法律意见书——预审结论不构成法律意见
- ❌ 不在 S1 判「不过」时强行产出标签与标题
- ❌ 不编造不存在的违规项——每条须能在原文中定位
- ❌ 不跨过 S4 人工确认直接宣称合规
- ❌ 不修改原文——只给修改建议，改稿由人工或上游改写技能执行

## 调用示例

**输入**（`examples/input.json`）：待校验小红书咖啡文案（含极限词与功效承诺）。

**输出**（脚本实跑）：S1 判定「不过」、违规 5 项（一级 3、二三级 2，逐项附原文片段），
S2/S3 按规则挂起；产物落 `out/合规适配交付.md`。

## 所属工作流

- 上游：[one-draft-multi-post-flow](../one-draft-multi-post-flow/)（一稿多投改写，触发本流）
- 下游：[publish-schedule-table-flow](../publish-schedule-table-flow/)（合规通过后排期）

## 合规声明

- 输出标注「AI 生成内容」；预审不构成法律意见，最终发布保留人工确认环节
- 词表随平台规则更新，使用前核对词表版本

---

*本复合技能定义由 build_p0_assets.py 生成，P1 深度改造升级为脚本编排*
