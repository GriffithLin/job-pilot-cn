"""validator 防虚构测试：数字白名单 / 公司名 / 禁词 / 年限。"""

from jobpilot.scoring.validator import validate_tailor_output

PROFILE = {
    "persona": {"tenure_years": 1},
    "resume_facts": {
        "preserved_companies": ["某国产 AI 芯片公司"],
        "real_metrics": ["-56%", "5ms→2.19ms", "20+", "553us→321us"],
        "allowed_skills": ["C++", "PyTorch ATen"],
        "forbidden_claims": ["精通", "Triton 生产经验"],
    },
}

RESUME = "在国产 NPU 公司交付 20+ 算子，反向优化 5ms 到 2.19ms（-56%）。"


def test_valid_output_passes():
    text = "【AI 算子方向】\n- 交付 20+ 算子，反向优化 5ms→2.19ms（-56%）"
    assert validate_tailor_output(text, PROFILE, RESUME) == []


def test_fabricated_number_fails():
    text = "- 反向优化性能提升 -80%"
    errors = validate_tailor_output(text, PROFILE, RESUME)
    assert any("80" in e for e in errors)


def test_forbidden_company_fails():
    text = "- 曾在英伟达负责 CUDA kernel 优化"
    errors = validate_tailor_output(text, PROFILE, RESUME)
    assert any("英伟达" in e for e in errors)


def test_forbidden_word_fails():
    text = "- 精通 Triton 生产经验调优"
    errors = validate_tailor_output(text, PROFILE, RESUME)
    assert any("精通" in e for e in errors)
    assert any("Triton 生产经验" in e for e in errors)


def test_tenure_inflation_fails():
    text = "- 3 年 GPU 算子开发经验，交付 20+ 算子"
    errors = validate_tailor_output(text, PROFILE, RESUME)
    assert any("年限" in e for e in errors)


def test_llm_leak_fails():
    text = "以下是修改后的版本：- 交付 20+ 算子"
    errors = validate_tailor_output(text, PROFILE, RESUME)
    assert any("泄漏" in e for e in errors)
