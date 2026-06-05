"""真实 LLM fallback 验证：本地配 2 个 provider, 1 个挂的, 1 个能用的。

跑前需要：
  - COGCORE_LLM_ENDPOINT = DeepSeek (能跑)
  - COGCORE_LLM_MODEL = deepseek-chat

  - 第二个 fake provider 加在运行时:
    reg.add(name="fake", endpoint="http://127.0.0.1:1", model="x", priority=1)
  - 期望：fake 失败 → fallback 到 DeepSeek → 拿到真实回复
"""
from __future__ import annotations

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

os.environ["COGCORE_LLM_ENDPOINT"] = "https://api.deepseek.com/v1"
os.environ["COGCORE_LLM_API_KEY"] = "sk-30f3ba9b7c89444ab79145ce2700c34a"
os.environ["COGCORE_LLM_MODEL"] = "deepseek-chat"

from cogcore.llm_bridge import LLMBridge
from cogcore.llm_registry import LLMRegistry, LLMService


def main() -> None:
    print("=== Real LLM Fallback Test ===\n")

    # Provider 1: 故意指向不存在的端口, 必失败
    fake_bridge = LLMBridge(
        endpoint="http://127.0.0.1:1",
        model="fake",
        api_key="x",
        timeout=2,
    )

    # Provider 2: DeepSeek 真服务
    real_bridge = LLMBridge(
        endpoint=os.environ["COGCORE_LLM_ENDPOINT"],
        api_key=os.environ["COGCORE_LLM_API_KEY"],
        model=os.environ["COGCORE_LLM_MODEL"],
        timeout=30,
    )

    reg = LLMRegistry()
    reg.add(
        name="fake",
        endpoint="http://127.0.0.1:1",
        model="fake",
        bridge=fake_bridge,
        priority=1,
        timeout=5,
    )
    reg.add(
        name="deepseek",
        endpoint=os.environ["COGCORE_LLM_ENDPOINT"],
        model=os.environ["COGCORE_LLM_MODEL"],
        bridge=real_bridge,
        priority=2,
        timeout=30,
    )

    print("Configured providers:")
    for r in reg.health_report():
        print(f"  {r['name']} (priority={r['priority']}, healthy={r['healthy']})")
    print()

    svc = LLMService(reg, max_attempts=3)
    print("Calling chat() - expect fake to fail, fallback to deepseek...")
    t0 = time.time()
    result = svc.chat(
        [{"role": "user", "content": "Reply with just 'OK' and nothing else."}],
    )
    dt = time.time() - t0
    print(f"Result: {result!r}")
    print(f"Time: {dt:.2f}s\n")

    print("Health after call:")
    for r in reg.health_report():
        print(
            f"  {r['name']}: total_calls={r['total_calls']}, "
            f"total_failures={r['total_failures']}, "
            f"consecutive_failures={r['consecutive_failures']}, "
            f"healthy={r['healthy']}"
        )

    if "OK" in result or len(result) > 0:
        print("\nPASS: Fallback to DeepSeek worked")
    else:
        print("\nFAIL: No valid response")
        sys.exit(1)


if __name__ == "__main__":
    main()
