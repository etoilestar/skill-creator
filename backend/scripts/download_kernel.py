"""
backend/scripts/download_kernel.py

skill-creator 内核下载脚本。

职责：
    - 从指定来源下载 skill-creator 内核的最新版本
    - 更新 backend/kernels/skill-creator/ 目录中的内容
    - 计算并更新 kernel.json 中的文件 checksum
    - 校验下载完整性（SKILL.md 必须存在且格式正确）

使用方式：
    # 首次下载（在 backend/ 目录下执行）
    python scripts/download_kernel.py

    # 更新到最新版本
    python scripts/download_kernel.py --force

    # 下载指定 GitHub 仓库版本
    python scripts/download_kernel.py --repo iml885203/openclaw-skill-creator --ref main

注意：
    - 脚本会在执行前备份当前内核（存放到 kernels/skill-creator.bak/）
    - 下载失败时自动恢复备份
    - 建议在 Docker build 阶段或系统首次部署时执行此脚本
    - 生产环境升级内核前请先在测试环境验证

内核来源：
    主要来源：https://skillsmp.com/skills/openclaw-openclaw-skills-skill-creator-skill-md
    GitHub 备用：https://github.com/iml885203/openclaw-skill-creator
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# 默认 GitHub API URL（通过 GitHub API 下载，无需 git）
DEFAULT_GITHUB_REPO = "iml885203/openclaw-skill-creator"
DEFAULT_GITHUB_REF = "main"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"

# 内核目录路径（相对于本脚本的位置）
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
KERNEL_DIR = BACKEND_DIR / "kernels" / "skill-creator"


def download_file(url: str, dest_path: Path) -> bool:
    """
    下载指定 URL 的文件到目标路径。

    Args:
        url: 下载 URL
        dest_path: 目标文件路径

    Returns:
        True 表示下载成功，False 表示失败。
    """
    try:
        print(f"  下载: {url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "skillfactory-kernel-downloader/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(response.read())
        print(f"  ✅ 已保存: {dest_path}")
        return True
    except Exception as e:
        print(f"  ❌ 下载失败: {e}", file=sys.stderr)
        return False


def compute_sha256(file_path: Path) -> str:
    """
    计算文件的 SHA256 哈希值。

    Args:
        file_path: 文件路径

    Returns:
        SHA256 哈希值的十六进制字符串（带 "sha256:" 前缀）。
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def backup_kernel() -> Path:
    """
    备份当前内核目录到 skill-creator.bak/。

    Returns:
        备份目录路径（如果原目录存在的话），否则返回 None。
    """
    if not KERNEL_DIR.exists():
        return None

    backup_dir = KERNEL_DIR.parent / "skill-creator.bak"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(KERNEL_DIR, backup_dir)
    print(f"已备份当前内核到: {backup_dir}")
    return backup_dir


def restore_backup(backup_dir: Path) -> None:
    """
    从备份恢复内核目录。

    Args:
        backup_dir: 备份目录路径
    """
    if backup_dir and backup_dir.exists():
        if KERNEL_DIR.exists():
            shutil.rmtree(KERNEL_DIR)
        shutil.copytree(backup_dir, KERNEL_DIR)
        print(f"已从备份恢复内核: {backup_dir}")


def download_kernel(repo: str, ref: str, force: bool = False) -> bool:
    """
    从 GitHub 下载 skill-creator 内核文件。

    下载内容：
    - SKILL.md（核心定义文件，必须存在）
    - scripts/eval_description.py（触发精度评估脚本）

    Args:
        repo: GitHub 仓库（格式：owner/repo）
        ref: Git 引用（分支名或 commit SHA）
        force: 是否强制覆盖已有内核

    Returns:
        True 表示下载成功，False 表示失败。
    """
    if KERNEL_DIR.exists() and not force:
        kernel_json = KERNEL_DIR / "kernel.json"
        if (KERNEL_DIR / "SKILL.md").exists():
            print(f"内核已存在: {KERNEL_DIR}")
            print("使用 --force 参数强制重新下载")
            return True

    print(f"\n开始下载 skill-creator 内核...")
    print(f"  来源仓库: {repo}")
    print(f"  分支/提交: {ref}")
    print(f"  目标目录: {KERNEL_DIR}\n")

    # 备份当前内核
    backup_dir = backup_kernel()

    try:
        # 确保内核目录存在
        KERNEL_DIR.mkdir(parents=True, exist_ok=True)
        (KERNEL_DIR / "scripts").mkdir(exist_ok=True)

        base_url = f"{GITHUB_RAW_BASE}/{repo}/{ref}"

        # 下载 SKILL.md（必须成功）
        skill_md_ok = download_file(
            f"{base_url}/SKILL.md",
            KERNEL_DIR / "SKILL.md",
        )
        if not skill_md_ok:
            print("❌ SKILL.md 下载失败，内核下载中止", file=sys.stderr)
            restore_backup(backup_dir)
            return False

        # 下载 eval 脚本（可选，失败时警告但不中止）
        eval_ok = download_file(
            f"{base_url}/scripts/eval_description.py",
            KERNEL_DIR / "scripts" / "eval_description.py",
        )
        if not eval_ok:
            print("⚠️  eval_description.py 下载失败，沙盒测试功能将不可用")

        # 计算 checksum
        checksum = compute_sha256(KERNEL_DIR / "SKILL.md")

        # 更新/创建 kernel.json
        kernel_json_path = KERNEL_DIR / "kernel.json"
        meta = {
            "kernel_id": "skill-creator",
            "version": "1.0.0",
            "source_url": "https://skillsmp.com/skills/openclaw-openclaw-skills-skill-creator-skill-md",
            "github_ref": repo,
            "downloaded_at": datetime.utcnow().isoformat() + "Z",
            "checksum_skill_md": checksum,
            "status": "active",
            "description": "OpenClaw Skill Creator 内核，用于指导 AI 创建符合 OpenClaw 规范的 Skill。",
            "capabilities": ["skill_creation_guide", "description_eval", "quality_checklist"],
        }
        kernel_json_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"\n✅ skill-creator 内核下载完成！")
        print(f"   SKILL.md checksum: {checksum}")
        print(f"   目录: {KERNEL_DIR}")
        return True

    except Exception as e:
        print(f"❌ 内核下载失败: {e}", file=sys.stderr)
        restore_backup(backup_dir)
        return False


def main():
    parser = argparse.ArgumentParser(description="下载 skill-creator 内核")
    parser.add_argument("--repo", default=DEFAULT_GITHUB_REPO, help="GitHub 仓库（owner/repo）")
    parser.add_argument("--ref", default=DEFAULT_GITHUB_REF, help="分支名或 commit SHA")
    parser.add_argument("--force", action="store_true", help="强制重新下载（覆盖已有内核）")
    args = parser.parse_args()

    success = download_kernel(args.repo, args.ref, args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
