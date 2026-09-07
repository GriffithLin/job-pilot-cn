# JobPilot-CN

半自动国内求职 agent：**抓岗 → AI 打分 → 打招呼语/简历定制要点 → 人工发送**。

架构思想与平台经验来自 [ApplyPilot](https://github.com/Pickle-Pixel/applypilot)（海外）与 [get_jobs](https://github.com/loks666/get_jobs)（国内平台），均未复用任何一方代码，见 [ATTRIBUTION.md](ATTRIBUTION.md)。

## 设计理念

- **半自动**：AI 干 80% 的活（抓取、过滤、打分、生成话术），最后一步「发送」由人在手机/网页上完成——Boss 直聘有检测机制（disable-devtool 检测 CDP、行为分析），全自动投递有封号风险；低频抓取 + 人工发送把风险压到最低。
- **SQLite 单表数据总线**：阶段间零直接调用，「阶段完成 = 该阶段负责的列非 NULL」，`jp run` 幂等可续传，崩溃重跑即接续。
- **防虚构三层**：LLM 只产结构化数据 → 代码组装文本 → 确定性 validator（数字白名单 / 公司占位 / 禁词 / 年限）守门，杜绝 AI 编造简历事实。

## Pipeline

```
[1] Discover   Boss(滚动采集+薪资字体解码) / 猎聘(XHR 拦截) → jobs 表（纯代码过滤，不进 LLM）
[2] Enrich     JD 全文（Boss 优先 API 拦截，DOM 兜底；猎聘 SPA 水合轮询）
[3] Score      LLM 打分 1-10（P1/P2/P3 映射 rubric，低于阈值不生成话术）
[4] Greet      ≤60 字打招呼语（失败回退静态语）
[5] Tailor     定制简历要点（validator 防虚构守门）
[6] Report     ~/.jobpilot-cn/reports/YYYY-MM-DD.md 每日待发清单
     —— 人工在 Boss/猎聘 App 发送 ——
[7] jp sent    回记发送状态
```

## 技术栈

Python 3.11+ · Typer · Playwright(Chromium) · SQLite(WAL) · OpenAI 兼容 LLM 端点 · Rich · Pydantic

## 快速开始

```powershell
uv sync
uv run playwright install chromium          # 浏览器底座需要

# 1. 生成 profile（从简历 md，生成后编辑 ~/.jobpilot-cn/profile.json 填真实信息）
uv run python scripts/build_profile.py --resume path/to/你的简历.md

# 2. 配置 LLM（OpenAI 兼容端点）
Copy-Item .env.example .env; notepad .env

# 3. 扫码登录（登录态持续保存，约一周一次）
uv run jp login boss
uv run jp login liepin

# 4. 校准打分质量（可选，用一份目标 JD 验证）
uv run jp check-jd examples/JD-AMD-calibration.md

# 5. 日常：每日一次
uv run jp run --max 20
#    打开 reports/ 下的清单，手机上发送，然后：
uv run jp sent --interactive

# 其他
uv run jp status              # 各阶段计数板
uv run jp run --skip-browser  # 只跑离线阶段（不碰浏览器）
```

## 项目结构

```
src/jobpilot/
├── cli.py            # Typer 入口
├── models.py         # 列级状态谓词——全系统的总线契约
├── db.py / pipeline.py / report.py
├── discovery/        # browser.py（Playwright 唯一封装点）+ boss.py + liepin.py
├── enrichment/       # Boss API 拦截 + 猎聘详情页
└── scoring/          # score / greet / tailor / validator
prompts/              # LLM prompt 与代码分离
scripts/              # build_profile 等一次性脚本
examples/             # 打分校准用 JD 样例
```

## 风控红线

- 每日一次 `jp run`，每平台 ≤20-40 岗，绝不循环轮询。
- 出现滑块/登录页/风控拦截 → 程序暂停等人工处理，不自动过验证。
- Token 预算：score 每岗 ≈ 4-5k tokens，greet/tailor 各 ≈ 1-2k；40 岗全流程 ≈ 25-35 万 tokens，用 `--max` 控量。

## 使用须知

- 本项目仅供**学习研究**与**个人求职**使用；请遵守目标平台用户协议，使用产生的一切风险与责任由使用者自行承担。
- 不用于任何商业用途；请保持低频使用，勿对平台造成负担。

## License

[MIT](LICENSE)
