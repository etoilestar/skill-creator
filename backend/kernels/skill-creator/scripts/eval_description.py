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
import re
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


def _extract_tokens(text: str) -> set:
    """
    从文本中提取有效的匹配 token 集合，同时支持英文单词和中文字符。

    策略：
    - 英文：按单词拆分，去除停用词和单字符词
    - 中文：提取 CJK 字符，只生成双字 bigram（不保留单字）

    只用 bigram 而不保留单字的原因：
    - 单个汉字语义模糊（如"件""帮""用"出现在大量不相关词汇中），
      保留单字会引入大量误触发（false positive）。
    - bigram 组合包含足够的语义信息（如"创建""技能""文件"），
      精度远优于单字匹配。
    - 无需安装 jieba 等分词库，可在纯标准库的沙盒环境中运行。

    Args:
        text: 待提取的原始文本

    Returns:
        token 字符串集合
    """
    # 英文停用词
    en_stop = {
        "use", "when", "not", "for", "the", "a", "an", "and", "or", "to",
        "is", "it", "of", "in", "that", "this", "with", "as", "are", "was",
        "i", "you", "he", "she", "we", "they", "do", "be", "have", "has",
        "by", "at", "on", "if", "so", "but", "can", "will", "user", "users",
        "want", "wants", "need", "needs", "help", "me", "my",
    }
    # 中文停用词组（用于过滤低语义 bigram）
    zh_stop_bigrams = {
        "什么", "怎么", "哪里", "一个", "一些", "一下", "可以", "没有",
        "的话", "一样", "这个", "那个", "这种", "那种", "如果", "因为",
        "所以", "但是", "然后", "还有", "还是", "或者", "以及", "之后",
    }

    tokens: set = set()

    # --- 英文单词 token ---
    for w in re.findall(r'[a-z]+', text.lower()):
        if w not in en_stop and len(w) > 1:
            tokens.add(w)

    # --- 中文 bigram token（只用 bigram，不用单字）---
    cjk_chars = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text)
    for i in range(len(cjk_chars) - 1):
        bigram = cjk_chars[i] + cjk_chars[i + 1]
        if bigram not in zh_stop_bigrams:
            tokens.add(bigram)

    return tokens


def _overlap_score(desc_tokens: set, prompt_tokens: set) -> float:
    """
    计算描述 token 集与 prompt token 集的重叠系数（Overlap Coefficient）。

    重叠系数 = |A ∩ B| / min(|A|, |B|)

    使用重叠系数而非 Jaccard：
    - 当 prompt 很短（用户常见），分母取较小集的大小，
      避免因 prompt 词少而使 Jaccard 虚低。

    Args:
        desc_tokens: 从 description 提取的 token 集
        prompt_tokens: 从 prompt 提取的 token 集

    Returns:
        0.0 ~ 1.0 之间的相似度得分
    """
    if not desc_tokens or not prompt_tokens:
        return 0.0
    intersection = desc_tokens & prompt_tokens
    return len(intersection) / min(len(desc_tokens), len(prompt_tokens))


# 触发判定阈值：重叠系数 >= 此值则认为 prompt 会触发该 Skill
# 经验值 0.15：对于 10 个描述关键词，只需 1-2 个出现在 prompt 中即可
_TRIGGER_THRESHOLD = 0.15


def run_eval_auto(skill_path: Path, evals: list) -> dict:
    """
    以自动化模式运行评估，通过 token 重叠得分判断触发性（非交互，适合沙盒环境）。

    自动模式的评估逻辑：
    - 同时支持英文单词和中文字符（单字 + bigram）的 token 提取
    - 使用归一化重叠系数替代原始计数阈值，消除描述长度影响
    - 无需安装 jieba 等分词库，可在标准 Python 环境中运行

    Args:
        skill_path: SKILL.md 文件路径
        evals: 测试用例列表

    Returns:
        包含评估结果的字典
    """
    skill = parse_skill_md(skill_path)
    description = skill.get("description", "")
    desc_tokens = _extract_tokens(description)

    results = []
    for case in evals:
        prompt = case["prompt"]
        expected = case["should_trigger"]

        prompt_tokens = _extract_tokens(prompt)
        score = _overlap_score(desc_tokens, prompt_tokens)
        actual = score >= _TRIGGER_THRESHOLD

        correct = actual == expected
        results.append({
            "prompt": prompt,
            "expected": expected,
            "actual": actual,
            "correct": correct,
            "overlap_score": round(score, 4),
        })

    return _build_report(skill, results)


