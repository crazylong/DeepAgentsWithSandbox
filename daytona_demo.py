"""Daytona + DeepAgents 最小示例（博客第二章）。

需要能访问 Daytona 海外 API（国内需代理），并在 .env 配置：
    DAYTONA_API_KEY / DAYTONA_BASE_URL / OPENAI_API_KEY / OPENAI_BASE_URL
"""
import os

from dotenv import load_dotenv
from daytona import Daytona, DaytonaConfig
from langchain_daytona import DaytonaSandbox
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

load_dotenv()

llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "gpt-4o"),
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

# 1. 创建远程沙箱（向 Daytona 服务发起请求，创建一个隔离容器）
config = DaytonaConfig(
    api_key=os.getenv("DAYTONA_API_KEY"),
    api_url=os.getenv("DAYTONA_BASE_URL", "https://app.daytona.io/api"),
    target="us",
)
sandbox = Daytona(config).create()
print(f"沙箱创建成功，ID: {sandbox.id}")

# 2. 把沙箱包装成 DeepAgents 的后端
backend = DaytonaSandbox(sandbox=sandbox)

# 3. 创建 Agent，传入沙箱后端
agent = create_deep_agent(
    model=llm,
    backend=backend,
    system_prompt=(
        "你是一个 Python 编码助手，运行在完全隔离的沙箱中。"
        "可以用 execute 运行 shell 命令，用 write_file / read_file 操作文件。"
    ),
)

# 4. 下发任务
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": (
            "在 /home/daytona/ 下创建 test_sandbox.py，"
            "打印 'Hello from the secure sandbox!' 和当前工作目录，"
            "然后运行它并告诉我输出。"
        ),
    }]
})
print(result["messages"][-1].content)

sandbox.delete()