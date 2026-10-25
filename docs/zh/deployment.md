title: "生产部署"
slug: "deployment"
module: []
tags: ["docs", "guide", "operations", "production"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/deployment.md"
related_tests: ["tests/integration/test_deployment_guide_symbols.py", "tests/integration/test_feature_example_matrix.py"]
related_examples: ["examples/graceful_shutdown"]
estimate_pd: 2.0
last_updated: "2026-10-25T00:00:00Z"
pr_links: []

# 生产部署

本页讲的是**进程边界**：什么会启动、什么会停止、负载均衡该问它什么、哪个开关改变哪个行为。
前提是你已经有一个能在本机跑起来的应用 —— 没有的话，先看 [快速开始](getting_started.md)。

下面提到的每一项都是**本版本真实存在**的面。本页没写的开关，就不是受支持的生产行为变更方式。

## 你部署的是什么

你部署的是**一个进程**，它运行**一个入口方法**。入口方法就是普通 Python 函数，用 `@application` 标记、用 `@configure(...)` 配置：

```python
from cullinan import application, configure


@configure(user_packages=["myapp"], server_host="0.0.0.0", server_port=8080)
@application
def main(): ...
```

`main()` 启动服务器并阻塞，直到进程被要求停止。把它交给**监督者**（systemd、容器运行时、或你平台的进程管理器），不要自己在代码里 fork：
重启策略、日志收集、信号投递都属于监督者；在框架里再实现一遍，只会让你在"进程不肯退出"时有两个地方要查。

### 横向扩展

在负载均衡后面跑 N 个进程。没有集群成员、没有共享状态、没有选主：每个进程都是独立副本 ——
这正是"滚动发布"能简化为"起新的、停旧的"的原因。

## 选引擎

框架可以跑在两种后端之上，请求路径一致。按**部署**选一个，而不是按路由选：

```python
@configure(user_packages=["myapp"], server_engine="asgi")
@application
def main(): ...
```

`server_engine` 接受 `"auto"`、`"tornado"`、`"asgi"`。环境变量 `CULLINAN_ENGINE` 效果相同，
在容器里通常是更好的选择：同一个镜像不必重建就能跑任一后端。

## 关闭序列

收到停止信号（`SIGTERM`；Windows 上还有 `SIGINT` 与 `SIGBREAK`）后，进程按**这个顺序**做四件事：

1. **宣告排空** —— 就绪谓词**立即**变为 `False`，探针或负载均衡由此获得一个"不再派活"的窗口；
2. **对仍然到达的请求回 `503`** —— 不是 `500`。排空期到达的请求是**时机**问题、不是请求本身有错，读状态码的人必须能区分这两者；
3. **等待已在跑的请求**，最长 `drain_timeout`；
4. **关闭** —— 监听器消失、容器关闭、进程退出。

第 2 步有个用一次发版换来的前提：**排空期间"谁还能找到你"取决于引擎。**

| 引擎 | 排空期到达的请求 |
|---|---|
| Tornado | 监听器保持打开，请求被接收并回 `503` + `Retry-After: 1` |
| ASGI（uvicorn） | uvicorn 在关闭流程**第一步**关监听，随后对所有已开连接调 `shutdown()` —— 所以**没有"你能主动够到它"的窗口**：信号后约 0.1s 内可能仍得到 `503`，之后既有连接被断开、新连接不被接受（客户端要么挂住要么被拒）。按"实例已经消失"处理 |

这个顺序框架改不了：上限交给了服务器，什么时候停止监听、什么时候断开连接都由服务器决定。请据此规划 —— 每次探针都新建连接的实现看到的是"实例消失"而不是 `503`；这依然是正确的"别往我这里派活"信号，只是它不是你能读到的状态码。**在 ASGI 上，可靠的它就绪信号只有关闭开始之前那一次读数。**

第 3 步由**一个数**兜住，而这个数是交给**真正负责等待的那一方**的：

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], drain_timeout=15.0)
@application
def main(): ...


