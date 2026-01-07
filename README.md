# Python 项目混淆工具

本工具使用 Cython 将 Python 项目编译为 C 扩展（`.so` 文件），在保持程序可执行性的同时使代码不可读。
为了安全起见，工具会在 `dists/` 目录下创建项目的**副本**进行处理，绝对不会修改您的原始源代码。

## 环境准备

安装构建所需的依赖：

```bash
pip install -r requirements.txt
```

*（主要用于安装 `Cython` 和 `setuptools`）*

## 使用方法

## 使用方法

### 1. 基础命令

运行脚本并指定您的源项目路径：

```bash
python3 build_obfuscated.py /path/to/my_project [options]
```

* **运行环境要求**: 运行构建脚本的 Python 版本必须与目标运行环境的 Python 版本完全一致。

#### 核心参数

*   `--include [patterns...]`: 指定**需要编译**的文件模式（白名单）。**支持传入多个模式，用空格分隔**。
*   `--exclude [patterns...]`: 指定**不进行编译**的文件模式（黑名单）。优先级高于 `--include`。**支持传入多个模式，用空格分隔**。
*   `--dirs [dirs...]`: （兼容旧版）指定包含的目录。会自动转换为 `--include ./dir_name/*`。
*   `--cleanup` / `--no-cleanup`: 编译后是否删除原始 `.py` 文件（默认删除）。

#### 模式匹配规则 (Pattern Matching)

工具支持灵活的通配符匹配（支持 `*`），规则如下：

1.  **相对路径匹配 (`./` 前缀)**:
    *   如果模式以 `./` 开头（例如 `./core` 或 `./utils/main.py`），则严格匹配相对于项目根目录的路径。
    *   **目录自动递归**: 如果路径指向一个目录且没有通配符（例如 `./core`），会自动匹配该目录下的所有内容（等同于 `./core/*`）。

2.  **文件名递归匹配 (无前缀)**:
    *   如果模式**不**以 `./` 开头（例如 `utils.py` 或 `__init__.py`），则会在整个项目中递归查找匹配的文件名。

**优先级**: `Exclude` > `Include`。即如果一个文件同时满足包含和排除规则，它将被**排除**。

### 2. 常用示例 (Recommended)

#### 示例 A：只加密特定核心目录

只编译 `risk/bots` 目录下的所有代码，排除所有 `__init__.py`（保留包结构）和 `main.py`（保留入口）。

```bash
python3 build_obfuscated.py ./my_project \
    --include "./risk/bots" \
    --exclude "__init__.py" "main.py"
```

#### 示例 B：加密整个项目，排除测试和配置

加密所有 `.py` 文件，但排除 `tests` 目录、`config.py` 和 `main.py`。

```bash
python3 build_obfuscated.py ./my_project \
    --include "*.py" \
    --exclude "./tests" "config.py" "main.py" "__init__.py"
```

#### 示例 C：仅加密特定名称的文件（递归）

加密项目中所有名为 `algorithm.py` 的文件，无论其在哪层目录下。

```bash
python3 build_obfuscated.py ./my_project \
    --include "algorithm.py"
```

#### 示例 D：加密多个特定目录

同时加密 `core`、`utils` 和 `plugins/payment` 这三个目录，并排除所有 `__init__.py`。

```bash
python3 build_obfuscated.py ./my_project \
    --include "./core" "./utils" "./plugins/payment" \
    --exclude "__init__.py"
```

## 工作流程

1. **复制 (Copy)**: 将项目完整复制到 `dists/{project_name}` 目录。
2. **编译 (Compile)**: 查找副本中指定目录下的 `.py` 文件并编译为 `.so`。
3. **清理 (Clean)**: 删除副本中的原始 `.py` 文件（除非使用了 `--no-cleanup` 参数）。

## 安全与混淆增强

为了进一步提高代码安全性，本工具在编译完成后会自动执行以下操作：

1. **去除符号表 (Strip Symbols)**: 自动调用系统 `strip` 命令处理生成的 `.so` 文件。
    * 移除调试信息和符号表。
    * 使反汇编后的函数名变为无意义的地址，极大增加逆向工程难度。
    * 减小文件体积。

2. **禁用严格类型检查**: 防止因 Cython 类型推断导致的运行时错误。

进入生成的发布目录：

```bash
cd dists/ft_futures_data
export PYTHONPATH=$(pwd)
```

像平常一样运行您的项目（**注意：必须使用与构建时相同的 Python 版本**）：

```bash
python -m risk.pilot --env .env_prod_remote
```

## 常见问题排查 (Troubleshooting)

### `ModuleNotFoundError` / `ImportError`

* **版本不匹配**: 请确保 **构建 (Build)** 和 **运行 (Run)** 使用的是完全相同的 `python`解释器版本。`.so` 文件是与特定 Python 版本绑定的（例如 Python 3.9 编译的文件无法在 Python 3.12 下运行）。
* **缺少 `__init__.py`**: 如果遇到导入错误，请检查构建命令中是否包含了 `--exclude __init__.py`。

### `TypeError: ... expected list, got NoneType`

* **严格类型检查**: Cython 默认会进行严格类型检查。我们已经在构建脚本中禁用了此功能。应该不会再遇到这个问题。

### `OSError: ... /home/ubuntu`

* **路径问题**: 检查您的配置文件或代码中是否有硬编码的 Linux 路径。
