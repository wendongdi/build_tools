# 快速上手指南

## ⚡ 三步完成 Python 项目的混淆 + 编译 + 打包

### 1. 准备环境

```bash
git clone <this-repo-url> build_tools
cd build_tools
pip install -r requirements.txt  # 可选，build.sh 会自动安装
```

> 建议在独立虚拟环境或 Conda 环境中执行，以保持依赖干净。

### 2. 调整配置（可选）

编辑 `build_config.json`，至少确认：

```json
{
  "project_root": "/abs/path/to/your/project",
  "project_name": "ft_futures_risk_ctrl",
  "entry": "main.py",
 "output_dir": "dist"
}
```

> 请将 `project_root` 调整为待打包项目的绝对路径或相对路径（相对 `build_config.json` 所在目录）。

其他阶段与排除项均可按需修改。

### 3. 一键构建

```bash
# Linux / macOS
./build.sh --backup /path/to/backup   # 可选: PYTHON_BIN=python ./build.sh

# Windows
build.bat --backup D:\backup   # 可选: set PYTHON_BIN=python && build.bat

# 或直接调用 Python
conda run -n vnpy python build.py --backup /path/to/backup
# 若已有 Cython 结果，可复用 Stage 目录
conda run -n vnpy python build.py --reuse-stage /tmp/pybundle_xxx
```

完成后在 `dist/` 目录获取最终可执行文件。

---

## 🔍 命令行选项速查

```bash
python build.py --skip-obfuscate    # 跳过混淆
python build.py --skip-cython       # 跳过 Cython 编译
python build.py --skip-package      # 跳过 Nuitka 打包
python build.py --keep-stage        # 保留临时目录
python build.py --entry app.py      # 指定新的入口
python build.py --config custom.json
python build.py --debug             # 输出调试日志
python build.py --restore /path/to/backup  # 从备份恢复
python build.py --reuse-stage /tmp/pybundle_xxx  # 仅打包，复用 Stage
```

组合使用上述选项即可灵活调试各阶段。

---

## 🧱 生成过程概览

1. **Stage**：将项目复制到隔离目录，避免污染原仓库
2. **Obfuscate**：使用 python-minifier 压缩/重命名源码
3. **Cython**：把目标模块编译成 `.so/.pyd`，提供二进制保护
4. **Nuitka**：编译并打包为可执行产物

每个步骤的日志都会输出到终端，构建失败时即可定位问题。

---

## ❓ 常见问题

- **提示缺少编译器**：安装 gcc/clang（Linux/macOS）或 MSVC/Mingw（Windows）
- **Nuitka 提示缺少依赖**：在 `include_package` / `plugin_enable` 中补充
- **可执行文件体积过大**：在精简虚拟环境打包，或关闭 `onefile`
- **运行缓慢**：单文件模式初次运行需解压，属正常现象

---

祝你打包顺利！
