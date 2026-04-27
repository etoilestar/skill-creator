"""
backend/app/services/skill_index_service.py

Skill 索引与检索服务。

职责：
    - 扫描指定目录，建立所有 SKILL.md 的内存索引
    - 根据用户查询文本，返回最匹配的 Skill 列表（BM25-like 关键词评分）
    - 支持同时索引多个根目录（全局 kernels 目录 + 用户工作区目录）
    - 测试时暴露多 Skill 竞争结果，帮助验证 description 的区分度

算法说明：
    使用与 eval_description.py 相同的 token 提取策略（英文单词 + 中文字符/bigram），
    通过重叠系数（Overlap Coefficient）计算 query 和每个 Skill description 的相似度，
    返回按得分降序排列的 Skill 列表。

    无外部依赖，兼容沙盒和生产环境。

使用示例：
    service = SkillIndexService()
    service.index_directory("/app/workspace/task-001/my-skill")
    results = service.search("帮我创建一个处理 PDF 的技能", top_k=5)
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Token 提取工具（与 eval_description.py 保持一致）
# ---------------------------------------------------------------------------

_EN_STOP = {
    "use", "when", "not", "for", "the", "a", "an", "and", "or", "to",
    "is", "it", "of", "in", "that", "this", "with", "as", "are", "was",
    "i", "you", "he", "she", "we", "they", "do", "be", "have", "has",
    "by", "at", "on", "if", "so", "but", "can", "will", "user", "users",
    "want", "wants", "need", "needs", "help", "me", "my",
}

# 低语义 bigram 停用词（不应作为匹配依据的常见词组）
_ZH_STOP_BIGRAMS = {
    "什么", "怎么", "哪里", "一个", "一些", "一下", "可以", "没有",
    "的话", "一样", "这个", "那个", "这种", "那种", "如果", "因为",
    "所以", "但是", "然后", "还有", "还是", "或者", "以及", "之后",
}


def _extract_tokens(text: str) -> set:
    """
    从文本中提取有效的匹配 token 集合，同时支持英文单词和中文字符。

    策略：
    - 英文：按单词拆分，去除停用词和单字符词
    - 中文：只提取双字 bigram，不保留单字（单字语义模糊，易引起误匹配）

    与 eval_description.py 保持完全一致的算法，确保测试和检索结果的一致性。

    Args:
        text: 待提取的原始文本

    Returns:
        token 字符串集合
    """
    tokens: set = set()

    # 英文单词
    for w in re.findall(r'[a-z]+', text.lower()):
        if w not in _EN_STOP and len(w) > 1:
            tokens.add(w)

    # 中文 bigram（只用 bigram，不用单字）
    cjk_chars = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text)
    for i in range(len(cjk_chars) - 1):
        bigram = cjk_chars[i] + cjk_chars[i + 1]
        if bigram not in _ZH_STOP_BIGRAMS:
            tokens.add(bigram)

    return tokens


def _overlap_score(desc_tokens: set, query_tokens: set) -> float:
    """
    计算重叠系数：|A ∩ B| / min(|A|, |B|)

    Args:
        desc_tokens: Skill description 的 token 集
        query_tokens: 查询文本的 token 集

    Returns:
        0.0 ~ 1.0 之间的相似度得分
    """
    if not desc_tokens or not query_tokens:
        return 0.0
    return len(desc_tokens & query_tokens) / min(len(desc_tokens), len(query_tokens))


# ---------------------------------------------------------------------------
# SkillIndexService
# ---------------------------------------------------------------------------


class SkillEntry:
    """
    Skill 索引条目，存储单个 Skill 的元数据和 token 集。

    Attributes:
        name: Skill 名称（来自 frontmatter name 字段）
        description: Skill 描述（来自 frontmatter description 字段）
        skill_path: SKILL.md 的绝对路径
        tokens: 从 description 预先提取的 token 集（用于快速检索）
    """

    __slots__ = ("name", "description", "skill_path", "tokens")

    def __init__(self, name: str, description: str, skill_path: str):
        self.name = name
        self.description = description
        self.skill_path = skill_path
        self.tokens: set = _extract_tokens(description)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "skill_path": self.skill_path,
        }


class SkillIndexService:
    """
    Skill 索引与检索服务类。

    在内存中维护一个 skill_path → SkillEntry 的映射，
    支持按目录批量索引和按查询文本检索。

    通常在两个场景下使用：
    1. 沙盒测试前：将当前工作区中的所有 Skill 索引，
       模拟多 Skill 竞争场景，验证待测 Skill 的 description 区分度。
    2. 应用运行时：作为全局 Skill 搜索服务，帮助用户找到已创建的 Skill。

    线程安全：不保证（当前为单线程 Flask 请求上下文使用）。
    """

    def __init__(self):
        # skill_path → SkillEntry
        self._index: Dict[str, SkillEntry] = {}

    # ------------------------------------------------------------------
    # 索引操作
    # ------------------------------------------------------------------

    def index_directory(self, root_path: str, recursive: bool = True) -> int:
        """
        扫描目录，将其中所有 SKILL.md 文件加入索引。

        Args:
            root_path: 要扫描的根目录路径（绝对路径）
            recursive: 是否递归扫描子目录（默认 True）

        Returns:
            本次新增或更新的 Skill 数量。
        """
        root = Path(root_path)
        if not root.is_dir():
            return 0

        count = 0
        pattern = "**/*.md" if recursive else "*.md"
        for md_file in root.glob(pattern):
            if md_file.name.upper() == "SKILL.MD":
                entry = self._parse_and_index(md_file)
                if entry is not None:
                    count += 1
        return count

    def index_skill_file(self, skill_md_path: str) -> Optional[SkillEntry]:
        """
        将单个 SKILL.md 文件加入索引。

        Args:
            skill_md_path: SKILL.md 文件的绝对路径

        Returns:
            成功时返回 SkillEntry，失败时返回 None。
        """
        return self._parse_and_index(Path(skill_md_path))

    def remove_skill(self, skill_md_path: str) -> bool:
        """
        从索引中移除指定的 Skill。

        Args:
            skill_md_path: SKILL.md 文件的绝对路径

        Returns:
            True 表示成功移除，False 表示该路径不在索引中。
        """
        key = str(Path(skill_md_path).resolve())
        if key in self._index:
            del self._index[key]
            return True
        return False

    def clear(self) -> None:
        """清空所有索引条目。"""
        self._index.clear()

    @property
    def size(self) -> int:
        """已索引的 Skill 数量。"""
        return len(self._index)

    # ------------------------------------------------------------------
    # 检索操作
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        """
        根据查询文本检索最匹配的 Skill 列表。

        按重叠系数得分降序排列，返回 top_k 个结果。
        得分为 0 的 Skill 不会出现在结果中。

        Args:
            query: 用户查询文本（中英文均支持）
            top_k: 返回结果数量上限（默认 5）

        Returns:
            按得分降序排列的 Skill 信息列表，每项包含：
            - name: Skill 名称
            - description: Skill 描述
            - skill_path: SKILL.md 路径
            - score: 匹配得分（0.0 ~ 1.0）
        """
        if not query or not self._index:
            return []

        query_tokens = _extract_tokens(query)
        if not query_tokens:
            return []

        scored: List[tuple] = []
        for entry in self._index.values():
            score = _overlap_score(entry.tokens, query_tokens)
            if score > 0:
                scored.append((score, entry))

        # 按得分降序，得分相同时按名称字母序保证稳定排序
        scored.sort(key=lambda x: (-x[0], x[1].name))

        results = []
        for score, entry in scored[:top_k]:
            item = entry.to_dict()
            item["score"] = round(score, 4)
            results.append(item)

        return results

    def list_all(self) -> List[dict]:
        """
        列出所有已索引的 Skill（不按查询排序）。

        Returns:
            SkillEntry 字典列表，按名称字母序排列。
        """
        entries = sorted(self._index.values(), key=lambda e: e.name)
        return [e.to_dict() for e in entries]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _parse_and_index(self, md_path: Path) -> Optional[SkillEntry]:
        """
        解析 SKILL.md 并添加到索引。

        只有包含有效 name 和 description 的 SKILL.md 才会被索引。

        Args:
            md_path: SKILL.md 的 Path 对象

        Returns:
            成功时返回 SkillEntry，解析失败时返回 None。
        """
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            return None

        name, description = self._parse_frontmatter(text)
        if not name or not description:
            return None

        entry = SkillEntry(
            name=name,
            description=description,
            skill_path=str(md_path.resolve()),
        )
        self._index[entry.skill_path] = entry
        return entry

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple:
        """
        解析 SKILL.md 的 YAML frontmatter，提取 name 和 description。

        Args:
            content: SKILL.md 全文

        Returns:
            (name, description) 元组，字段缺失时对应值为空字符串。
        """
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return "", ""

        try:
            end = lines.index("---", 1)
        except ValueError:
            return "", ""

        name, description = "", ""
        for line in lines[1:end]:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()

        return name, description
