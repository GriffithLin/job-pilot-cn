---
name: jd-collector
description: |
  JD（职位描述）收集与对标工具。使用场景：
  - 用户贴来一段 JD 文本，要落档并做需求映射
  - 用户要从某个平台（当前支持小红书）抓取近期 JD
  - 攒了多个 JD 后要横向对比市场信号、调整学习/简历
  触发词：「JD」「岗位」「招聘」「职位描述」「抓 JD」「对标岗位」
---

# JD Collector — 岗位描述收集与对标

## 核心流程（所有来源通用）

1. **落档**：原始 JD 逐字保存到用户的笔记仓库（当前为 `d:\gitspace\cuda-wiki\dfsx\`），
   文件名 `JD-<公司或平台>-<主题>-<YYYYMMDD>.md`
2. **需求映射**：P1（必须）/ P2（重要）/ P3（加分）三级，每条 JD 要求对照用户现状：
   ✅ 已满足 / ◐ 部分 / ❌ 缺失，附差距动作
3. **学习清单**：缺失项按性价比排序，标注预估投入
4. **简历调整点**：映射结论转成对简历文件的具体修改建议
5. **市场信号**（多 JD 时）：横向统计高频关键词，输出「市场在要什么」

## Adapter: 手动粘贴（默认）

用户贴 JD 文本 → 直接走核心流程，无需任何环境。

## Adapter: 小红书抓取

**前置**（一次性，已配置可跳过）：
- `~/.local/bin/` 下有 `xiaohongshu-mcp.exe` / `xiaohongshu-login.exe` / `jq.exe`
- `~/.xiaohongshu/cookies.json` 存在（登录态）。过期时运行 `xiaohongshu-login.exe` 扫码，
  cookie 会写到运行时工作目录，需移到 `~/.xiaohongshu/cookies.json`
- MCP 服务：`xiaohongshu-mcp.exe` 后台运行于 :18060
- ⚠️ Windows Defender 需排除 go-rod 的 leakless 临时目录（知名误报）

**用法**：
```bash
# 关键词必须是纯 ASCII（如 CUDA），中文经 Windows curl 会乱码 —— 一律走 python 客户端：
echo '{"keyword":"CUDA 招聘","filters":{"sort_by":"最新"}}' > args.json  # 由 python 写入更稳
python3 <skill>/scripts/xhs_call.py search_feeds args.json
# 详情（feed_id/xsec_token 来自搜索结果）：
echo '{"feed_id":"...","xsec_token":"..."}' > args2.json
python3 <skill>/scripts/xhs_call.py get_feed_detail args2.json
```
- 参数 JSON 文件用 python 以 UTF-8 写入（`json.dump(..., ensure_ascii=False)`）
- 详情返回 `data.note`：`time`(ms 时间戳) / `desc`(正文) / `imageList` / `comments`
- 图片里的 JD 无法解析，img≥4 的帖子标注「详情在图」让用户自己看

**抓取节奏（防限流）**：搜索间隔 ≥15s；连续搜索报 `context deadline exceeded`
时等 20s 重试；详情抓取间隔 8s；单轮控制在 ≤20 个请求，勿高频批量。

**踩坑记录**：
- Windows curl.exe 把命令行参数转 ANSI 代码页，中文 JSON body 必乱码 → 必须用 python 客户端
- MCP Streamable HTTP 需要 `Accept: application/json, text/event-stream` 头
- python urllib 需禁用系统代理（ProxyHandler({})）
- MCP 一次搜索内含 60s 超时，慢就是失败，退避重试即可

## 输出模板

见 `dfsx/JD-AMD-GPU深度学习框架优化.md`（映射表结构）与
`dfsx/JD-小红书-AI算子岗-20260902.md`（多帖汇总结构）。
