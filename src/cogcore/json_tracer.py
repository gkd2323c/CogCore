"""M4.3a JSON trace (L8)。

为每个 graph 节点 / LLM 调用写入 trace JSONL。

设计:
  - JSONTracer(path, node_name): context manager + decorator
  - 写入 traces/YYYY-MM-DD.jsonl, 每行:
    {ts, tick, node, thread_id, duration_ms, status, error?, sha256_input, sha256_output}
  - SHA-256 校验输入/输出 (论文 5.6.1 白箱追溯)
  - 不引入 Langfuse / Prom / Grafana
  - 用 stdlib json + hashlib, 零外部依赖
  - thread_safe (用文件锁)
"""
from __future__ import annotations

import contextlib
import datetime
import functools
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================


class TraceRecord:
    """单条 trace 记录。"""

    def __init__(
        self,
        node: str,
        *,
        thread_id: str | None = None,
        tick: int | None = None,
        input_data: Any = None,
        output_data: Any = None,
        duration_ms: float = 0.0,
        status: str = "ok",
        error: str | None = None,
        extra: dict | None = None,
    ) -> None:
        self.ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.tick = tick
        self.node = node
        self.thread_id = thread_id
        self.duration_ms = duration_ms
        self.status = status
        self.error = error
        self.sha256_input = self._hash(input_data)
        self.sha256_output = self._hash(output_data)
        self.input_size = self._size(input_data)
        self.output_size = self._size(output_data)
        self.extra = extra or {}

    @staticmethod
    def _hash(data: Any) -> str:
        if data is None:
            return ""
        try:
            s = json.dumps(data, default=str, sort_keys=True, ensure_ascii=False)
        except Exception:
            s = repr(data)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    @staticmethod
    def _size(data: Any) -> int:
        if data is None:
            return 0
        try:
            return len(json.dumps(data, default=str, ensure_ascii=False))
        except Exception:
            return len(repr(data))

    def to_dict(self) -> dict:
        d = {
            "ts": self.ts,
            "node": self.node,
            "thread_id": self.thread_id,
            "tick": self.tick,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error": self.error,
            "sha256_input": self.sha256_input,
            "sha256_output": self.sha256_output,
            "input_size": self.input_size,
            "output_size": self.output_size,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


# ============================================================
# 文件写入
# ============================================================


class TraceWriter:
    """线程安全的 JSONL 写入器。"""

    def __init__(self, base_dir: str = "traces") -> None:
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._fp = None
        self._current_date = None

    def _path_for_date(self, date: datetime.date) -> str:
        return os.path.join(self.base_dir, f"{date.isoformat()}.jsonl")

    def _open(self, path: str) -> None:
        if self._fp and not self._fp.closed:
            if self._fp.name == path:
                return
            self._fp.close()
        self._fp = open(path, "a", encoding="utf-8")

    def write(self, record: TraceRecord) -> None:
        """追加一条记录。"""
        today = datetime.date.today()
        path = self._path_for_date(today)
        line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            if self._current_date != today:
                self._open(path)
                self._current_date = today
            self._fp.write(line)
            self._fp.flush()

    def close(self) -> None:
        with self._lock:
            if self._fp and not self._fp.closed:
                self._fp.close()
                self._fp = None
                self._current_date = None


# ============================================================
# Tracer (高层)
# ============================================================


class JSONTracer:
    """trace 上下文管理器 + 装饰器。

    用法 1: context manager
        tracer = JSONTracer("stage_5_cfs_evaluate")
        with tracer(thread_id="t-1", tick=42) as t:
            t.set_input(state_dict)
            result = do_work()
            t.set_output(result)

    用法 2: 装饰器
        @JSONTracer.decorator(node_name="llm_call", node="llm")
        def chat(prompt):
            return call_llm(prompt)

    用法 3: 简单包装
        with JSONTracer("node_x", thread_id="t-1") as t:
            ...
    """

    def __init__(
        self,
        node: str,
        *,
        thread_id: str | None = None,
        tick: int | None = None,
        writer: TraceWriter | None = None,
    ) -> None:
        self.node = node
        self.thread_id = thread_id
        self.tick = tick
        self.writer = writer or TraceWriter()
        self._input: Any = None
        self._output: Any = None
        self._extra: dict = {}
        self._t0: float = 0.0
        self._error: str | None = None
        self._status: str = "ok"

    def set_input(self, data: Any) -> None:
        self._input = data

    def set_output(self, data: Any) -> None:
        self._output = data

    def set_extra(self, key: str, value: Any) -> None:
        self._extra[key] = value

    def set_status(self, status: str, error: str | None = None) -> None:
        self._status = status
        self._error = error

    def __enter__(self) -> "JSONTracer":
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.time() - self._t0) * 1000
        status = self._status
        error = self._error
        if exc_type is not None:
            status = "error"
            error = f"{exc_type.__name__}: {exc_val}"
        record = TraceRecord(
            node=self.node,
            thread_id=self.thread_id,
            tick=self.tick,
            input_data=self._input,
            output_data=self._output,
            duration_ms=duration_ms,
            status=status,
            error=error,
            extra=self._extra or None,
        )
        try:
            self.writer.write(record)
        except Exception as e:
            logger.warning(f"trace write failed: {e}")

    @staticmethod
    def decorator(
        node: str,
        *,
        thread_id_arg: str | None = "thread_id",
        tick_arg: str | None = "tick",
        writer: TraceWriter | None = None,
    ) -> Callable:
        """把函数包成自动 trace 的版本。

        Args:
            node: 节点名
            thread_id_arg: 从 kwargs 里取 thread_id 的 key (None 表示不取)
            tick_arg: 从 kwargs 里取 tick 的 key
        """
        _writer = writer or TraceWriter()

        def deco(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs) -> Any:
                tid = kwargs.get(thread_id_arg) if thread_id_arg else None
                tk = kwargs.get(tick_arg) if tick_arg else None
                tracer = JSONTracer(node, thread_id=tid, tick=tk, writer=_writer)
                with tracer:
                    tracer.set_input({"args": args, "kwargs": kwargs})
                    result = fn(*args, **kwargs)
                    tracer.set_output(result)
                    return result

            return wrapper

        return deco


