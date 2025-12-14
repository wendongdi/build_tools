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

### 1. 基础命令

运行脚本并指定您的源项目路径：

```bash
python3 build_obfuscated.py /path/to/my_project --dirs [folders] --exclude [files]
```

* 运行构建脚本的Python版本必须与原项目一致，建议直接用原项目的Python环境来构建。
* `--dirs`: 指定需要加密的文件夹路径（及其子文件夹）。
* `--exclude`: 指定**不进行编译**的文件。
  * **重要提示**：请务必排除 `__init__.py` 以保留包的导入结构。
  * 请排除主入口脚本（如 `main.py`），否则无法直接运行。

### 2. 常用示例（推荐）

如果您只想加密特定文件夹（例如 `risk/bots`），同时确保入口脚本正常工作，请使用以下命令：

```bash
python3 build_obfuscated.py /Users/david/Documents/GitHub/fut_trans_nas/ft_futures_data \
    --dirs risk/bots \
    --exclude pilot.py __init__.py
```

## 工作流程

1. **复制 (Copy)**: 将项目完整复制到 `dists/{project_name}` 目录。
2. **编译 (Compile)**: 查找副本中指定目录下的 `.py` 文件并编译为 `.so`。
3. **清理 (Clean)**: 删除副本中的原始 `.py` 文件（除非使用了 `--no-cleanup` 参数）。

## 运行混淆后的项目

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
