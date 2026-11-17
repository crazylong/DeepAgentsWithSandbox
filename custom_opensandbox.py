"""OpenSandbox 沙箱后端实现，遵循 DeepAgents SandboxBackendProtocol。

职责边界：
  - 不负责创建/销毁远程沙箱（由调用方完成）
  - 只包装已有 SandboxSync，提供 execute / upload_files / download_files
  - 文件读写的高层方法（read/write/ls/...）继承自 BaseSandbox

对应博客《DeepAgents 接入 OpenSandbox》第四章。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import cast

from opensandbox import SandboxSync
from opensandbox.models import WriteEntry

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

SyncPollingInterval = float | Callable[[float], float]
PollingStrategy = Callable[[float], float]
logger = logging.getLogger(__name__)


class OpenSandboxBackend(BaseSandbox):
    """继承 BaseSandbox 的文件操作方法，仅实现 execute、download_files、upload_files。"""

    def __init__(
        self,
        *,
        sandbox: SandboxSync,
        timeout: int = 60 * 60,
        sync_polling_interval: SyncPollingInterval = 0.1,
    ) -> None:
        self._sandbox = sandbox
        self._default_timeout = timeout
        # 与 Daytona 适配器保持一致：轮询间隔支持 callable，可做退避策略
        if callable(sync_polling_interval):
            polling_strategy = cast("PollingStrategy", sync_polling_interval)
        else:
            def polling_strategy(_elapsed: float) -> float:
                return sync_polling_interval
        self._sync_polling_interval = polling_strategy

    @property
    def id(self) -> str:
        return self._sandbox.id

    # 沙箱中非交互式 shell 不会加载 /etc/profile，需要手动注入环境变量。
    # /opt/skills-venv/bin 必须置顶：让 python/pip 走沙箱内虚拟环境，
    # 避开系统 Python 的 PEP 668（externally-managed）限制。
    SANDBOX_PATH = (
        "/opt/skills-venv/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        wrapped = f'export PATH="{self.SANDBOX_PATH}:$PATH" && {command}'
        return self._execute_command(wrapped, timeout=effective_timeout)

    def _execute_command(self, command: str, *, timeout: int) -> ExecuteResponse:
        try:
            # OpenSandbox SDK 的 commands.run 是同步阻塞调用，
            # 不需要 Daytona 那套 session + 轮询
            result = self._sandbox.commands.run(command)

            stdout = ""
            stderr = ""
            if result.logs.stdout:
                stdout = "\n".join(log.text for log in result.logs.stdout)
            if result.logs.stderr:
                stderr = "\n".join(log.text for log in result.logs.stderr)

            # 沿用官方约定：stderr 用标签拼接，方便 LLM 区分
            output = stdout
            if stderr and stderr.strip():
                output += f"\n<stderr>{stderr.strip()}</stderr>"

            return ExecuteResponse(
                output=output,
                exit_code=result.exit_code or 0,
                truncated=False,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"执行命令时发生错误：{error_msg}", exc_info=True)
            # 沿用官方约定：超时返回 124
            if "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"命令在 {timeout} 秒后超时",
                    exit_code=124,
                    truncated=False,
                )
            return ExecuteResponse(
                output=f"执行命令时出错：{error_msg}",
                exit_code=1,
                truncated=False,
            )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            try:
                content = self._sandbox.files.read_file(path)
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                responses.append(
                    FileDownloadResponse(path=path, content=content_bytes, error=None)
                )
            except Exception:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        upload_entries: list[WriteEntry] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                if isinstance(content, bytes):
                    try:
                        content_str = content.decode("utf-8")
                    except UnicodeDecodeError:
                        content_str = content.decode("latin-1")
                else:
                    content_str = str(content)
                upload_entries.append(WriteEntry(path=path, data=content_str, mode=0o644))
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))

        if upload_entries:
            try:
                self._sandbox.files.write_files(upload_entries)
            except Exception as e:
                # 批量写入失败：把已标记成功的条目全部回滚为错误，
                # 避免上层误以为文件已落盘
                for resp in responses:
                    if resp.error is None:
                        resp.error = f"upload_failed: {e}"
        return responses


def prepare_sandbox(backend: OpenSandboxBackend) -> None:
    """沙箱就绪后的初始化：建 venv + 预装依赖（幂等）。

    系统 Python 有 PEP 668 externally-managed 限制，pip install 会被拒绝；
    统一 venv + PATH 置顶后，Agent 的 python/pip 命令自动路由进 venv。
    """
    backend.execute("python3 -m venv /opt/skills-venv")
    pip = "/opt/skills-venv/bin/pip"
    # 国内环境走阿里云 PyPI 镜像
    args = "-i https://mirrors.aliyun.com/pypi/simple/ --default-timeout=60 --no-input -q"
    backend.execute(f"{pip} install --upgrade pip {args}", timeout=60)

    # sentinel 文件避免重复安装（沙箱被复用时很有用）
    if backend.execute("test -f /tmp/.venv_packages_installed").exit_code != 0:
        result = backend.execute(
            f"{pip} install requests beautifulsoup4 {args}", timeout=300
        )
        if result.exit_code == 0:
            backend.execute("touch /tmp/.venv_packages_installed")