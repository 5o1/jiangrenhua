# jiangrenhua

`jiangrenhua` 是 `write-project-paper` 写作 skill 的独立源码仓库。它把项目证据取舍、中文研究论文写作、四轮复审和可重复的 HTML/PDF 审计放在同一版本中。仓库名是 `jiangrenhua`；为兼容现有调用，skill 的调用名仍是 `$write-project-paper`。

## 内容

- [`skills/write-project-paper/SKILL.md`](skills/write-project-paper/SKILL.md)：skill 入口和工作边界。
- [`skills/write-project-paper/references/`](skills/write-project-paper/references/)：证据、引用、复审和研究者叙述视角规则。
- [`skills/write-project-paper/scripts/audit_paper.py`](skills/write-project-paper/scripts/audit_paper.py)：引用闭合、语言候选、人工裁定指纹与可选 PDF 审计。
- [`tests/`](tests/)：确定性回归测试。
- [`evals/`](evals/)：干净上下文试跑的微型项目、用例与人工评审量表。

## 使用

Codex skill 是一个包含 `SKILL.md` 的目录；当前仓库中的可安装目录为 `skills/write-project-paper`。在 Codex 能发现该目录的环境中，使用 `$write-project-paper` 调用。若机器上已经有同名 skill，先比较版本，不要直接覆盖。此仓库不会自动修改现有的 `~/.codex/skills/write-project-paper`。

审计 HTML 论文：

```bash
python skills/write-project-paper/scripts/audit_paper.py paper.html --json
```

若论文保留了审计脚本标出的对象主语段落，按 `references/authorial-voice-harness.md` 写裁定 JSON，再运行：

```bash
python skills/write-project-paper/scripts/audit_paper.py paper.html \
  --voice-review paper_voice_review.json --pdf paper.pdf --json
```

脚本只能定位形式上的候选；研究者是否真正承担了设计和解释，仍须按论文证据与语义人工判断。不能把代词数量当作质量分数。

## 验证

```bash
python -m unittest discover -s tests -v
```

`evals/` 还定义了从空白上下文试跑的任务和检查项。确定性测试通过，不等于干净上下文 agent 试跑通过；后者须在隔离工作目录中另行执行，并保存输出与评审记录。

目前没有配置 Git 远端，也没有发布许可证。未经另行决定，不应将该仓库推送为公开项目。
