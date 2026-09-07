"""薪资解析测试：字体反爬解码 + 正则解析。"""

from jobpilot.discovery.boss import decode_salary_font, parse_salary


def test_decode_salary_font():
    # E8F3=3, E8F5=5, E8F8=8, E8F2=2 → "35-82K·16薪" 中的私有区字符
    raw = f"{chr(0xE8F3)}{chr(0xE8F5)}-{chr(0xE8F8)}{chr(0xE8F2)}K·16薪"
    assert decode_salary_font(raw) == "35-82K·16薪"


def test_decode_salary_font_2026():
    # 2026-09 实测段 U+E031-E03A（kanzhun 字体），取自真实卡片抓包
    # -K·薪 → 35-65K·15薪
    raw = f"{chr(0xE034)}{chr(0xE036)}-{chr(0xE037)}{chr(0xE036)}K·{chr(0xE032)}{chr(0xE036)}薪"
    assert decode_salary_font(raw) == "35-65K·15薪"
    # -元/天 → 500-800元/天（日结岗）
    raw = f"{chr(0xE036)}{chr(0xE031)}{chr(0xE031)}-{chr(0xE039)}{chr(0xE031)}{chr(0xE031)}元/天"
    assert decode_salary_font(raw) == "500-800元/天"


def test_parse_salary_normal():
    assert parse_salary("25-45K·16薪") == (25, 45, 16)
    assert parse_salary("20-40K") == (20, 40, 12)
    assert parse_salary("15-25k") == (15, 25, 12)


def test_parse_salary_reversed():
    # 反爬字体解码后可能出现倒序，取 min/max 兜底
    assert parse_salary("45-25K") == (25, 45, 12)


def test_parse_salary_invalid():
    assert parse_salary("面议") is None
    assert parse_salary("") is None
    assert parse_salary("500-800元/天") is None


def test_liepin_salary():
    from jobpilot.discovery.liepin import _parse_liepin_salary
    assert _parse_liepin_salary("25-45K") == (25, 45, 12)
    assert _parse_liepin_salary("面议") is None
