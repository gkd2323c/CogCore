"""M4.3a JSON trace viewer CLI。

零依赖, 纯 stdlib, 读 JSONL 输出 HTML。

用法:
    python scripts/trace_viewer.py                       # 最新一天的 trace
    python scripts/trace_viewer.py --date 2026-06-06    # 指定日期
    python scripts/trace_viewer.py --file traces/x.jsonl # 指定文件
    python scripts/trace_viewer.py --open                # 自动在浏览器打开
    python scripts/trace_viewer.py --node stage_5        # 只看一个 node
    python scripts/trace_viewer.py --thread t-1          # 只看一个 thread
    python scripts/trace_viewer.py --status error        # 只看 error
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cogcore.json_tracer import (
    HTML_TEMPLATE,
    TraceWriter,
    list_trace_files,
    read_traces,
    render_html,
    write_html,
)


def find_latest_trace() -> str | None:
    files = list_trace_files("traces")
    if not files:
        return None
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="CogCore JSON trace viewer")
    parser.add_argument("--file", help="trace 文件路径 (默认找 traces/ 最新)")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD (会自动找 traces/YYYY-MM-DD.jsonl)")
    parser.add_argument("--node", help="只看一个 node (过滤)")
    parser.add_argument("--thread", help="只看一个 thread (过滤)")
    parser.add_argument("--status", help="只看一个 status (ok / error)")
    parser.add_argument("--out", help="输出 HTML 路径 (默认 .html 与 trace 同名)")
    parser.add_argument("--open", action="store_true", help="浏览器自动打开")
    parser.add_argument("--markdown", action="store_true", help="输出 markdown 报告而非 HTML")
    args = parser.parse_args()

    # 决定 trace 文件
    trace_path = args.file
    if not trace_path and args.date:
        trace_path = os.path.join("traces", f"{args.date}.jsonl")
    if not trace_path:
        trace_path = find_latest_trace()
    if not trace_path or not os.path.exists(trace_path):
        print(f"[!] 没找到 trace 文件: {trace_path}", file=sys.stderr)
        return 1

    print(f"[*] reading: {trace_path}", file=sys.stderr)
    records = read_traces(
        trace_path,
        node=args.node,
        thread_id=args.thread,
        status=args.status,
    )
    print(f"[*] matched {len(records)} records", file=sys.stderr)

    if args.markdown:
        from cogcore.json_tracer import aggregate_by_node
        by_node = aggregate_by_node(records)
        print(f"# Trace 报告 — {os.path.basename(trace_path)}")
        print()
        print(f"- **Records**: {len(records)}")
        if records:
            threads = sorted({r.get('thread_id', '?') for r in records if r.get('thread_id')})
            print(f"- **Threads**: {len(threads)}")
            print(f"- **Nodes**: {len(by_node)}")
            print(f"- **Errors**: {sum(1 for r in records if r.get('status') == 'error')}")
            print()
            print("## By node")
            print()
            print("| Node | Count | Mean (ms) | Min | Max | Errors |")
            print("|------|-------|-----------|-----|-----|--------|")
            for n, s in sorted(by_node.items()):
                print(f"| `{n}` | {s['count']} | {s.get('mean_ms', 0):.2f} | "
                      f"{s.get('min_ms', 0):.2f} | {s.get('max_ms', 0):.2f} | {s['errors']} |")
        return 0

    # HTML 输出
    html = render_html(trace_path, records)
    out_path = args.out or str(Path(trace_path).with_suffix(".html"))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[+] HTML 写入: {out_path}", file=sys.stderr)

    if args.open:
        url = "file://" + os.path.abspath(out_path)
        webbrowser.open(url)
        print(f"[+] 浏览器打开: {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
