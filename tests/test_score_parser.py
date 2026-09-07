"""score 输出协议解析测试。"""

from jobpilot.scoring.score import parse_score_output


def test_parse_ok():
    text = "SCORE: 8\nKEYWORDS: PagedAttention✓, vLLM对接✓, Triton✗\nREASONING: 算子方向全命中，缺口是 Triton 与 3 年 GPU 年限。"
    out = parse_score_output(text)
    assert out["fit_score"] == 8
    assert "PagedAttention✓" in out["score_keywords"]
    assert "Triton" in out["score_reasoning"]


def test_parse_clamp():
    out = parse_score_output("SCORE: 15\nKEYWORDS: x\nREASONING: y")
    assert out["fit_score"] == 10
    out = parse_score_output("SCORE: 0\nKEYWORDS: x\nREASONING: y")
    assert out["fit_score"] == 1


def test_parse_multiline_garbage():
    out = parse_score_output("抱歉我无法评估这个岗位。SCORE: 7\nKEYWORDS: a\nREASONING: b")
    assert out["fit_score"] == 7


def test_parse_failure_score_zero():
    out = parse_score_output("这个岗位挺好的。")
    assert out["fit_score"] == 0  # 失败记 0，--rescore 可重试
