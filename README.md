# DeepAgentsWithSandbox

DeepAgents 接入阿里开源 OpenSandbox 的最小可运行实现：用一百多行代码实现 `OpenSandboxBackend`，把 DeepAgents 官方海外沙箱（Daytona 等）替换为可私有化部署的执行环境。

**配套博客（含完整源码解读与踩坑记录）**：
https://blog.csdn.net/u012470019/article/details/170927172

版本基准：deepagents 0.7.5 / langchain-daytona 0.0.8 / opensandbox 0.1.7 / opensandbox-server 0.2.1。
已在 macOS + Docker Desktop 环境端到端实测跑通（Agent 在沙箱中写脚本、执行、取回产物）。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `custom_opensandbox.py` | 核心：`OpenSandboxBackend(BaseSandbox)` 实现 + `prepare_sandbox()` venv 初始化 |
| `main_opensandbox.py` | 端到端示例：创建沙箱 → Agent 执行质数统计任务 → 下载产物 → 回收沙箱 |
| `test_opensandbox_sdk.py` | OpenSandbox SDK 冒烟测试（不依赖模型，先验证 Server 链路） |
| `daytona_demo.py` | Daytona 官方示例对照（需海外网络与 API Key，本仓库未实际运行） |
| `Dockerfile.server` | macOS Docker Desktop 下容器化运行 Server 的镜像 |
| `sandbox-server-container.toml` | 容器化 Server 配置（监听 0.0.0.0:8080） |
| `sandbox-local.toml` | Linux 宿主机进程方式运行 Server 的配置（127.0.0.1:8080） |
| `run_e2e.log` / `server.log` | 实测运行日志 |

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+，实测 3.13
pip install -r requirements.txt
cp .env.example .env   # 填入 ALIBABA_API_KEY（百炼 DashScope Key）
```

### 2. 启动 OpenSandbox Server

**Linux（原生 Docker）**：宿主机进程直接跑即可。

```bash
OPENSANDBOX_INSECURE_SERVER=YES opensandbox-server --config sandbox-local.toml
```

**macOS（Docker Desktop）**：Server 必须容器化。Docker Desktop 的容器跑在 Linux VM 里，
macOS 宿主机进程无法直连沙箱容器的 bridge IP（健康检查全部超时）；把 Server 放进同一
bridge 网络并挂载 docker.sock 即可解决。Linux 原生 Docker 无此问题。

```bash
docker build -t opensandbox-server-local -f Dockerfile.server .
docker run -d --name opensandbox-server \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/sandbox-server-container.toml:/app/sandbox.toml \
  -e OPENSANDBOX_INSECURE_SERVER=YES \
  opensandbox-server-local
```

### 3. 运行

```bash
# 先验证 Server 链路（不需要模型 Key）
python test_opensandbox_sdk.py

# 端到端：Agent 在沙箱里写代码、执行、取回产物
python main_opensandbox.py
```

## 注意事项

- **代理环境变量**：若 `NO_PROXY` 含 CIDR / IPv6 条目（如 `127.0.0.0/8`、`[::1]`），httpx 会直接崩溃
  （`InvalidURL: Invalid port`）。运行 Server 和客户端前清掉代理变量，例如：
  `env -u NO_PROXY -u no_proxy -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy python main_opensandbox.py`
- **PEP 668**：code-interpreter 镜像的系统 Python 禁止 pip 直装，`prepare_sandbox()` 会创建
  `/opt/skills-venv` 并在 `execute` 时注入 PATH，无需改镜像。
- **无 API Key 的 Server 仅供本地调试**：`OPENSANDBOX_INSECURE_SERVER=YES` 是显式确认不安全模式，
  生产部署请在 toml 中配置 `server.api_key`。

更多细节（BaseSandbox 协议约定、Daytona 适配器源码对照、macOS 拓扑排查过程）见博客。