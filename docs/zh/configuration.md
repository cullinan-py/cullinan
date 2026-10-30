title: "配置"
slug: "configuration"
module: []
tags: ["docs", "guide", "configuration"]
author: "plumeink"
reviewers: []
status: new
locale: zh
translation_pair: "docs/configuration.md"
related_tests: ["tests/core/test_config_file.py", "tests/integration/test_feature_example_matrix.py"]
related_examples: ["examples/config_file"]
estimate_pd: null
last_updated: "2026-10-31"

# 配置

Cullinan 从**一个配置文件**读取项目设置——不是 `.env`，也不是散落各处的环境变量。

```json
{
  "server_port": 8080,
  "server_host": "0.0.0.0",
  "server_engine": "asgi"
}
```

`application.run(main)` 会读它。不需要 import，也不需要额外调用。

## 为什么用文件而不是 `.env`

`.env` 是扁平的 `KEY=VALUE` 列表：没有层级、没有类型、也没有办法表达「这个值来自别处」。
它更回答不了打包后真正要紧的那个问题：**这个文件在哪，以及它有没有被打进产物里？**

配置文件能同时回答这四点，所以 `python-dotenv`——框架此前唯一的运行时依赖——已经不再使用。
Cullinan 现在**没有任何运行时依赖**；JSON 由标准库读取。

## 文件名

| 文件 | 何时读取 |
|---|---|
| `application.json` | 存在即读取 |
| `application-<profile>.json` | 设置 `CULLINAN_PROFILE` 时，**叠加**在基线之上 |

`.toml`、`.yaml`、`.yml` 也支持，但仅当解释器或环境能解析它们——TOML 需要 Python 3.11+
（或 `tomli`），YAML 需要 `pyyaml`。解析器缺失时会明确报出该装哪个包，而不是静默地什么都不加载。
JSON 什么都不需要，所以它是永远可用的格式。

## 文件从哪里找

按顺序：

1. `CULLINAN_CONFIG` 指定的路径，或 `load_project_config(path=...)` 传入的路径
2. 工作目录
3. **被启动的可执行体所在目录**

!!! warning "绝不搜索已安装的包目录"
    把配置文件放进安装包会在两个方向上出错：你的设置会随产物一起分发；而产物内的旧副本
    还会**遮蔽**你放在可执行体旁边、刚刚改过的那份。只搜索上面两个位置，并有测试钉住这一点。

显式指定的路径不存在是错误。在有人指名了文件之后回落到默认值，会把一个拼写错误藏到上线。

## 优先级

从高到低：

| # | 来源 | 示例 |
|---|---|---|
| 1 | `run()` 的参数 | `run(main, port=9090)` |
| 2 | 环境变量 | `SERVER_PORT=9090` |
| 3 | `configure(...)` | `@configure(server_port=9090)` |
| 4 | 配置文件 | `{"server_port": 9090}` |
| 5 | 内置默认值 | `4080` |

代码里写的值优先于文件，因为文件先被应用；环境变量优先于两者，因为它在取值时才读取。

## 别把密钥放进文件

一个会被提交、或随二进制一起分发的文件，不是放密钥的地方。**不要把一个值写进文件。**
写在里面的内容应当经得起被贴进 issue——因为迟早会有一次被贴进去。

**该文件默认被忽略。** `application*.json`、`application*.toml`、`application*.yaml`
与 `application*.yml` 已加入 `.gitignore`，所以一次普通的 `git add .` 不会把带值的文件
提进仓库。模板形态——`application*.example.json` 以及对应的 `.toml` / `.yaml` / `.yml`
——仍然可被追踪：那才是用来提交的形态，里面存的是引用而不是值。忽略规则是默认值而不是
一堵墙（`git add -f` 可以绕过），因此仓库侧的检查会把每一个 `application*` 文件**读两遍**
——磁盘上的一份、索引里的一份——任一份里有明文值都会报警。这两份不是同一份，而且任一份都
能把值带进仓库：索引里那份是推送会发出去的内容，磁盘上尚未暂存的修改则是下一份会进历史的内容。
它会对敏感键名下的明文值报警，也会对**值本身是已知凭据形态**的（PEM 私钥头、AWS access
key id、GitHub token）报警——后者与键名叫什么无关。

JSON 与 TOML **在解释器能解析时**按文档读取（TOML 需要 Python 3.11+）；否则按行扫描，
并**报出这次降级**——不会静默。YAML 恒按行读取，写成多行块的值会被记为「无法判定」，
而不是被静默放过。

