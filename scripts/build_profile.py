"""一次性脚本：从简历 md 生成 ~/.jobpilot-cn/ 下的 resume.txt + profile.json。

用法：
    uv run python scripts/build_profile.py --resume path/to/你的简历.md
可重复跑：--force 覆盖已有 profile.json（会连带覆盖手工调整，注意先备份）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jobpilot import config  # noqa: E402


def strip_markdown(text: str) -> str:
    """md → 纯文本（打分输入用）。"""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*>\s*", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`(.+?)`", r"\1", line)
        line = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", line)
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines)


def extract_metrics(text: str) -> list[str]:
    """提取量化指标候选（数字+单位），供人工核对。"""
    pattern = re.compile(
        r"-?\d+(?:\.\d+)?(?:%|us|ms|µs|s|K|k)?"
        r"(?:\s*[→~-]\s*-?\d+(?:\.\d+)?(?:%|us|ms|µs|s|K|k)?)?"
        r"(?:\s*~\s*-?\d+(?:\.\d+)?%?)?"
        r"|\d+\+"
    )
    seen: list[str] = []
    for m in pattern.findall(text):
        if m not in seen and any(c.isdigit() for c in m):
            seen.append(m)
    return seen


# 示例 profile：结构即契约（persona / preferences / facts / resume_facts 四块，
# validator 按 resume_facts 校验防虚构）。生成后请编辑 ~/.jobpilot-cn/profile.json
# 填入真实信息——真实值不要写进本脚本，避免随仓库公开。
EXAMPLE_PROFILE = {
    "persona": {
        "name": "张三",
        "direction": "AI 算子开发 / 异构计算（GPU / NPU kernel 方向）",
        "direction_summary": "大模型算子优化",
        "tenure_years": 1,
        "tenure_since": "2025.07",
        "greet_tenure": "1 年",
    },
    "preferences": {
        "cities": ["上海", "深圳"],
        "salary_min_k": 25,
        "keywords": ["算子开发", "GPU 优化", "异构计算", "CUDA"],
        "title_blacklist": ["外包", "驻场", "实习", "驱动", "测试开发"],
        "company_blacklist": [],
        "min_score_to_greet": 6,
    },
    "facts": {
        "have": [
            "NPU 算子开发 1 年（embedding / attention 算子全周期）",
            "20+ 算子交付，多项量化优化",
        ],
        "lack": ["Triton", "torch.compile", "GPU 量产经验", "上游开源贡献"],
    },
    "resume_facts": {
        "preserved_companies": ["某 AI 芯片公司"],
        "preserved_school": None,  # TODO：学历待填
        "real_tenure": "1 年",
        "real_metrics": ["+30%", "10ms→5ms", "20+"],
        "allowed_skills": ["C++", "Python", "PyTorch", "类 CUDA 软件栈"],
        "forbidden_claims": [
            "精通", "多年 GPU", "3 年以上", "Triton 生产经验", "主导开源",
        ],
        "company_blocklist": [],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", required=True, help="简历 markdown 路径")
    parser.add_argument("--force", action="store_true", help="覆盖已有 profile.json")
    args = parser.parse_args()

    resume_md = Path(args.resume)
    if not resume_md.exists():
        raise SystemExit(f"简历不存在: {resume_md}")

    # 1. resume.txt
    plain = strip_markdown(resume_md.read_text(encoding="utf-8"))
    config.resume_path().write_text(plain, encoding="utf-8")
    print(f"✓ resume.txt 已生成（{len(plain)} 字）: {config.resume_path()}")

    # 2. profile.json
    if config.profile_path().exists() and not args.force:
        print(f"· profile.json 已存在，跳过（--force 覆盖）: {config.profile_path()}")
    else:
        config.profile_path().write_text(
            json.dumps(EXAMPLE_PROFILE, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✓ profile.json 已生成: {config.profile_path()}")

    # 3. searches.yaml
    if not config.searches_path().exists():
        example = config.REPO_ROOT / "searches.example.yaml"
        if example.exists():
            shutil.copy(example, config.searches_path())
            print(f"✓ searches.yaml 已从模板生成: {config.searches_path()}")

    # 4. 量化指标候选清单（人工核对进 profile.json 的 real_metrics）
    print("\n量化指标候选（已出现在简历中的数字，validator 白名单自动含简历数字）：")
    for m in extract_metrics(plain):
        print(f"  · {m}")

    print("\nTODO（请编辑 ~/.jobpilot-cn/profile.json 填入真实信息）：")
    print("  · preferences.cities / salary_min_k（目标城市与薪资底线）")
    print("  · resume_facts.preserved_school（学历）")
    print("  · .env 填 OPENAI_API_KEY / JOBPILOT_MODEL")


if __name__ == "__main__":
    main()
