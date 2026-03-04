from src.llm import validate_llm_block


def test_validate_llm_block_ok():
    txt = (
        "难点评估：数据难点=数据规模较大；工程难点=部署与并行；数学/算法难点=优化与正则化；"
        "匹配度：4/5（理由：与CV方向高度相关）；"
        "评价：任务明确，资料充分。实践性较强。"
        "补充信息：无"
    )
    assert validate_llm_block(txt)


def test_validate_llm_block_missing():
    assert not validate_llm_block("评价：仅有评价，其他缺失。")

