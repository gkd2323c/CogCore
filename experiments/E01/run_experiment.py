"""E01 历史顺序改变后续同序输入的结构复用成本

HDB 实验：先送入同序/乱序序列建立历史，再用同序探针查询，
对比两种历史下的 match_score，计算存储优势。

运行：python experiments/E01/run_experiment.py
"""

import os
import json
import hashlib
from typing import Any

from cogcore.types import StimulusAtom, Modality, AtomEnergy, StimulusSource
from cogcore.hdb import HDB


def compute_sha256(filepath: str) -> str:
    """计算文件的 SHA-256 哈希值。"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def make_atoms(seq: str) -> list[StimulusAtom]:
    """将序列字符串转为 StimulusAtom 列表。

    seq: 如 "A B C D E"（空格分隔的单字符序列）。
    返回每个字符作为一个独立 StimulusAtom。
    """
    atoms: list[StimulusAtom] = []
    for ch in seq.split():
        atoms.append(
            StimulusAtom(
                content=ch,
                source=StimulusSource.EXTERNAL,
                modality=Modality.TEXT,
                energy=AtomEnergy(real=1.0, virtual=0.0),
                trace={"origin": "experiment"},
            )
        )
    return atoms


def run_case(
    first_order: str,
    second_order: str,
    probe_order: str,
    label: str,
) -> dict[str, Any]:
    """运行单个 case。

    返回含 match_score、structure_count 等信息的字典。
    """
    hdb = HDB()

    # 第一阶段：送入 first_order × 5
    atoms_first = make_atoms(first_order)
    for _ in range(5):
        hdb.lookup(atoms_first)

    # 第二阶段：送入 second_order × 5
    atoms_second = make_atoms(second_order)
    for _ in range(5):
        hdb.lookup(atoms_second)

    # 探针：同序序列
    probe_atoms = make_atoms(probe_order)
    result = hdb.lookup(probe_atoms)

    best_score = max(result.match_scores.values()) if result.match_scores else 0.0
    structure_count = len(hdb._structures)

    return {
        "label": label,
        "first_order": first_order,
        "second_order": second_order,
        "probe_order": probe_order,
        "match_score": best_score,
        "structure_count": structure_count,
        "matched_count": len(result.matched_structures),
        "new_structures_count": len(result.new_structures),
    }


def run_e01_experiment() -> None:
    print("=" * 60)
    print("E01: 历史顺序改变后续同序输入的结构复用成本")
    print("=" * 60)

    # 确保输出目录
    os.makedirs("experiments/E01/tables/source_tables", exist_ok=True)

    same_order = "A B C D E"
    reverse_order = "E D C B A"

    # Case 1: 同序→乱序→同序探针
    case1 = run_case(same_order, reverse_order, same_order, "Case1_同序→乱序")
    # Case 2: 乱序→同序→同序探针
    case2 = run_case(reverse_order, same_order, same_order, "Case2_乱序→同序")

    score_same_history = case2["match_score"]   # Case 2: 同序为最近历史
    score_reverse_history = case1["match_score"]  # Case 1: 乱序为最近历史

    storage_advantage = score_same_history / max(score_reverse_history, 0.01)

    print(f"\n{'Case':<25} {'match_score':>12} {'structures':>12}")
    print("-" * 52)
    print(f"{case1['label']:<25} {case1['match_score']:>12.4f} {case1['structure_count']:>12}")
    print(f"{case2['label']:<25} {case2['match_score']:>12.4f} {case2['structure_count']:>12}")
    print()
    print(f"Storage Advantage (同序 / 乱序): {storage_advantage:.4f}")
    print(f"Target: 2.300")
    print()

    # 汇总
    results = [case1, case2]
    target_value = 2.300

    passed = abs(storage_advantage - target_value) < 1e-5

    # 写 summary.json
    summary_data = {
        "metrics": {
            "case1_match_score": case1["match_score"],
            "case2_match_score": case2["match_score"],
            "storage_advantage": storage_advantage,
            "target": target_value,
            "passed": passed,
        },
        "cases": results,
    }
    with open("experiments/E01/tables/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    # 写 source_tables
    with open("experiments/E01/tables/source_tables/cases_detail.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # 写 design.md
    design_content = """# E01 历史顺序改变后续同序输入的结构复用成本

