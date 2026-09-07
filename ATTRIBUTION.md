# Attribution

本项目的架构思想与平台抓取知识受以下两个开源项目启发，**未复用任何一方代码**：

- [ApplyPilot](https://github.com/Pickle-Pixel/applypilot)（AGPL-3.0）——
  借鉴其「SQLite 单表数据总线 + 列级状态机」的 pipeline 编排思想，以及
  「LLM 只产结构化数据、代码组装文本、确定性 validator 校验」的分层信任防虚构设计。
  本项目所有代码均凭理解重写，未逐行复制其源码。
- [get_jobs](https://github.com/loks666/get_jobs)（禁止商用协议）——
  借鉴其沉淀的客观事实与经验：Boss 直聘 / 猎聘的 URL 格式、DOM 选择器、
  XHR 接口路径、薪资字体反爬映射规律（私有区 Unicode → 数字）、登录态管理经验
  与反检测思路。选择器字符串与接口路径属客观事实，实现代码均为重写。

如本项目未来公开发布，请保留本声明。
