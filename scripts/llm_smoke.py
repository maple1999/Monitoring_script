from __future__ import annotations

import os
import sys

from src.config import load_config
from src.models import Item, gen_item_id
from src.llm import generate_llm_block


def main():
    cfg = load_config()
    item = Item(
        item_id=gen_item_id("smoke", "https://example.com"),
        category="contest",
        title="Image classification challenge",
        url="https://example.com/contest",
        source="example",
        summary="Classify 10k images into 10 classes. Provide training code and report.",
        deadline="2026-04-10",
        tags=["cv", "classification"],
    )
    block = generate_llm_block(cfg, item)
    if not block:
        print("LLM smoke test failed or returned empty output.")
        sys.exit(2)
    print("LLM block:\n" + block)
    sys.exit(0)


if __name__ == "__main__":
    main()

