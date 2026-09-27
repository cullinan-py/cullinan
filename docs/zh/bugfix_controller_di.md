# Controller 依赖注入 Bug 修复说明

Author: plumeink

## 问题描述

### Bug 表现

在使用 `@controller` 装饰器的类中，通过 `Inject()` 标记的依赖项在运行时未被替换为实际的服务实例：

```python
@controller(url='/api')
class BotController:
    multi_channel_service: MultiChannelService = Inject()
    
    def handle_request(self):
        # 错误：self.multi_channel_service 仍然是 Inject 对象
        # AttributeError: 'Inject' object has no attribute 'get_binding'
        self.multi_channel_service.get_binding(...)
```

### 错误信息

```
AttributeError: 'Inject' object has no attribute 'get_binding'
```

## 根本原因

`ControllerRegistry.get_instance()` 方法直接调用 `controller_class()` 实例化 Controller，而没有通过 `ApplicationContext._create_class_instance()` 来处理依赖注入。

**问��代码（修复前）**：
```python
# cullinan/controller/registry.py
def get_instance(self, name: str):
    # ...
    # 直接实例化，没有处理 Inject() 标记
    instance = controller_class()
    return instance
```

## 修复方案

### 1. 添加全局 ApplicationContext 访问点

在 `cullinan/core/__init__.py` 中添加：

```python
_global_application_context = None

def get_application_context():
    """获取全局 ApplicationContext 实例"""
    return _global_application_context

def set_application_context(ctx) -> None:
    """设置全局 ApplicationContext 实例"""
    global _global_application_context
    _global_application_context = ctx
```

### 2. 修改 ControllerRegistry.get_instance()

在 `cullinan/controller/registry.py` 中修改：

```python
def get_instance(self, name: str):
    # ...
    from cullinan.core import get_application_context
    ctx = get_application_context()

    if ctx is not None and ctx.is_refreshed:
        # 通过 ApplicationContext 创建实例并注入依赖
        instance = ctx._create_class_instance(controller_class)
    else:
        # Fallback: 直接实例化（无依赖注入）
        logger.warning(f"ApplicationContext not available for controller {name}")
        instance = controller_class()
    
    return instance
```

### 3. 在所有入口点设置全局 ApplicationContext

修改以下文件，在创建 `ApplicationContext` 后调用 `set_application_context(ctx)`：

- `cullinan/scanner.py`
- `cullinan/bootstrap.py`
- `cullinan/application.py`
- `cullinan/app.py`

## 测试验证

### 运行所有测试

```bash
python tests/run_all_di_tests.py
```

### 测试套件概览

| 测试文件 | 说明 | 测试数 |
|----------|------|--------|
| `test_di_fix.py` | 基础修复验证 | 3 |
| `test_comprehensive_di.py` | 全方位 DI 测试 | 15 |
| `test_botcontroller_regression.py` | BotController 回归测试 | 4 |

### 全方位测试分类

**专项测试（Controller DI Bug 修复）**：
1. 基础 Controller DI
2. 多服务注入
3. 可选依赖注入
4. hasattr 检查（原 Bug 场景）
5. Controller 单例模式
6. 无 ApplicationContext 时的降级处理

**健壮性测试（Service DI）**：
1. 基础 Service DI
2. 链式注入
3. Service 单例模式
4. 按名称注入
5. 类型推断注入

**边界测试**：
1. 缺少必需依赖
2. 空 Controller（无依赖）
3. 带 `__init__` 的 Controller
4. 并发访问安全

### 预期输出

```
======================================================================
所有测试执行完成
======================================================================
  [PASS] 基础修复验证
  [PASS] 全方位测试套件
  [PASS] BotController 专项回归测试
======================================================================
结果: 全部通过
```

## 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `cullinan/core/__init__.py` | 添加 `get_application_context()` 和 `set_application_context()` |
| `cullinan/controller/registry.py` | 修改 `get_instance()` 使用 ApplicationContext 进行依赖注入 |
| `cullinan/scanner.py` | 添加 `set_application_context(ctx)` 调用 |
| `cullinan/bootstrap.py` | 添加 `set_application_context(ctx)` 调用 |
| `cullinan/application.py` | 添加 `set_application_context(ctx)` 调用 |
| `cullinan/app.py` | 添加 `set_application_context(ctx)` 调用 |

## 新增测试文件

| 文件 | 说明 |
|------|------|
| `tests/test_di_fix.py` | 基础 DI 修复验证（3 个测试） |
| `tests/test_comprehensive_di.py` | 全方位 DI 测试套件（15 个测试） |
| `tests/test_botcontroller_regression.py` | BotController 回归测试（4 个场景） |
| `tests/run_all_di_tests.py` | 所有 DI 测试的运行器 |

## 注意事项

1. `@controller` 和 `@service` 装饰器**不需要**额外添加 `@injectable` 装饰器
2. 依赖注入在 Controller 实例化时通过 `ApplicationContext._create_class_instance()` 自动处理
3. 可选依赖使用 `Inject(required=False)` 标记，未找到时返回 `None`

