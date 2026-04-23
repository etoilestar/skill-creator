"""
backend/app/sandbox/docker_runner.py

Docker 沙盒执行器。

职责：
    - 在隔离的 Docker 容器中运行 skill-creator 的 eval_description.py
    - 实施严格的资源限制和安全隔离（无网络、内存上限、CPU 限制）
    - 处理超时、容器崩溃等异常情况
    - 收集并返回容器的输出日志和测试报告

安全隔离措施：
    1. 无网络访问（--network none）：容器不能进行任何网络请求
    2. 只读文件系统挂载：Skill 文件和 eval 脚本以只读方式挂载
    3. 内存限制（默认 256m）：防止内存溢出攻击
    4. CPU 限制（默认 0.5 核）：防止 CPU 占用过高
    5. 执行超时（默认 60 秒）：超时后强制终止容器
    6. 自动清理（--rm）：容器退出后自动删除，不留残留
    7. 输出目录隔离：测试输出写入独立的临时目录，测试后清理

执行流程：
    1. 在 SANDBOX_BASE_PATH/{test_id}/ 创建临时工作目录
    2. 将 evals.json 写入临时目录
    3. 组装 docker run 命令
    4. 以子进程方式执行，设置超时
    5. 解析输出目录中的 result.json
    6. 清理临时目录
    7. 返回结果字典

注意：
    - 本执行器需要宿主机或 Worker 容器有 Docker 访问权限
    - 在 Docker Compose 中通过挂载 /var/run/docker.sock 实现
    - 沙盒镜像（skillfactory-sandbox:latest）需要预先构建
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from flask import current_app


class SandboxRunner:
    """
    Docker 沙盒执行器类。

    通过调用 docker run 命令在隔离容器中执行 eval_description.py，
    收集执行结果并返回标准化的结果字典。
    """

    def run_eval(
        self,
        skill_path: str,
        eval_script_path: str,
        evals: list,
        test_id: str,
    ) -> Dict:
        """
        在 Docker 容器中执行 Skill 触发精度测试。

        Args:
            skill_path: Skill 目录的宿主机绝对路径（挂载到容器中）
            eval_script_path: eval_description.py 的宿主机绝对路径
            evals: 测试用例列表（将被写为 evals.json）
            test_id: 测试记录 ID（用于创建临时目录）

        Returns:
            标准化结果字典：
            {
                "report": {...},          # eval_description.py 的输出报告（JSON）
                "raw_output": "...",      # Docker 容器的原始 stdout/stderr
                "duration_seconds": 0.0,  # 执行耗时
                "timed_out": False,       # 是否超时
                "error": None,            # 错误信息（无错误时为 None）
            }
        """
        sandbox_base = current_app.config.get("SANDBOX_BASE_PATH", "/app/sandboxes")
        docker_image = current_app.config.get(
            "SANDBOX_DOCKER_IMAGE", "skillfactory-sandbox:latest"
        )
        timeout = int(current_app.config.get("SANDBOX_TIMEOUT_SECONDS", 60))
        memory_limit = current_app.config.get("SANDBOX_MEMORY_LIMIT", "256m")
        cpu_limit = current_app.config.get("SANDBOX_CPU_LIMIT", "0.5")

        # 创建本次测试的临时目录
        test_dir = Path(sandbox_base) / test_id
        test_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 将测试用例写入临时目录
            evals_path = test_dir / "evals.json"
            evals_path.write_text(
                json.dumps(evals, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            output_dir = test_dir / "output"
            output_dir.mkdir(exist_ok=True)

            # 组装 docker run 命令
            cmd = self._build_docker_command(
                skill_path=skill_path,
                eval_script_path=eval_script_path,
                evals_path=str(evals_path),
                output_dir=str(output_dir),
                docker_image=docker_image,
                memory_limit=memory_limit,
                cpu_limit=cpu_limit,
                timeout=timeout,
            )

            # 执行 Docker 命令
            start_time = time.time()
            result = self._execute_docker(cmd, timeout=timeout + 10)  # 留 10 秒给 Docker 启动
            duration = time.time() - start_time

            # 解析输出结果
            report = self._read_result(output_dir)

            return {
                "report": report,
                "raw_output": result.get("output", ""),
                "duration_seconds": round(duration, 2),
                "timed_out": result.get("timed_out", False),
                "error": result.get("error"),
            }

        finally:
            # 清理临时目录（无论成功还是失败都清理）
            self._cleanup(test_dir)

    @staticmethod
    def _build_docker_command(
        skill_path: str,
        eval_script_path: str,
        evals_path: str,
        output_dir: str,
        docker_image: str,
        memory_limit: str,
        cpu_limit: str,
        timeout: int,
    ) -> list:
        """
        构建 docker run 命令列表。

        挂载说明：
        - /skill: Skill 目录（只读挂载，防止容器修改用户文件）
        - /eval_script.py: eval_description.py（只读挂载）
        - /evals.json: 测试用例文件（只读挂载）
        - /output: 结果输出目录（读写，容器将结果写入此处）

        Args:
            ... 各参数见 run_eval 说明

        Returns:
            shell 命令列表，可直接传给 subprocess.run()
        """
        return [
            "docker", "run",
            "--rm",                          # 容器退出后自动删除
            "--network", "none",             # 禁止网络访问
            "--memory", memory_limit,         # 内存限制
            "--cpus", cpu_limit,             # CPU 限制
            # 只读挂载 Skill 目录
            "-v", f"{skill_path}:/skill:ro",
            # 只读挂载 eval 脚本
            "-v", f"{eval_script_path}:/eval_script.py:ro",
            # 只读挂载测试用例
            "-v", f"{evals_path}:/evals.json:ro",
            # 读写挂载输出目录（容器需要写入结果）
            "-v", f"{output_dir}:/output",
            docker_image,
            # 容器内执行的命令：带超时的 Python 调用
            "timeout", str(timeout),
            "python3", "/eval_script.py",
            "--skill", "/skill/SKILL.md",
            "--evals", "/evals.json",
            "--output", "/output/result.json",
            "--auto",  # 使用自动化模式（非交互）
        ]

    @staticmethod
    def _execute_docker(cmd: list, timeout: int) -> dict:
        """
        执行 Docker 命令，处理超时和异常。

        Args:
            cmd: docker 命令列表
            timeout: 超时秒数

        Returns:
            包含 output、timed_out、error、exit_code 的字典。
        """
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = proc.stdout + proc.stderr
            return {
                "output": output[:10000],  # 限制输出长度
                "exit_code": proc.returncode,
                "timed_out": False,
                "error": None if proc.returncode in (0, 1) else f"容器退出码: {proc.returncode}",
            }
        except subprocess.TimeoutExpired:
            # 超时后尝试清理可能残留的容器
            return {
                "output": "沙盒执行超时",
                "exit_code": -1,
                "timed_out": True,
                "error": "执行超时",
            }
        except FileNotFoundError:
            # docker 命令不存在
            return {
                "output": "",
                "exit_code": -1,
                "timed_out": False,
                "error": "Docker 不可用，沙盒测试无法执行。请确认 Docker 已安装并可访问。",
            }
        except Exception as e:
            return {
                "output": "",
                "exit_code": -1,
                "timed_out": False,
                "error": f"沙盒执行异常: {str(e)}",
            }

    @staticmethod
    def _read_result(output_dir: Path) -> Optional[dict]:
        """
        从输出目录读取 result.json。

        Args:
            output_dir: 沙盒输出目录 Path

        Returns:
            解析后的测试报告字典，文件不存在或解析失败时返回 None。
        """
        result_file = output_dir / "result.json"
        if not result_file.exists():
            return None
        try:
            return json.loads(result_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _cleanup(test_dir: Path) -> None:
        """
        清理沙盒测试临时目录。

        使用 shutil.rmtree 递归删除整个测试目录。
        清理失败时记录警告但不抛出异常（不影响主流程）。

        Args:
            test_dir: 要清理的目录 Path
        """
        import shutil

        try:
            if test_dir.exists():
                shutil.rmtree(test_dir)
        except Exception as e:
            # 清理失败不影响测试结果，记录警告日志即可
            import warnings
            warnings.warn(f"沙盒临时目录清理失败 {test_dir}: {e}", RuntimeWarning)