## 1. 机制预测与目标

HDB 应当对输入序列的顺序敏感：当历史中反复出现同序输入后，后续的同序探针能以更高的匹配分数复用已有结构；而当历史中混入乱序输入后，同序探针的结构复用效率下降。

预测：同序历史下的探针匹配分数应显著高于乱序历史下的探针匹配分数，量化为存储优势 = 同序历史 match_score / max(乱序历史 match_score, 0.01)，目标值 2.300。

## 2. 变量控制与对照系统

创建两对方向（两个 case）：
- **Case 1（同序→乱序）**：先送入同序序列 "A B C D E" × 5 建立结构，再送入乱序 "E D C B A" × 5 干扰，最后用同序探针 "A B C D E" 查询 match_score。
- **Case 2（乱序→同序）**：先送入乱序 × 5，再送入同序 × 5，最后用同序探针查询 match_score。

关键对照：两种 case 的唯一变量是"最近一段历史是同序还是乱序"，输入总量和内容完全相同。

## 3. 输入样本家族

| Case | 第一阶段（×5） | 第二阶段（×5） | 探针 | 含义 |
|------|--------------|--------------|------|------|
| Case 1 | A B C D E | E D C B A | A B C D E | 同序后受乱序干扰 |
| Case 2 | E D C B A | A B C D E | A B C D E | 乱序后受同序修正 |

Case 数：2。

## 4. 判据与指标

- **同序历史 match_score**：Case 2 的探针最佳匹配分数（同序为最近历史）
- **乱序历史 match_score**：Case 1 的探针最佳匹配分数（乱序为最近历史）
- **存储优势**：同序 match_score / max(乱序 match_score, 0.01)
- **目标值**：2.300

HDB 使用 2-gram 字符级 tokenization；序列以单字符原子送入后拼接为整体内容计算 token 重叠。
"""
    with open("experiments/E01/design.md", "w", encoding="utf-8") as f:
        f.write(design_content)

    # 写 report.md
    status_str = "通过" if passed else "未通过"
    report_content = f"""# E01 历史顺序改变后续同序输入的结构复用成本 — 实验终稿报告

## 一、运行结果汇总

| 指标 | 实测值 | 目标值 | 状态 |
|------|--------|--------|------|
| Case 1 match_score（乱序历史） | {case1['match_score']:.4f} | — | — |
| Case 2 match_score（同序历史） | {case2['match_score']:.4f} | — | — |
| **存储优势** | **{storage_advantage:.4f}** | **2.300** | **{status_str}** |

## 二、分支数据分析

1. **Case 1（同序→乱序→探针）**：
   先以同序 "A B C D E" × 5 建立结构，再以乱序 "E D C B A" × 5 干扰。探针 match_score = {case1['match_score']:.4f}。结构中存在 {case1['structure_count']} 个节点。

2. **Case 2（乱序→同序→探针）**：
   先以乱序 × 5，再以同序 × 5 修正。探针 match_score = {case2['match_score']:.4f}。

## 三、结论

{'存储优势达到目标值 2.300，实验通过。同序历史显著降低了结构复用成本。' if passed else '存储优势未达目标，当前 HDB 的 2-gram tokenization 对同序/乱序的敏感度不足以产生预期分化。需要增强 HDB 的顺序敏感匹配机制（如引入位置编码或 n-gram 跨原子连接）。'}
"""
    with open("experiments/E01/report.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    # 写 manifest.json
    manifest_data = {
        "experiment": "E01",
        "description": "Historical order impact on structural reuse cost",
        "files": {
            "tables/summary.json": {
                "sha256": compute_sha256("experiments/E01/tables/summary.json")
            },
            "design.md": {
                "sha256": compute_sha256("experiments/E01/design.md")
            },
            "report.md": {
                "sha256": compute_sha256("experiments/E01/report.md")
            },
        },
    }
    with open("experiments/E01/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    # 最终断言
    if passed:
        print("E01 PASS")
    else:
        print("E01 FAIL — storage advantage does not match target")
        assert passed, (
            f"Storage advantage {storage_advantage:.4f} != target {target_value}"
        )


if __name__ == "__main__":
    run_e01_experiment()