有两点需要知道：

- 用 `CULLINAN_CONFIG` 指名的文件不受这里任何一条规则覆盖——它的名字可以是任意字符串。
  这样的文件请自己保证不进版本库。
- 已经被提交的文件仍然在历史里。规则挡住的是下一次 `git add .`，它不改写历史。
  删掉文件也不等于把它移出了版本库：在删除被提交之前（对于已经推送过的值，还要重写历史），
  那份副本仍然可以被取到。本检查读的是**工作树与索引**，**不读 `HEAD`**——
  曾经提交、后来从索引移除的值不在本检查范围；把它从历史里去掉是另一件事。

**也不要 `print` 它。** `get_config()` 交回的是已解析的值，所以把整份文档 `print`
出来或打进调试日志，等于把密钥写进终端、日志文件或 CI 输出——那是第二份副本，却没有
第一份拥有的任何保护。打你要看的那个设置，不要打整份文档。

替代做法是在本该写值的地方写引用，为此提供两个能力：

```json
{
  "discord": {
    "token": "${DISCORD_TOKEN}",
    "fallback_channel": "${DEFAULT_CHANNEL:general}"
  }
}
```

- `${VAR}` 在读完文件之后被环境变量替换。
- `${VAR:default}` 在变量不存在时取 `default`。
- **既无值也无默认**的占位符会直接报错。替换成空串会把「缺失的设置」变成「看起来配好了的设置」，
  错误会在更晚、更不显眼的地方出现。

### 如果文件必须是密文

传入解密函数。Cullinan 不自带：

```python
from cullinan.support.config_file import load_project_config

config = load_project_config(decryptor=my_decrypt)   # {"encrypted": "..."} → 明文
```

密钥与密文放在一起不构成加密，所以框架不假装可以。密钥属于部署环境——环境变量、密钥管理服务、
HSM——并始终留在产物之外。

## 打包

把应用编译成二进制会提高读取你代码的成本，但它**不会**让随包分发的**数据**变成秘密。
打进包里的配置文件，可以从包里被解出来。所以这里的指引是位置性的，不是密码学的：

- **不要把配置文件打进包。** 放在可执行体旁边，或用 `CULLINAN_CONFIG` 指过去。
  Cullinan 从不搜索包目录，所以「让打包器把它复制进去」不会带来任何好处。
- **让文件只存引用，不存值。** `${VAR}` 把秘密留在密钥管理服务放好的环境变量里。
- **逐项判断某个设置是否真的必须保密。** 端口号不是秘密，Bot token 是。
  按这条线拆分文件，比把整个文件加密更有效。

关于打包后的应用如何解析自身目录，见[打包指南](packaging.md)——「代码在哪」与「用户数据在哪」
是两件事，这个区分在这里同样适用。

## 完整示例

```json
{
  "server_port": 8080,
  "server_host": "0.0.0.0",
  "server_engine": "tornado",
  "verbose": true,
  "discord": {
    "token": "${DISCORD_TOKEN}"
  }
}
```

```python
from cullinan import application, configure


@configure(user_packages=["myapp"])
@application
def main():
    ...


if __name__ == "__main__":
    main()
```

```bash
CULLINAN_PROFILE=prod DISCORD_TOKEN=... python -m myapp
```

同目录下的 `application-prod.json` 会在取值之前叠加到 `application.json` 之上。

可运行的版本见 [`examples/config_file`](https://github.com/cullinan-py/cullinan/tree/master/examples/config_file)。

## 从 `.env` 迁移

`.env` 里的每个键在文件里都有对应位置，而且嵌套键更易读：

| `.env` | `application.json` |
|---|---|
| `SERVER_PORT=8080` | `{"server_port": 8080}` |
| `DISCORD_TOKEN=abc` | `{"discord": {"token": "${DISCORD_TOKEN}"}}` |
| — | 用 `CULLINAN_PROFILE` 切换 profile |

读取 `.env` 已不再支持，提供它的依赖也已移除。如果你的部署本来就直接导出这些环境变量，
则无需任何改动：环境变量仍然优先于文件。

## 在代码里读配置

```python
from cullinan.support import get_config

port = get_config().server_port
```

如果你要的是原始文档而不是框架设置：

```python
from cullinan.support.config_file import load_project_config

settings = load_project_config()          # 没有文件时返回 {}
```

`load_project_config()` 对「文件不存在」不报错——没有配置文件的应用也是合法应用。
但以下三种情况会报错：文件无法解析、占位符无法解析、显式路径不存在。
