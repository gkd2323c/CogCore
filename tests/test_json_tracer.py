"""M4.3a JSON tracer 测试。

覆盖: TraceRecord, TraceWriter, JSONTracer (cm/decorator), 聚合, HTML viewer。
"""
from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from cogcore.json_tracer import (
    HTML_TEMPLATE,
    JSONTracer,
    TraceRecord,
    TraceWriter,
    aggregate_by_node,
    aggregate_by_thread,
    list_trace_files,
    read_traces,
    render_html,
    trace_node,
    write_html,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_traces_dir(tmp_path):
    return str(tmp_path / "traces")


# ============================================================
# TraceRecord
# ============================================================


def test_trace_record_basic():
    r = TraceRecord(node="n1", tick=1, thread_id="t-1", duration_ms=12.5)
    d = r.to_dict()
    assert d["node"] == "n1"
    assert d["tick"] == 1
    assert d["thread_id"] == "t-1"
    assert d["duration_ms"] == 12.5
    assert d["status"] == "ok"
    assert d["error"] is None
    assert "ts" in d
    assert d["sha256_input"] == ""  # 没设 input, 默认空
    assert d["sha256_output"] == ""


def test_trace_record_with_input_output():
    r = TraceRecord(
        node="n1",
        input_data={"x": 1, "y": "hello"},
        output_data=[1, 2, 3],
    )
    d = r.to_dict()
    assert len(d["sha256_input"]) == 64  # sha256 hex
    assert len(d["sha256_output"]) == 64
    assert d["input_size"] > 0
    assert d["output_size"] > 0


def test_trace_record_with_error():
    r = TraceRecord(node="n1", status="error", error="boom")
    assert r.to_dict()["status"] == "error"
    assert r.to_dict()["error"] == "boom"


def test_trace_record_with_extra():
    r = TraceRecord(node="n1", extra={"k": "v", "n": 42})
    d = r.to_dict()
    assert d["extra"] == {"k": "v", "n": 42}


# ============================================================
# TraceWriter
# ============================================================


def test_trace_writer_creates_file(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    r = TraceRecord(node="n1")
    w.write(r)
    w.close()
    files = list_trace_files(tmp_traces_dir)
    assert len(files) == 1
    # 检查文件可读且含 1 行
    with open(files[0]) as f:
        lines = f.readlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["node"] == "n1"


def test_trace_writer_appends(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    for i in range(5):
        w.write(TraceRecord(node=f"n{i}"))
    w.close()
    files = list_trace_files(tmp_traces_dir)
    with open(files[0]) as f:
        lines = f.readlines()
    assert len(lines) == 5


def test_trace_writer_thread_safe(tmp_traces_dir):
    """多线程写不损坏 JSONL."""
    import threading
    w = TraceWriter(base_dir=tmp_traces_dir)

    def worker(start):
        for i in range(start, start + 10):
            w.write(TraceRecord(node=f"n{i}"))

    threads = [threading.Thread(target=worker, args=(t * 100,)) for t in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    w.close()

    files = list_trace_files(tmp_traces_dir)
    with open(files[0]) as f:
        lines = f.readlines()
    assert len(lines) == 30
    # 全部能解析
    for line in lines:
        json.loads(line)


# ============================================================
# JSONTracer context manager
# ============================================================


def test_tracer_context_manager(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    with JSONTracer("n1", thread_id="t-1", tick=42, writer=w) as t:
        t.set_input({"x": 1})
        result = 1 + 1
        t.set_output(result)
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert len(records) == 1
    assert records[0]["node"] == "n1"
    assert records[0]["thread_id"] == "t-1"
    assert records[0]["tick"] == 42
    assert records[0]["status"] == "ok"
    assert len(records[0]["sha256_input"]) == 64
    assert len(records[0]["sha256_output"]) == 64


def test_tracer_captures_exception(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    with pytest.raises(ValueError):
        with JSONTracer("n1", writer=w) as t:
            raise ValueError("test error")
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert records[0]["status"] == "error"
    assert "ValueError" in records[0]["error"]
    assert "test error" in records[0]["error"]


def test_tracer_records_duration(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    with JSONTracer("n1", writer=w):
        time.sleep(0.05)  # 50ms
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert records[0]["duration_ms"] >= 50


def test_tracer_set_status(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    with JSONTracer("n1", writer=w) as t:
        t.set_status("warn", "non-fatal")
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert records[0]["status"] == "warn"
    assert records[0]["error"] == "non-fatal"


# ============================================================
# JSONTracer decorator
# ============================================================


def test_tracer_decorator(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    @JSONTracer.decorator(node="my_func", thread_id_arg="tid", tick_arg="tk", writer=w)
    def my_fn(x, y, tid=None, tk=None):
        return x + y

    result = my_fn(2, 3, tid="t-1", tk=99)
    assert result == 5
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert records[0]["node"] == "my_func"
    assert records[0]["thread_id"] == "t-1"
    assert records[0]["tick"] == 99


def test_tracer_trace_node_helper(tmp_traces_dir):
    """trace_node 装饰器 (更简单版本)."""
    w = TraceWriter(base_dir=tmp_traces_dir)

    @trace_node("stage_x")
    def my_stage(state):
        return {"ok": True}

    # 装饰器固定用默认 writer (写到 traces/) - 这里只验证装饰器可以工作
    out = my_stage({"k": 1})
    assert out == {"ok": True}
    # 清理 traces/ 副作用
    import shutil
    traces_default = "traces"
    if os.path.isdir(traces_default):
        for f in os.listdir(traces_default):
            if f.endswith(".jsonl"):
                # 只删今天的数据, 避免删其他文件
                from datetime import date
                if f.startswith(date.today().isoformat()):
                    os.unlink(os.path.join(traces_default, f))


# ============================================================
# Aggregation
# ============================================================


def test_aggregate_by_node():
    records = [
        {"node": "n1", "duration_ms": 10, "status": "ok"},
        {"node": "n1", "duration_ms": 20, "status": "ok"},
        {"node": "n1", "duration_ms": 30, "status": "error"},
        {"node": "n2", "duration_ms": 5, "status": "ok"},
    ]
    by = aggregate_by_node(records)
    assert by["n1"]["count"] == 3
    assert by["n1"]["errors"] == 1
    assert by["n1"]["mean_ms"] == 20.0
    assert by["n1"]["min_ms"] == 10.0
    assert by["n1"]["max_ms"] == 30.0
    assert by["n2"]["count"] == 1


def test_aggregate_by_thread():
    records = [
        {"node": "n1", "thread_id": "t-1", "status": "ok"},
        {"node": "n2", "thread_id": "t-1", "status": "ok"},
        {"node": "n1", "thread_id": "t-2", "status": "error"},
    ]
    by = aggregate_by_thread(records)
    assert by["t-1"]["count"] == 2
    assert "n1" in by["t-1"]["nodes"]
    assert "n2" in by["t-1"]["nodes"]
    assert by["t-2"]["count"] == 1
    assert by["t-2"]["errors"] == 1


# ============================================================
# read_traces filtering
# ============================================================


def test_read_traces_no_filter(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    for n in ("n1", "n2", "n1"):
        w.write(TraceRecord(node=n, thread_id="t-1"))
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0])
    assert len(records) == 3


def test_read_traces_filter_by_node(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    for n in ("n1", "n2", "n1"):
        w.write(TraceRecord(node=n, thread_id="t-1"))
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0], node="n1")
    assert len(records) == 2
    assert all(r["node"] == "n1" for r in records)


def test_read_traces_filter_by_status(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    w.write(TraceRecord(node="n1", status="ok"))
    w.write(TraceRecord(node="n2", status="error", error="x"))
    w.close()
    records = read_traces(list_trace_files(tmp_traces_dir)[0], status="error")
    assert len(records) == 1
    assert records[0]["status"] == "error"


# ============================================================
# HTML viewer
# ============================================================


def test_render_html_basic(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    w.write(TraceRecord(node="n1", thread_id="t-1", tick=1, duration_ms=10))
    w.write(TraceRecord(node="n2", thread_id="t-1", tick=1, duration_ms=20, status="error", error="boom"))
    w.close()
    path = list_trace_files(tmp_traces_dir)[0]
    html = render_html(path)
    assert "<!DOCTYPE html>" in html
    assert "CogCore Trace" in html
    assert "n1" in html
    assert "n2" in html
    assert "boom" in html
    assert "Records:" in html


def test_render_html_empty(tmp_traces_dir):
    """空文件应该返回合理的 HTML."""
    os.makedirs(tmp_traces_dir, exist_ok=True)
    fake_path = os.path.join(tmp_traces_dir, "empty.jsonl")
    with open(fake_path, "w"):
        pass
    html = render_html(fake_path)
    assert "Empty trace" in html


def test_write_html_creates_file(tmp_traces_dir):
    w = TraceWriter(base_dir=tmp_traces_dir)
    w.write(TraceRecord(node="n1"))
    w.close()
    trace_path = list_trace_files(tmp_traces_dir)[0]
    html_path = write_html(trace_path)
    assert os.path.exists(html_path)
    assert html_path.endswith(".html")
    with open(html_path, encoding="utf-8") as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content


# ============================================================
# 集成测试: 模拟跑 50 tick
# ============================================================


def test_integration_50_records(tmp_traces_dir):
    """模拟 50 tick, 每 tick 跑 10 stage, 验证每节点都有 trace."""
    w = TraceWriter(base_dir=tmp_traces_dir)
    nodes = [f"stage_{i}" for i in range(1, 11)]
    for tick in range(50):
        for n in nodes:
            t = JSONTracer(n, thread_id=f"t-{tick % 3}", tick=tick, writer=w)
            with t:
                t.set_input({"tick": tick})
                t.set_output({"processed": True})
    w.close()
    path = list_trace_files(tmp_traces_dir)[0]
    records = read_traces(path)
    # 50 * 10 = 500
    assert len(records) == 500
    by = aggregate_by_node(records)
    assert len(by) == 10
    for n in nodes:
        assert by[n]["count"] == 50
