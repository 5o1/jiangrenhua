# 本地版本门禁：先审生成文章，再改版本号

`VERSION` 使用 `A.B.C`。普通 commit 和 GitHub Actions 只运行快速单元测试，**不启动 agent**。当且仅当准备递增版本时，在本地运行一次干净上下文试跑，保存生成文章、PDF、完整 trace、自动审计和独立语义审阅。试跑不从当前对话继承项目历史，也不改动仓库中的 fixture 或现有已安装 skill。

## 发布流程

先把 skill 与脚本修改提交到 Git；安装试跑依赖后，执行：

```bash
python -m pip install -r evals/requirements.txt
python tools/release.py 0.1.0
```

首次执行会从新的 `codex exec` 会话生成论文，并写入 `evals/artifacts/v0.1.0/<源码提交前 12 位>/`。这是被 `.gitignore` 忽略的本地产物目录。它包含 `workspace/paper.html`、`paper.pdf`、`paper_review.md`、`paper_voice_review.json`、`trace.jsonl`、`audit.json`、`summary.json` 和待填写的 `human_review.json`。单次运行上限 20 分钟；缺依赖会在启动 agent 前报错。失败时保持 `VERSION` 不变；修正 skill 并提交后，新的源码提交可再次试跑。同一目标版本与源码提交不会重复启动模型。

自动检查通过后，审阅者须打开**这次 agent 真正生成的** HTML、PDF 和复审记录，逐项填写 `human_review.json` 的 `reviewer` 与 `checks`：

| 检查 | 需要审阅的文字质量 |
|---|---|
| `claims_grounded` | 结果与 fixture 证据一致，写清 1/3、2/3；不虚构真机或泛化结论。 |
| `authorial_voice` | 研究者承担设计、观察、解释与局限；对象主语只留在物理机制或实际结果等适当位置；不按“我们”次数打分。 |
| `beginner_readability` | 正文不用术语表也能连续读懂；首次术语有具体解释，没有一句一段的碎片化表述。 |
| `four_round_review` | 复审文件展示按顺序发现、修改、复查的四轮过程，而非空泛的全项通过声明。 |
| `pdf_visual` | 人工逐页看过 PDF，无截断、缺字、空白页或明显版式缺陷。 |

每项只有 `pass: true` 且 `evidence` 写出可定位的段落、引文、源文件或页码，才算通过。审阅者不能只看脚本输出；`paper_voice_review.json` 是生成代理的自查文件，**不能代替** `human_review.json`。若文本不合格，保持该项 `pass: false`，说明失败位置；修改 skill、提交后再以新源码进行试跑。不要手改生成论文来冒充 skill 的能力。

全部审阅通过后，重新执行相同命令：

```bash
python tools/release.py 0.1.0
```

发布脚本核对版本、源码提交、全部生成文件的 SHA-256、自动审计和逐项语义审阅；只有全部匹配才把 `VERSION` 更新为 `0.1.0`，创建本地 release commit 与 `v0.1.0` tag。它**不会 push**。配置的本地 pre-commit hook 也会拦截绕过发布脚本的版本文件提交；hook 不运行 agent。Git hook 不是安全边界，可以手动禁用，因此项目约定只通过 `tools/release.py` 发布。

## 验收边界

自动审计能发现若干形式错误，却不能判断研究者的叙述责任、因果说法或初学者可读性。即使 `summary.json` 写着 `machine_pass: true`，只要生成文本任一语义项未通过，版本仍不得迭代。`rubric.md` 保留更完整的评审量表；当前正式版本门禁使用显式调用用例，其他用例仍是后续扩展，不应声称已经通过。
