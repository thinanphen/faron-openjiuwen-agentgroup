# -*- coding: utf-8 -*-
"""法元 · Faron Agent Group —— 在线运行（需要真实模型接口）。

与 `run_offline_demo.py` 的区别：
    离线版把「不依赖模型的部分」跑通（工具 / 自检 / 交付）；
    本脚本把整套 openJiuwen TeamAgent 真正驱动起来，
    由 LLM 成员自主完成 建单 → 认领 → 检索 → 起草 → 自检 → 汇总。

运行前请配置环境变量（详见 faron_agentgroup/config.py）：
    FARON_LLM_API_BASE       例如 https://api.deepseek.com/v1
    FARON_LLM_API_KEY
    FARON_LLM_PROVIDER       默认 openai（OpenAI 兼容）
    FARON_LLM_MODEL_STRONG   主理 / 起草员
    FARON_LLM_MODEL_FAST     检索员 / 质检员

用法：
    python run_online.py                # 单轮委托
    python run_online.py --probe        # 只探测接口连通性
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from faron_agentgroup import FaronAgentGroup
from faron_agentgroup import config as cfg

COMMISSION = (
    "我方（中国某制造企业）与日本某商社设立合资公司，合资合同履行中出现出资迟延与"
    "经营分歧。请出具《合同审查意见书》：①日方出资迟延是否构成违约、我方能否请求"
    "继续履行；②准据法与管辖约定是否有效；③风险条款与修改建议。"
    "引用法条必须来自本地法库检索结果。"
)


def _mask(s: str) -> str:
    if not s:
        return "(empty)"
    return s[:6] + "..." + s[-4:] if len(s) > 12 else "***"


async def probe(conf: cfg.FaronConfig) -> bool:
    """探测模型接口连通性（发一次最小请求）。"""
    import aiohttp

    ep = conf.endpoints[0]
    url = ep.api_base_url.rstrip("/") + "/chat/completions"
    print(f"探测端点：{url}")
    print(f"模型    ：{ep.model_name}")
    print(f"Key     ：{_mask(ep.api_key)}")
    payload = {
        "model": ep.model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    headers = {"Authorization": f"Bearer {ep.api_key}",
               "Content-Type": "application/json"}
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, json=payload, headers=headers) as r:
                body = await r.text()
                print(f"HTTP {r.status}")
                print(body[:600])
                return r.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"探测失败：{type(exc).__name__}: {exc}")
        return False


async def main() -> int:
    conf = cfg.load_config_from_env()
    print("=" * 74)
    print("法元 · Faron Agent Group —— 在线运行")
    print("=" * 74)
    print(f"真实模型可用：{conf.has_model}")
    for e in conf.endpoints:
        print(f"  [{e.tier:6}] {e.model_name:24} @ {e.api_base_url}")

    if not conf.has_model:
        print("\n" + "!" * 74)
        print("未检测到可用的模型接口（FARON_LLM_API_KEY 未设置或仍是占位值）。")
        print("请先配置环境变量，或改用离线可复现路径：")
        print("    python run_offline_demo.py        # 工具 / 自检 / 交付，全程不需要模型")
        print("    python tests/test_audit_citations.py  # 确定性自检的测试向量（含反例）")
        print("!" * 74)
        return 2

    if "--probe" in sys.argv:
        return 0 if await probe(conf) else 1

    group = FaronAgentGroup(conf)
    print("\n已部署团队：")
    print(json.dumps(group.describe(), ensure_ascii=False, indent=2))

    print("\n" + "-" * 74)
    print("开始执行委托（流式输出）")
    print("-" * 74)

    chunks = 0
    try:
        async for chunk in group.run(COMMISSION):
            chunks += 1
            text = getattr(chunk, "content", None) or str(chunk)
            print(f"[{chunks:03d}] {text[:400]}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n运行中断：{type(exc).__name__}: {exc}")
        return 1

    print("-" * 74)
    print(f"完成，共收到 {chunks} 个流式分片。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
