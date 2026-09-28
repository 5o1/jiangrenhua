# jiangrenhua

`jiangrenhua` 是 `write-project-paper` 写作 skill 的独立源码仓库。它把项目证据取舍、中文研究论文写作、四轮复审和可重复的 HTML/PDF 审计放在同一版本中。仓库名是 `jiangrenhua`；为兼容现有调用，skill 的调用名仍是 `$write-project-paper`。

## 内容

- [`skills/write-project-paper/SKILL.md`](skills/write-project-paper/SKILL.md)：skill 入口和工作边界。
- [`skills/write-project-paper/references/`](skills/write-project-paper/references/)：证据、引用、复审和研究者叙述视角规则。
- [`skills/write-project-paper/scripts/audit_paper.py`](skills/write-project-paper/scripts/audit_paper.py)：引用闭合、语言候选、人工裁定指纹与可选 PDF 审计。
- [`tests/`](tests/)：确定性回归测试。
- [`evals/`](evals/)：仅在本地版本迭代时运行的干净上下文试跑、生成物和语义审阅量表。
- [`tools/release.py`](tools/release.py)：语义审阅通过后才更新 `VERSION` 并创建本地 tag。

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

普通提交与 GitHub Actions 只运行上述快速单元测试，不启动 agent。`VERSION` 初始为 `0.0.0`（尚无正式发布）；提出 `A.B.C` 新版本时才在本地运行一次干净上下文写作试跑。**通过的对象是 agent 生成的文章，不是进程退出码**：自动审计只是前置条件，审阅者还须阅读全文和 PDF，以具体段落、证据与页码填写 `human_review.json`。任一语义项目未通过，版本保持不变。

本地发布流程见 [`evals/README.md`](evals/README.md)。同一源码提交和目标版本的合格试跑会复用，不因第二次执行发布命令重复消耗模型额度。源码修改后，旧审阅不能复用。

已配置 `origin` 为 `https://github.com/5o1/jiangrenhua`，但本地发布命令不会推送；推送需另行执行。尚未发布许可证。
