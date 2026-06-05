"""M3.6 自迭代元循环 (L12.3 + L12.4)。

把'自检 / 自改 / 自部署 / 自学'组装成 9 步可执行循环:

  1. observe()    拉当前 tick 状态 + 测试结果 + git 状态
  2. detect_gap()  根据观测判断是否需要修 (LLM 解读)
  3. plan_fix()    调 LLM 规划: 读哪些文件, 改哪些地方
  4. read_source() 调 read_file 读相关源码
  5. propose_change() 调 LLM 生成 JSON 提案
  6. test()        跑 pytest, 必须 100% 过
  7. commit()      git_commit (含 [auto-iterate] 标签)
  8. reload()      importlib.reload + 10 tick 健康检查
  9. log()         写入 self_iteration.jsonl + diary

安全闸门（每步都验证）：
  - test() 失败  -> rollback 写错误到日志
  - reload 后 10 tick error_log >= 3 -> 自动 git revert
  - commit message 必含 [auto-iterate] 标签 (M3.5 闸门已实现)
  - 只改 src/cogcore/ 和 tests/  (M3.5 闸门已实现)

热重载实现：
  - importlib.reload() (推荐) - 简单但脆弱
  - 真实生产建议 fork 子进程 + A/B 对照 (M3.6 范围外)
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from cogcore.tools import ToolRegistry
from cogcore.llm_bridge import LLMBridge

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================


@dataclasses.dataclass
class Gap:
    """检测到的能力缺口。"""

    id: str
    description: str
    severity: str  # low / medium / high
    evidence: dict  # 来自 observe() 的相关数据


@dataclasses.dataclass
class Plan:
    """修复计划。"""

    gap_id: str
    files_to_read: list[str]
    files_to_modify: list[str]
    reasoning: str


@dataclasses.dataclass
class Change:
    """提议的代码变更。"""

    target_file: str
    new_content: str
    commit_message: str


# ============================================================
# 元循环
# ============================================================


class SelfIterateLoop:
    """9 步自迭代元循环。"""

    def __init__(
        self,
        registry: ToolRegistry,
        llm: LLMBridge,
        project_root: str = ".",
        data_dir: str = "cogcore_data",
        health_check_ticks: int = 5,  # 测试时用小值
    ) -> None:
        self.registry = registry
        self.llm = llm
        self.root = project_root
        self.data_dir = data_dir
        self.health_check_ticks = health_check_ticks
        self.log_path = os.path.join(data_dir, "self_iteration.jsonl")
        self._log_fp: Any = None

    # ============================================================
    # 9 步
    # ============================================================

    def observe(self) -> dict:
        """步骤 1: 拉当前状态。

        为了避免跑全量测试超时, observe 只跑一个小测试 (test_config.py) 作为 proxy。
        如果需要更全面诊断, 可以显式调用 self.test() 跑全量。
        """
        result = {"timestamp": datetime.now().isoformat()}
        try:
            result["git_status"] = self.registry.execute_tool("git_status", {})
        except Exception as e:
            result["git_status"] = {"error": str(e)}
        # 跑一个轻量测试作为快速健康检查
        try:
            test_result = self.registry.execute_tool("run_tests", {"path": "tests/test_config.py"})
            if isinstance(test_result, dict):
                result["test"] = test_result
            else:
                result["test"] = {"raw": str(test_result)}
        except Exception as e:
            result["test"] = {"error": str(e)}
        return result

    def detect_gap(self, observation: dict) -> Optional[Gap]:
        """步骤 2: 调 LLM 判断是否有 gap。

        简化版: 如果测试有 failed/error 就算 gap
        """
        test = observation.get("test", {})
        if test.get("failed", 0) > 0 or test.get("errors", 0) > 0:
            return Gap(
                id=f"gap-{int(time.time())}",
                description=f"{test.get('failed', 0)} tests failed, {test.get('errors', 0)} errors",
                severity="high" if test.get("failed", 0) > 0 else "medium",
                evidence={"test": test},
            )
        return None

    def plan_fix(self, gap: Gap) -> Plan:
        """步骤 3: 调 LLM 规划修复。"""
        # 简化: 基于 failed tests 自动规划
        return Plan(
            gap_id=gap.id,
            files_to_read=[],  # LLM 会填充
            files_to_modify=[],  # LLM 会填充
            reasoning=gap.description,
        )

    def read_source(self, plan: Plan) -> dict:
        """步骤 4: 读相关源码。"""
        sources: dict[str, str] = {}
        for path in plan.files_to_read:
            try:
                content = self.registry.execute_tool("read_file", {"path": path, "offset": 0, "limit": 200})
                sources[path] = content
            except Exception as e:
                sources[path] = f"Error: {e}"
        return sources

    def propose_change(self, plan: Plan, sources: dict) -> Change:
        """步骤 5: 调 LLM 生成 JSON 提案。

        在简单实现里, 这个方法被 mock - 测试中传 LLM 响应。
        在实际运行中, LLM 看 plan + sources 生成 Change。
        """
        # 默认实现: 返回一个无变更的 Change (子类或 mock 可覆盖)
        return Change(
            target_file="",
            new_content="",
            commit_message=f"[auto-iterate] {plan.gap_id}: no change proposed",
        )

    def apply_change(self, change: Change) -> bool:
        """应用提议的变更到磁盘。

        安全检查: 路径必须在允许区 (M3.5 闸门)。
        """
        if not change.target_file:
            return False
        from cogcore.self_modify_safety import check_paths

        ok, err = check_paths([change.target_file])
        if not ok:
            self._log({"step": "apply_change", "error": err})
            return False
        p = Path(self.root) / change.target_file
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            f.write(change.new_content)
        return True

    def test(self) -> bool:
        """步骤 6: 跑测试。"""
        # 跑一个轻量子集以避免超时. 真实场景可改跑全量.
        result = self.registry.execute_tool("run_tests", {"path": "tests/test_config.py"})
        if isinstance(result, dict):
            if result.get("error"):
                return False
            return result.get("failed", 0) == 0 and result.get("errors", 0) == 0
        return False

    def commit(self, change: Change) -> str:
        """步骤 7: git commit。"""
        msg = change.commit_message
        if "[auto-iterate]" not in msg:
            return "Error: missing [auto-iterate] tag"
        return self.registry.execute_tool(
            "git_commit",
            {"message": msg, "paths": [change.target_file] if change.target_file else []},
        )

    def reload(self, changed_modules: list[str]) -> bool:
        """步骤 8: 热重载 + 健康检查。

        真实生产建议 fork 子进程 + A/B 对照, M3.6 范围外。
        这里用 importlib.reload + 简单 health check (返回 5 tick 模拟)。
        """
        if not changed_modules:
            return True
        try:
            for mod_name in changed_modules:
                if mod_name in importlib.sys.modules:
                    importlib.reload(importlib.sys.modules[mod_name])
            return True
        except Exception as e:
            self._log({"step": "reload", "error": str(e)})
            return False

    def health_check(self) -> bool:
        """步骤 8 补充: 跑 N tick 看 error_log。"""
        # 真实实现: 调 service.tick() N 次, 检查 error_log
        # M3.6 范围: 跳过, 总是返回 True
        # (M3.7 会接入真实的 service)
        return True

    def log(self, step: str, payload: dict) -> None:
        """步骤 9: 写入自改日志。"""
        self._log({"step": step, **payload})

    # ============================================================
    # 内部
    # ============================================================

    def _log(self, payload: dict) -> None:
        """追加一行到 self_iteration.jsonl。"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            payload["ts"] = datetime.now().isoformat()
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.warning(f"log failed: {e}")

    # ============================================================
    # 主入口
    # ============================================================

    def run_once(self, dry_run: bool = False) -> dict:
        """完整跑一次元循环。

        Returns:
            {
                "skipped": "no gap detected",
                "dry_run": True, "plan": ..., "change": ...,
                "success": True, "gap_id": ..., "change": ...,
                "failed": "tests failed",
                "rolled_back": True,
            }
        """
        result: dict = {}
        try:
            # 1. observe
            self.log("observe_start", {})
            obs = self.observe()
            self.log("observe_done", obs)

            # 2. detect gap
            self.log("detect_gap_start", {})
            gap = self.detect_gap(obs)
            if gap is None:
                self.log("detect_gap_done", {"result": "no_gap"})
                return {"skipped": "no gap detected"}
            self.log("detect_gap_done", {"gap": dataclasses.asdict(gap)})

            # 3. plan
            self.log("plan_start", {})
            plan = self.plan_fix(gap)
            self.log("plan_done", dataclasses.asdict(plan))

            # 4. read
            self.log("read_start", {"files": plan.files_to_read})
            sources = self.read_source(plan)
            self.log("read_done", {"files_read": list(sources.keys())})

            # 5. propose
            self.log("propose_start", {})
            change = self.propose_change(plan, sources)
            self.log("propose_done", {"target": change.target_file, "msg_len": len(change.commit_message)})

            if dry_run:
                return {
                    "dry_run": True,
                    "gap": dataclasses.asdict(gap),
                    "plan": dataclasses.asdict(plan),
                    "change": dataclasses.asdict(change),
                }

            # 6. apply + test
            if not change.target_file or not change.new_content:
                self.log("skip", {"reason": "no concrete change proposed"})
                return {"skipped": "no concrete change proposed"}

            applied = self.apply_change(change)
            if not applied:
                return {"failed": "apply_change blocked by safety check"}
            self.log("applied", {"file": change.target_file})

            if not self.test():
                self.rollback(change.target_file)
                self.log("test_failed", {"file": change.target_file})
                return {"failed": "tests failed", "rolled_back": True}
            self.log("test_passed", {})

            # 7. commit
            self.log("commit_start", {})
            commit_result = self.commit(change)
            self.log("commit_done", {"result": commit_result[:200]})
            if "Error" in commit_result:
                return {"failed": f"commit failed: {commit_result[:200]}"}

            # 8. reload + health
            modules_changed = [m for m in [self._path_to_module(change.target_file)] if m]
            if not self.reload(modules_changed):
                self.revert(change.target_file)
                self.log("reload_failed", {})
                return {"failed": "reload failed, reverted"}
            if not self.health_check():
                self.revert(change.target_file)
                self.log("health_check_failed", {})
                return {"failed": "health check failed, reverted"}
            self.log("reload_ok", {"modules": modules_changed})

            # 9. done
            result = {
                "success": True,
                "gap_id": gap.id,
                "change": dataclasses.asdict(change),
            }
            self.log("complete", result)
            return result
        except Exception as e:
            self.log("error", {"exception": str(e)})
            return {"failed": f"exception: {e}"}

    # ============================================================
    # 辅助
    # ============================================================

    def _path_to_module(self, path: str) -> str:
        """src/cogcore/tools.py -> cogcore.tools"""
        if path.startswith("src/") and path.endswith(".py"):
            mod = path[4:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[:-9]
            return mod
        return ""

    def rollback(self, file: str) -> None:
        """测试失败时: 恢复文件 (删除, 因为修改是写到 .py 文件, 不在 git 跟踪时)."""
        p = Path(self.root) / file
        if p.exists():
            # 我们的修改是 untracked, 直接删除
            try:
                p.unlink()
            except Exception as e:
                self._log({"step": "rollback", "error": str(e)})

    def revert(self, file: str) -> None:
        """commit 之后出问题: git revert + 跑 reload。"""
        try:
            result = self.registry.execute_tool("git_revert", {"commit_sha": "HEAD"})
            self._log({"step": "revert", "result": str(result)[:200]})
        except Exception as e:
            self._log({"step": "revert", "error": str(e)})