def run_eval_llm(skill_path: Path, evals: list) -> dict:
    """
    以 LLM 裁判模式运行评估。

    通过 LLM API 判断每个 prompt 是否会触发该 Skill，
    适合需要语义级判断（而非关键词匹配）的高精度场景。

    依赖环境变量（均在容器启动时通过 -e 注入）：
        LLM_API_KEY   : LLM API 密钥（必填）
        LLM_BASE_URL  : API 基础 URL（可选，默认 OpenAI 官方地址）
        LLM_MODEL     : 模型名称（可选，默认 gpt-4o-mini）

    如果 openai 库不可用或 LLM 调用失败，自动 fallback 到 run_eval_auto()。

    Args:
        skill_path: SKILL.md 文件路径
        evals: 测试用例列表

    Returns:
        包含评估结果的字典（格式与 run_eval_auto 完全一致）
    """
    import os

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        print("[llm-judge] LLM_API_KEY 未设置，fallback 到 auto 模式", file=sys.stderr)
        return run_eval_auto(skill_path, evals)

    skill = parse_skill_md(skill_path)
    description = skill.get("description", "")

    def _ask_llm(prompt_text: str) -> bool:
        """调用 LLM 判断 prompt 是否会触发该 Skill，返回布尔值。"""
        user_content = (
            f"以下是一个 Skill 的描述：\n{description}\n\n"
            f"用户输入：{prompt_text}\n\n"
            "该用户输入是否会触发这个 Skill？只回答 yes 或 no。"
        )
        # 优先使用 openai 库
        try:
            import openai  # noqa: PLC0415
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = openai.OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=5,
                temperature=0,
            )
            answer = (response.choices[0].message.content or "").strip().lower()
            return answer.startswith("y")
        except ImportError:
            pass  # openai 不可用，fallback 到 http.client

        # Fallback：使用标准库 http.client，兼容纯 stdlib 的沙盒环境
        import http.client
        import json as _json
        import ssl
        import urllib.parse

        url = base_url or "https://api.openai.com"
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc or parsed.path  # 处理仅填 host 的情况
        path_prefix = parsed.path.rstrip("/")

        payload = _json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": 5,
            "temperature": 0,
        }).encode("utf-8")

        try:
            conn = http.client.HTTPSConnection(host, context=ssl.create_default_context())
            conn.request(
                "POST",
                f"{path_prefix}/v1/chat/completions",
                body=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp = conn.getresponse()
            data = _json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip().lower()
            return answer.startswith("y")
        except Exception:
            raise  # 由外层捕获

    results = []
    fallback_triggered = False
    for case in evals:
        prompt_text = case["prompt"]
        expected = case["should_trigger"]
        try:
            actual = _ask_llm(prompt_text)
        except Exception as exc:
            print(f"[llm-judge] LLM 调用失败：{exc}，fallback 到 auto 模式", file=sys.stderr)
            fallback_triggered = True
            break
        correct = actual == expected
        results.append({
            "prompt": prompt_text,
            "expected": expected,
            "actual": actual,
            "correct": correct,
        })

    if fallback_triggered:
        return run_eval_auto(skill_path, evals)

    return _build_report(skill, results)



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
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        dest="llm_judge",
        help="LLM 裁判模式（使用 LLM API 进行语义级判断，需要设置 LLM_API_KEY 环境变量）",
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

    if args.llm_judge:
        report = run_eval_llm(skill_path, evals)
    elif args.auto:
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
