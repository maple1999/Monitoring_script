from src.storage.db import Database
from src.models import Item, gen_item_id
from src.dedup import apply_dedup
from src.renderer import render_email


def test_dedup_by_url(tmp_path, monkeypatch):
    db = Database(path=str(tmp_path / "test.db"))
    it1 = Item(item_id=gen_item_id("s", "u1"), category="contest", title="t1", url="u1", source="s")
    it2 = Item(item_id=gen_item_id("s", "u1"), category="contest", title="t2", url="u1", source="s")
    items, dropped = apply_dedup(db, [it1, it2], by_url=True)
    assert len(items) == 1 and dropped == 1


def test_render_email_with_llm_block():
    item = Item(item_id=gen_item_id("s", "u2"), category="internship", title="CV Intern", url="u2", source="s")
    item.llm_block = (
        "难点评估：数据难点=数据偏置；工程难点=部署；数学/算法难点=收敛与泛化；"
        "匹配度：4/5（理由：CV岗位匹配）；评价：结构清晰，目标明确。具备实践价值。"
        "补充信息：无"
    )
    result = render_email({"internship": item}, {"status": "success", "notice": ""})
    assert "CV Intern" in result["text"]
    assert "难点评估" in result["html"]

