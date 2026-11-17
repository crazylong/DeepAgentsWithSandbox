"""DeepAgents + OpenSandboxBackend 端到端示例（博客 4.4）。

运行前确保 opensandbox-server 已启动，.env 中配置了模型密钥。
默认走阿里云百炼 OpenAI 兼容接口（ALIBABA_API_KEY / ALIBABA_BASE_URL）。
"""
import os
from datetime import timedelta

import httpx
from dotenv import load_dotenv
from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from custom_opensandbox import OpenSandboxBackend, prepare_sandbox

load_dotenv()

IMAGE = os.getenv(
    "SANDBOX_IMAGE",
    "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2",
)

# 1. 连接 OpenSandbox Server（本地部署默认 127.0.0.1:8080）
config = ConnectionConfigSync(
    domain=os.getenv("OPENSANDBOX_DOMAIN", "http://127.0.0.1:8080"),
    use_server_proxy=True,   # 命令/文件请求经 Server 代理转发到沙箱
    request_timeout=timedelta(seconds=60),
    transport=httpx.HTTPTransport(limits=httpx.Limits(max_connections=20)),
)

# 2. 创建沙箱（也可用 SandboxSync.connect(sandbox_id, ...) 复用已有沙箱）
sandbox = SandboxSync.create(
    IMAGE,
    entrypoint=["/opt/opensandbox/code-interpreter.sh"],
    env={"PYTHON_VERSION": "3.11"},
    resource={"cpu": "2", "memory": "4Gi"},
    timeout=timedelta(minutes=30),
    connection_config=config,
)
print(f"沙箱创建成功，ID: {sandbox.id}")

# 3. 包装为 DeepAgents 后端，并做 venv 初始化
backend = OpenSandboxBackend(sandbox=sandbox)
prepare_sandbox(backend)

# 4. 创建 Agent —— 和 Daytona 示例唯一的区别就是 backend 这一行
llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "qwen-plus"),
    temperature=0,
    api_key=os.getenv("ALIBABA_API_KEY"),
    base_url=os.getenv("ALIBABA_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
)
agent = create_deep_agent(
    model=llm,
    backend=backend,
    system_prompt=(
        "你是一个 Python 编码助手，运行在完全隔离的沙箱中。"
        "可以用 execute 运行 shell 命令，用 write_file / read_file 操作文件。"
    ),
)

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": (
            "写一个脚本统计 1 到 100 中所有质数，保存到 /tmp/primes.py，"
            "运行它并把结果写入 /tmp/primes.txt，最后告诉我质数个数。"
        ),
    }]
})
print("=" * 60)
print(result["messages"][-1].content)

# 5. 取回产物（走文件传输 API，不是 shell）
files = backend.download_files(["/tmp/primes.txt"])
if files[0].error:
    print(f"产物下载失败: {files[0].error}")
else:
    print("=" * 60)
    print("产物 /tmp/primes.txt 内容：")
    print(files[0].content.decode("utf-8"))

sandbox.kill()
print("端到端测试完成，沙箱已回收")