# ============================================================
# 聚合查询
# ============================================================


def list_trace_files(base_dir: str = "traces") -> list[str]:
    """列出所有 trace 文件。"""
    if not os.path.isdir(base_dir):
        return []
    return sorted(
        os.path.join(base_dir, f) for f in os.listdir(base_dir) if f.endswith(".jsonl")
    )


def read_traces(
    path: str,
    *,
    node: str | None = None,
    thread_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """读 trace 文件, 可选过滤。"""
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if node and rec.get("node") != node:
                continue
            if thread_id and rec.get("thread_id") != thread_id:
                continue
            if status and rec.get("status") != status:
                continue
            out.append(rec)
    return out


def aggregate_by_node(records: list[dict]) -> dict[str, dict]:
    """按 node 聚合: count / mean duration / error count. 返回 {node: stats}."""
    out: dict[str, dict] = {}
    for r in records:
        n = r.get("node", "?")
        s = out.setdefault(n, {"count": 0, "errors": 0, "total_ms": 0.0, "min_ms": float("inf"), "max_ms": 0.0})
        s["count"] += 1
        s["total_ms"] += r.get("duration_ms", 0)
        s["min_ms"] = min(s["min_ms"], r.get("duration_ms", 0))
        s["max_ms"] = max(s["max_ms"], r.get("duration_ms", 0))
        if r.get("status") == "error":
            s["errors"] += 1
    for n, s in out.items():
        if s["count"]:
            s["mean_ms"] = round(s["total_ms"] / s["count"], 3)
            s["min_ms"] = round(s["min_ms"], 3) if s["min_ms"] != float("inf") else 0
            s["max_ms"] = round(s["max_ms"], 3)
        s.pop("total_ms", None)
    return out


def aggregate_by_thread(records: list[dict]) -> dict[str, dict]:
    """按 thread_id 聚合."""
    out: dict[str, dict] = {}
    for r in records:
        t = r.get("thread_id", "?") or "?"
        s = out.setdefault(t, {"count": 0, "errors": 0, "nodes": set()})
        s["count"] += 1
        s["nodes"].add(r.get("node", "?"))
        if r.get("status") == "error":
            s["errors"] += 1
    for t, s in out.items():
        s["nodes"] = sorted(s["nodes"])
    return out


# ============================================================
# HTML viewer (零依赖)
# ============================================================


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>CogCore Trace — {filename}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; color: #222; }}
  h1 {{ font-size: 1.4em; }}
  h2 {{ font-size: 1.1em; margin-top: 1.5em; }}
  .stats {{ background: #f6f8fa; padding: 12px; border-radius: 6px;
            margin-bottom: 1em; }}
  .stats code {{ background: #e1e4e8; padding: 2px 6px; border-radius: 3px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
  th, td {{ border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }}
  th {{ background: #f6f8fa; font-weight: 600; }}
  tr.error {{ background: #ffeef0; }}
  tr.warn {{ background: #fff8c5; }}
  .ok {{ color: #1a7f37; font-weight: 600; }}
  .err {{ color: #cf222e; font-weight: 600; }}
  .mono {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 0.85em; }}
  .footer {{ color: #6e7781; margin-top: 2em; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>CogCore Trace — {filename}</h1>
<div class="stats">
  <strong>Records:</strong> {total} &nbsp;
  <strong>Threads:</strong> {threads} &nbsp;
  <strong>Nodes:</strong> {nodes} &nbsp;
  <strong>Errors:</strong> <span class="{err_class}">{errors}</span> &nbsp;
  <strong>Total duration:</strong> {total_ms:.1f} ms
</div>

<h2>By node</h2>
<table>
  <tr><th>Node</th><th>Count</th><th>Mean (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>Errors</th></tr>
{node_rows}
</table>

<h2>Records</h2>
<table>
  <tr><th>TS</th><th>Node</th><th>Thread</th><th>Tick</th><th>Status</th><th>Duration (ms)</th><th>sha256 (in→out)</th><th>Error</th></tr>
{record_rows}
</table>

<p class="footer">Generated by CogCore JSON tracer — {generated_at}</p>
</body>
</html>
"""


def render_html(path: str, records: list[dict] | None = None) -> str:
    """把 trace 文件渲染成 HTML。零依赖。"""
    if records is None:
        records = read_traces(path)
    if not records:
        return f"<html><body><h1>Empty trace: {os.path.basename(path)}</h1></body></html>"

    by_node = aggregate_by_node(records)
    threads = sorted({r.get("thread_id", "?") for r in records if r.get("thread_id")})
    nodes = sorted(by_node.keys())
    errors = sum(1 for r in records if r.get("status") == "error")
    total_ms = sum(r.get("duration_ms", 0) for r in records)

    node_rows_html = "\n".join(
        f"<tr><td class='mono'>{n}</td><td>{s['count']}</td><td>{s.get('mean_ms', 0):.2f}</td>"
        f"<td>{s.get('min_ms', 0):.2f}</td><td>{s.get('max_ms', 0):.2f}</td>"
        f"<td>{s['errors']}</td></tr>"
        for n, s in sorted(by_node.items())
    )

    record_rows = []
    for r in records:
        cls = "error" if r.get("status") == "error" else ""
        status_class = "err" if r.get("status") == "error" else "ok"
        sh_in = r.get("sha256_input", "")[:10]
        sh_out = r.get("sha256_output", "")[:10]
        record_rows.append(
            f"<tr class='{cls}'><td class='mono'>{r.get('ts', '')}</td>"
            f"<td class='mono'>{r.get('node', '')}</td>"
            f"<td class='mono'>{r.get('thread_id', '')}</td>"
            f"<td>{r.get('tick', '')}</td>"
            f"<td class='{status_class}'>{r.get('status', '')}</td>"
            f"<td>{r.get('duration_ms', 0):.2f}</td>"
            f"<td class='mono'>{sh_in}...{sh_out}...</td>"
            f"<td>{r.get('error') or ''}</td></tr>"
        )
    record_rows_html = "\n".join(record_rows)
    err_class = "err" if errors > 0 else "ok"
    return HTML_TEMPLATE.format(
        filename=os.path.basename(path),
        total=len(records),
        threads=len(threads),
        nodes=len(nodes),
        errors=errors,
        err_class=err_class,
        total_ms=total_ms,
        node_rows=node_rows_html,
        record_rows=record_rows_html,
        generated_at=datetime.datetime.now().isoformat(),
    )


def write_html(path: str, html_path: str | None = None) -> str:
    """渲染并写 HTML 文件. 返回 HTML 路径."""
    html = render_html(path)
    if html_path is None:
        html_path = str(Path(path).with_suffix(".html"))
    Path(html_path).parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


# ============================================================
# 工具: 装饰 node 函数的辅助
# ============================================================


def trace_node(
    node: str,
    *,
    thread_id: str | None = None,
    tick: int | None = None,
) -> Callable:
    """更简单的装饰器, 适合给 stage 节点用。"""
    tracer = JSONTracer(node, thread_id=thread_id, tick=tick)

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            t = JSONTracer(node, thread_id=thread_id, tick=tick)
            with t:
                t.set_input({"args_count": len(args), "kwargs_keys": list(kwargs.keys())})
                result = fn(*args, **kwargs)
                # 不存 result (state 太大), 只存类型
                t.set_output({"type": type(result).__name__})
                return result

        return wrapper

    return deco
