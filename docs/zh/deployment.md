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

收到 `SIGTERM` 后，进程停止接受新工作、等待已在跑的请求、然后退出。等待受 `drain_timeout` 约束。

`drain_timeout` 挂在运行时配置上，而运行时配置目前要通过 `Application(...)` 这个**高级入口类**触达。
多数应用无需碰它：声明入口方法、沿用默认值（30s）即可。只有必须改动这个数字时才用这个类：

```python
from cullinan.application import Application
from cullinan.web.gateway import WebRuntimeConfig

app = Application(
    MyRoot,
    runtime_config=WebRuntimeConfig(drain_timeout=15.0),
).install()
```

关于这个上限，有三点值得知道：

1. **它只是一个数。** lifespan 关闭与同步关闭路径读的是**同一个**配置值，所以"你等的"和"框架等的"不可能分叉。
2. **超时不是错误，而是决定。** 上限到期后，剩余工作被放弃、进程关闭。对卡住的请求这是正确行为，
   但它意味着：`drain_timeout` 应当**长于你最慢的正常请求**，**短于**编排系统发 `SIGKILL` 的时刻。
3. **结果是会报告的。** `ApplicationContext.shutdown()` 及其异步版本在时限内排空完成时返回 `True`，
   超时返回 `False` —— 于是"这次关闭丢了工作"可以在不看日志的情况下被检出。

如果你**已经在事件循环里**，用异步形式。同步形式会检测到运行中的循环并**拒绝阻塞它**——
在那里阻塞循环，会饿死它正在等待的那些请求；此时它**打警告并返回**，而不是假装已经排空。

## 探针：就绪与存活是两个问题

框架**不会**为你注册健康/就绪路由。这是有意的：探针属于你的运维叙事，
框架替你选一条路径，只会多一个能和你的基础设施产生分歧的东西。

它给你的是**状态**与**转折点**：

| 面 | 回答什么 |
|---|---|
| `Application.accepts_requests` | 这个实例还愿意接新活吗？开始排空后为 `False` |
| `Application.context.add_draining_handler(callback)` | 排空**开始的那一刻**执行它 |

读这个谓词的就绪探针，会在进程开始收尾的同一刻让流量停止进来：

```python
from cullinan.application import Application
from cullinan.web import get_api


@get_api(url="/ready")
def ready(self):
    app = Application.current()
    return {"ready": bool(app is None or app.accepts_requests)}
```

**存活探针要分开，并且回答 `True`。** 优雅关闭期间进程是健康的，而且它**本来就该**停止接流量；
一个读排空状态的存活探针，会把"健康的关闭"报告成"崩溃"，于是在发布中途招来一次重启。
两个探针的可运行版本见 [示例](examples.md)。

## 反向代理与转发头

在代理后面，客户端地址与 scheme 出现在**头部**而不是连接里。只在你**自己控制的代理**设置它们时才信任：

```python
from cullinan.web.gateway import WebRuntimeConfig

config = WebRuntimeConfig(trust_forwarded_headers=True)
```

默认关闭时，框架读**连接**。没有代理却打开它，等于让客户端随便声称自己是谁 ——
按 IP 的限流与审计日志就是这样悄悄失效的。

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
- [ ] 你**亲眼看过一次优雅关闭**，并看到探针在进程退出前发生变化

最后一条不是形式主义：它是唯一能证明"信号 → 排空 → 探针 → 负载均衡"整条链确实接通的检查。