main()
```

`drain_timeout` 就放在 `@configure(...)` 上，和 `server_port`、`server_engine` 并列 —— 一个只有高级入口才能摸到的旋钮，等于大多数应用永远找不到。`Application(...)`（**高级入口类**）配 `WebRuntimeConfig(drain_timeout=...)` 仍然可用，显式传入的运行时配置优先。

关于这个上限，有两点必须说清：

1. **它是被执行的，不是建议值。** `drain_timeout=1.0` 配一个需要 6s 的请求：两个引擎都在约 1.1–1.4s 退出（上限 + 收尾开销，不是固定的分引擎数字），慢请求被切断。而且**切断的表现不同**：ASGI 回 `500`（服务器取消任务），Tornado 直接断连。需要慢请求跑完，就把上限调大。
2. **结果会报告。** `ApplicationContext.shutdown()` 与 `ashutdown()` 在时限内排空完成时返回 `True`，超时返回 `False`。⚠️ 一个坑：在运行中的事件循环里从线程调用同步形式，它**拒绝阻塞循环**、打警告、返回 `False`，**但容器照样被关闭** —— 所以 `False` 的含义是"没有等"，不是"什么都没发生"。

## 探针：就绪与存活是两个问题

框架不替你注册健康/就绪路由，只给你**状态**与**转折点**：

| 面 | 回答什么 |
|---|---|
| `Application.accepts_requests` | 这个实例还愿意接新活吗？从排空**开始那一刻**起为 `False` |
| `Application.context.add_draining_handler(callback)` | 排空**开始的那一刻**执行它 |

因为排空是在**信号**处宣告、而不是等完之后才宣告，读这个谓词的就绪路由（或直接在 `accepts_requests` 为 `False` 时回 `503`）会在**还有流量可摘**的时候改变：

```python
from cullinan.application import Application
from cullinan.web import controller, get_api


@controller(url="/ops")
class OpsController:
    @get_api(url="/ready")
    def ready(self):
        app = Application.current()
        ready = app is None or app.accepts_requests
        return {"ready": ready}
```

**存活探针要分开，并且回答 `True`。** 优雅关闭期间进程是健康的，而且它**本来就该**停止接流量；读排空状态的存活探针会把健康关闭报成崩溃。

两个探针的可运行版本就在 `examples/graceful_shutdown/` 包里：`python -m examples.graceful_shutdown` 起服务，路由在 `root.py`。

## 两个引擎目前**不共享**什么

正常流量的请求路径、响应体、状态码，两个引擎一致。下面这些**不一致**，写出来是为了让你能提前规划，而不是上线后才发现：

- `server` 响应头（`uvicorn` 与 `TornadoServer`），它由服务器设置，不由框架设置；
- 排空期**新连接**是被回 `503`（Tornado）还是根本不被接受（ASGI，因为 uvicorn 先关监听）—— 见上面的关闭章节；
- 上限切断在飞请求时客户端看到什么：ASGI 是 `500`，Tornado 是断连；
- 超过 `max_request_body_bytes` 时的状态码：ASGI 是 `413`，Tornado 是 `400`（见下面的「请求体大小」章节）—— **两者都在上限处停止读取**，这才是关键。

**正常流量**上两个引擎一致：状态码、响应体、`405` 上的 `Allow`、对未知路径 `OPTIONS` 的 `404`。上面这些差异写出来，是为了让你能提前规划，而不是上线后才发现。

## 反向代理与转发头

在代理后面，客户端地址与 scheme 出现在**头部**而不是连接里。只在你**自己控制的代理**设置它们时才信任：

```python
from cullinan.web.gateway import WebRuntimeConfig

