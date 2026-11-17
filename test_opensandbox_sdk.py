"""OpenSandbox SDK 连通性测试（博客 4.1，不接 Agent）。

验证 Server、镜像、SDK 三者链路。运行前确保 opensandbox-server 已启动。
    OPENSANDBOX_DOMAIN=http://127.0.0.1:8080 python test_opensandbox_sdk.py
"""
import asyncio
import os
from datetime import timedelta

from dotenv import load_dotenv
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig
from opensandbox.models import WriteEntry

load_dotenv()

IMAGE = os.getenv(
    "SANDBOX_IMAGE",
    "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2",
)


async def main() -> None:
    config = ConnectionConfig(
        domain=os.getenv("OPENSANDBOX_DOMAIN", "http://127.0.0.1:8080"),
        use_server_proxy=True,
        request_timeout=timedelta(seconds=60),
    )
    sandbox = await Sandbox.create(
        IMAGE,
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        timeout=timedelta(minutes=10),
        connection_config=config,
    )
    print(f"沙箱创建成功，ID: {sandbox.id}")
    async with sandbox:
        execution = await sandbox.commands.run("echo 'Hello OpenSandbox!'")
        print(execution.logs.stdout[0].text)

        await sandbox.files.write_files([
            WriteEntry(path="/tmp/hello.txt", data="Hello World", mode=0o644)
        ])
        print(await sandbox.files.read_file("/tmp/hello.txt"))
    await sandbox.kill()
    print("SDK 链路测试通过")


if __name__ == "__main__":
    asyncio.run(main())