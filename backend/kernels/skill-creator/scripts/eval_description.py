#!/usr/bin/env python3
"""
评估 Skill 描述字段的触发精度工具脚本。

本脚本来自 skill-creator 内核（openclaw-skill-creator），用于在沙盒测试阶段
验证生成的 Skill 的描述（description）字段是否能够以正确的精度触发 Agent。

使用方法：
    python3 eval_description.py --skill path/to/SKILL.md --evals path/to/evals.json [--output path/to/result.json]

evals.json 格式：
    [
        {"prompt": "帮我润色这段文字", "should_trigger": true},
        {"prompt": "今天天气怎么样", "should_trigger": false}
    ]

在沙盒自动化测试模式下（传入 --auto 参数），脚本会以非交互模式运行，
通过 AI 判断而非人工输入来评估每个测试用例，并将结果写入 --output 指定的文件。

注意：
    - 若不传 --output 参数，测试结果将打印到 stdout
    - 若不传 --auto 参数，脚本以交互模式运行（用于本地手动测试）
    - 评分标准：正确率 >= 80% 为通过，否则需要改进描述字段
"""

import argparse
import json
import sys
from pathlib import Path


def parse_skill_md(path: Path) -> dict:
    """
    解析 SKILL.md 文件，提取 frontmatter 中的 name 和 description 字段。

    Args:
        path: SKILL.md 文件路径

    Returns:
        包含 name 和 description 的字典
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {"name": path.parent.name, "description": ""}

    try:
        end = lines.index("---", 1)
    except ValueError:
        return {"name": path.parent.name, "description": ""}

    frontmatter = "\n".join(lines[1:end])
    name, description = "", ""
    for line in frontmatter.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return {"name": name, "description": description}


def run_eval_interactive(skill_path: Path, evals: list) -> dict:
    """
    以交互模式运行评估，每个测试用例需要人工判断 y/n。

    Args:
        skill_path: SKILL.md 文件路径
        evals: 测试用例列表

    Returns:
        包含评估结果的字典
    """
    skill = parse_skill_md(skill_path)
    print(f"\n{'='*60}")
    print(f"Skill: {skill['name']}")
    print(f"Description:\n  {skill['description']}")
    print(f"{'='*60}\n")
    print("For each prompt, enter y (would trigger) or n (would not trigger).\n")

    results = []
    for i, case in enumerate(evals, 1):
        prompt = case["prompt"]
        expected = case["should_trigger"]
        print(f"[{i}/{len(evals)}] Prompt: {prompt}")
        print(f"       Expected: {'TRIGGER' if expected else 'NO TRIGGER'}")

        while True:
            ans = input("       Your judgment (y/n): ").strip().lower()
            if ans in ("y", "n"):
                break

        actual = ans == "y"
        correct = actual == expected
        status = "✅ PASS" if correct else "❌ FAIL"
        print(f"       {status}\n")
        results.append({
            "prompt": prompt,
            "expected": expected,
            "actual": actual,
            "correct": correct,
        })

    return _build_report(skill, results)


def run_eval_auto(skill_path: Path, evals: list) -> dict:
    """
    以自动化模式运行评估，通过描述关键词匹配来判断触发性（非交互，适合沙盒环境）。

    自动模式的评估逻辑：
    - 将 Skill description 中的关键词与 prompt 进行语义相似度匹配
    - 使用简单的词汇重叠方法（适合沙盒环境，无需 AI 调用）
    - 对于高精度需求，建议在真实 Agent 环境中进行人工评估

    Args:
        skill_path: SKILL.md 文件路径
        evals: 测试用例列表

    Returns:
        包含评估结果的字典
    """
    skill = parse_skill_md(skill_path)
    description = skill.get("description", "").lower()

    # 提取描述中的关键词（去除常见停用词）
    stop_words = {
        "use", "when", "not", "for", "the", "a", "an", "and", "or", "to",
        "is", "it", "of", "in", "that", "this", "with", "as", "are", "was",
    }
    desc_words = set(w.strip(".,():") for w in description.split() if w.lower() not in stop_words)

    results = []
    for case in evals:
        prompt = case["prompt"]
        expected = case["should_trigger"]
        prompt_lower = prompt.lower()

        # 简单关键词匹配：prompt 中出现描述关键词则认为会触发
        overlap = sum(1 for w in desc_words if w in prompt_lower)
        actual = overlap >= 1  # 至少 1 个关键词命中则认为触发

        correct = actual == expected
        results.append({
            "prompt": prompt,
            "expected": expected,
            "actual": actual,
            "correct": correct,
            "keyword_overlap": overlap,
        })

    return _build_report(skill, results)


def _build_report(skill: dict, results: list) -> dict:
    """
    根据评估结果构建报告字典。

    Args:
        skill: 解析后的 skill 信息
        results: 每个测试用例的结果列表

    Returns:
        标准化的评估报告字典
    """
    passed = sum(1 for r in results if r["correct"])
    total = len(results)
    rate = passed / total if total > 0 else 0.0

    false_negatives = [r for r in results if not r["correct"] and not r["actual"]]
    false_positives = [r for r in results if not r["correct"] and r["actual"]]

    report = {
        "skill_name": skill.get("name", ""),
        "description": skill.get("description", ""),
        "total_cases": total,
        "passed_cases": passed,
        "trigger_accuracy": round(rate, 4),
        "passed": rate >= 0.8,
        "false_negatives": [r["prompt"] for r in false_negatives],
        "false_positives": [r["prompt"] for r in false_positives],
        "details": results,
    }

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"Skill: {skill.get('name', '')}")
    print(f"Results: {passed}/{total} ({rate*100:.0f}%)")
    if rate >= 0.8:
        print("✅ Description looks good!")
    else:
        print("⚠️  Below 80% — description needs improvement.")
        if false_negatives:
            print(f"\nFalse negatives (should trigger, didn't):")
            for p in [r["prompt"] for r in false_negatives]:
                print(f"  - {p}")
        if false_positives:
            print(f"\nFalse positives (shouldn't trigger, did):")
            for p in [r["prompt"] for r in false_positives]:
                print(f"  - {p}")
    print(f"{'='*60}\n")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="评估 Skill 描述字段的触发精度"
    )
    parser.add_argument("--skill", required=True, help="SKILL.md 文件路径")
    parser.add_argument("--evals", required=True, help="测试用例 JSON 文件路径")
    parser.add_argument("--output", default=None, help="结果输出 JSON 文件路径（可选）")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="自动化模式（非交互，适合沙盒环境）",
    )
    args = parser.parse_args()

    skill_path = Path(args.skill)
    evals_path = Path(args.evals)

    if not skill_path.exists():
        print(f"Error: {skill_path} not found", file=sys.stderr)
        sys.exit(1)

    if not evals_path.exists():
        print(f"Error: {evals_path} not found", file=sys.stderr)
        sys.exit(1)

    evals = json.loads(evals_path.read_text(encoding="utf-8"))

    if args.auto:
        report = run_eval_auto(skill_path, evals)
    else:
        report = run_eval_interactive(skill_path, evals)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已写入: {output_path}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # 根据测试是否通过设置退出码（沙盒测试时由调用方检查退出码）
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