config = WebRuntimeConfig(trust_forwarded_headers=True)
```

默认关闭时，框架读**连接**。没有代理却打开它，等于让客户端随便声称自己是谁 ——
按 IP 的限流与审计日志就是这样悄悄失效的。

## `SIGTERM` 之后的退出码

排空完成与进程退出是两件事，而**退出码取决于引擎**：

| 引擎 | 干净排空后的退出码 | 实测环境 |
|---|---|---|
| ASGI（uvicorn） | `143` —— Python 侧看到的子进程状态是 `-15` | Linux 与 macOS |
| Tornado | `0` | Linux、macOS（`SIGTERM`）与 Windows（`SIGBREAK`）；适配器停掉自己的循环后返回 |

uvicorn 的非零退出码是**设计**，不是"关闭被打断"：事件循环排空、lifespan 关完之后，它恢复原有处理器并
**把捕获到的信号重新发给自己**，这样 shell 与监督进程看到的是真实原因：

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [2550]
# ASGI：$? 是 143（128 + 15）
```

Tornado 没有这一步：它停掉自己持有的循环然后返回，进程以 `0` 退出。

**判断有没有排空完成，看日志，不要看退出码。** 要求必须是 `0` 的监督进程，会把一次健康的 uvicorn
关闭报成崩溃；要求必须是 `143` 的，会把一次健康的 Tornado 关闭报成崩溃。

## 请求体大小

框架在知道"哪个路由会处理它"之前就要把 body 读完，所以上限只能在**入口处**执行：

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], max_request_body_bytes=1_000_000)
@application
def main(): ...
```

不设值 = 客户端发多少就读多少（沿用的历史行为，把它改成默认限制会打断既有上传）。设了值之后，超过它的请求会**在不读完剩余 body 的情况下被拒**，且不会进任何 handler。**状态码取决于哪一层拒绝，而两层不同**：

| 引擎 | 超限体 |
|---|---|
| ASGI | `413 Payload Too Large` + JSON 体，由适配器给出 |
| Tornado | `400 Bad Request` + 空体，由 Tornado 协议层（`max_body_size`）在框架看到请求之前给出 |

两者都是早停 —— 这才是关键性质；但它们**不是同一个状态码**，把它写成一致等于让你上线后自己发现。

部署对公网接受上传时请设它 —— 不设上限时，一个 1 MiB 的 body 打到一个**不存在的路径**，会被完整缓冲后才回 `404`。

## 静态文件

两种可行部署：

- **由代理提供静态文件。** 最快，且让应用进程只做应用的事。把代理指向同一目录即可。
- **由应用提供**，用 `configure(static_files=[...])`。没有代理、或文件由应用自己生成时有用。

无论哪种，都在**提供它们的那一层**设置缓存策略；框架不替你猜。

## 升级与弃用窗口

每次移除都会**带版本号公告**，且公告的版本**不会移动**。
这正是"可以规划的弃用"与"每次发布都往后滑、直到没人相信"之间的区别。

某个符号被弃用时，移除版本由**该弃用所落的版本线 + 策略窗口**算出 —— 从不以字面量写进源码，
所以只有一个值而不是两个。如果你在生产里锁版本范围，请按**公告的移除版本**锁，而不是按"过几个版本再说"。

## 部署检查清单

在你说某次部署"可用于生产"之前：

- [ ] 进程跑在会转发 `SIGTERM` 并等待的监督者之下
- [ ] `drain_timeout` 长于你最慢的正常请求
- [ ] 编排系统的强杀超时长于 `drain_timeout`
- [ ] 负载均衡的空闲超时长于就绪探针间隔
- [ ] 就绪探针读 `accepts_requests`；存活探针不读
- [ ] 代理会剥离入站 `X-Forwarded-*`（除非是它自己设置的）
- [ ] 你清楚静态文件由代理还是应用提供，且缓存策略设在那层
- [ ] 你在**自己的引擎**上亲眼看过一次优雅关闭，并确认它真实的样子：Tornado 上排空期到达的请求得到 `503`，ASGI 上实例直接不再应答 —— 且你的探针把这两种都判为"别往我这里派活"

最后一条不是形式主义：它是唯一能证明"信号 → 排空 → 探针 → 负载均衡"整条链确实接通的检查。
