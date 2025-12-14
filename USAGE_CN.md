# Python 项目混淆 + 二进制打包工具链使用指南

本指南介绍如何在任意 Python 项目中复用 `build_tools` 内的工具链，完成代码混淆、Cython 编译以及 Nuitka 打包，整个流程仅依赖免费开源组件，适用于离线/内网环境。

---

## 1. 环境准备

1. **建议使用独立环境**：通过 Conda 或 `python -m venv` 创建全新的虚拟环境，避免污染生产环境依赖。
2. **安装必要依赖**：

   ```bash
   git clone <this-repo-url> build_tools
   cd build_tools
   pip install -r requirements.txt
   ```

   - `python-minifier`：源码混淆
   - `Cython`：将 Python 源码编译为 C 扩展
   - `Nuitka`：生成可执行文件/独立目录

3. **离线安装方式**：若无法访问公网，可在联网机器执行：

   ```bash
   pip download python-minifier cython nuitka -d build_tools/wheels
   ```

   将生成的 `.whl` 文件拷贝到目标环境后，运行：

   ```bash
   pip install build_tools/wheels/*.whl

   或直接运行 `build.sh` / `build.bat`，脚本会优先检测 `wheels/` 目录并使用离线安装；若离线失败，再尝试在线安装，并最终确认 `python-minifier`、`Cython`、`Nuitka` 是否已存在于当前环境。
   ```

4. **编译工具链**：
   - Linux：`build-essential`/`gcc`/`clang`
   - macOS：Command Line Tools (`xcode-select --install`)
   - Windows：MSVC (Visual Studio) 或 Mingw-w64

---

## 2. 配置文件 (`build_config.json`)

| 字段 | 描述 |
| --- | --- |
| `project_root` | 待打包项目根目录（绝对或相对 `build_config.json`） |
| `project_name` | 输出产物名称，默认使用项目目录名 |
| `entry` | 入口脚本（相对项目根目录），默认 `main.py` |
| `output_dir` | 构建结果目录，默认 `dist/` |
| `copy.exclude` | Stage 阶段忽略的文件/目录模式 |
| `obfuscate.*` | python-minifier 参数（是否重命名、排除目录等；`rename_globals` 默认关闭以避免属性缺失） |
| `cython.targets` | 需要转换为 C 扩展的文件/目录列表 |
| `cython.remove_python` | Cython 成功后是否删除对应 `.py` |
| `nuitka.*` | Nuitka 打包选项：独立/单文件、插件、资源、缓存目录等 |

配置文件可随时调整，也可在命令行通过参数覆盖入口或关闭某些阶段。

> 使用前请先把 `project_root` 设置为实际的项目根目录（支持绝对路径或相对于 `build_config.json` 的相对路径）。

---

## 3. 基本用法

### 3.1 Linux / macOS

```bash
cd build_tools
./build.sh --backup /path/to/backup   # 或 python build.py --backup ...
```

### 3.2 Windows

```cmd
cd build_tools
build.bat --backup D:\backup   # 或 python build.py --backup ...
```

默认依次执行：

1. **Stage**：复制项目到隔离目录，保证源码安全；
2. **Obfuscate**：使用 python-minifier 混淆 `.py` 文件；
3. **Cython**：将配置中的模块编译为 `.so/.pyd`；
4. **Nuitka**：根据配置生成单文件或目录型可执行产物。

> 如果需要恢复备份，可执行 `python build.py --restore /path/to/backup` 并按照提示操作。
> 恢复操作会覆盖备份中的文件，但不会自动删除新增文件，请恢复后自行核对。构建完成后会输出各阶段耗时，便于分析性能瓶颈。

---

## 4. 常用命令

```bash
python build.py --skip-obfuscate   # 跳过混淆
python build.py --skip-cython      # 跳过 Cython 编译
python build.py --skip-package     # 跳过 Nuitka 打包
python build.py --entry app.py     # 指定自定义入口文件
python build.py --config custom.json
python build.py --keep-stage       # 保留临时目录用于排查
python build.py --debug            # 打印调试信息
python build.py --backup /path/to/backup   # 构建前完整备份
python build.py --restore /path/to/backup  # 从备份恢复后退出
python build.py --reuse-stage /tmp/pybundle_xxx  # 复用已有 Stage，只执行打包
```

可组合使用上述选项。例如先 `--skip-package` 验证混淆/Cython，再启用完整构建。

---

## 5. 常见定制场景

### 5.1 打包额外资源

在 `nuitka.include_data_dir` / `nuitka.include_data_files` 中声明：

```json
"include_data_dir": [
  "config=config",
  "templates=templates"
],
"include_data_files": [
  "config/config.yml=config/config.yml"
]
```

### 5.2 确保依赖被收集

对动态导入或插件式模块，在 `include_package`、`include_module`、`plugin_enable` 中显式声明：

```json
"include_package": ["pandas", "sqlalchemy"],
"plugin_enable": ["numpy", "multiprocessing"]
```

### 5.3 精简 Cython 编译范围

调整 `cython.targets` 以控制编译范围，或直接设置 `"enabled": false` 跳过该阶段。

### 5.4 调整 Nuitka 缓存与参数

- `cache_dir`：默认写入项目根 `.nuitka_cache`，可指向自定义路径；
- `extra_args`：直接附加 Nuitka 原生参数（如 `--clang`、`--lto=yes`）；
- `nofollow_imports`：使用通配符排除无关包，例如 `"tkinter*"`。

---

## 6. 故障排查

| 问题 | 可能原因 | 解决建议 |
| --- | --- | --- |
| `python-minifier` / `Cython` / `Nuitka` 未找到 | 依赖未安装或离线环境 | 使用 `pip install -r requirements.txt` 或安装预下载的 wheel |
| Cython 编译失败 | 目标使用大量动态特性或缺少头文件 | 缩减 `cython.targets`，或安装额外依赖（如 `numpy` headers） |
| Nuitka 报缺失模块 | 动态导入未显式声明 | 在 `include_package` / `include_module` / `plugin_enable` 中补齐 |
| 生成结果为空 | 编译被终止或输出目录不可写 | 查看日志，必要时使用 `--keep-stage` 保留现场 |
| 产物体积过大 | 打包包含完整解释器 | 在精简虚拟环境构建，或关闭 `onefile` 使用目录分发 |
| 单文件运行缓慢 | `--onefile` 需要解压临时文件 | 属正常现象，可改用多文件模式提升启动速度 |

---

## 7. 建议构建顺序

1. `python build.py --skip-cython --skip-package`：快速验证混淆阶段；
2. `python build.py --skip-package`：确认 Cython 编译通过；
3. `python build.py`：执行完整打包流程生成最终产物。

如需进一步调试，可通过 `--keep-stage` 查看 Stage 目录中混淆后的源码与中间产物。

---

## 8. 产物验证

构建完成后，产物位于 `dist/`（或自定义目录）。

- 单文件模式：直接执行 `./dist/ft_futures_risk_ctrl --help`
- 目录模式：进入 `dist/ft_futures_risk_ctrl.dist/` 运行主程序

如需自动化测试，可在脚本结束后执行自定义校验命令。

---

## 9. 临时目录清理

默认会自动删除 `/tmp/pybundle_*`（Linux/macOS）或系统临时目录下的 Stage。若使用了 `--keep-stage`，请在确认无误后手动清理。

---

通过以上流程即可在任意项目中快速复用本工具链，实现源码保护与跨平台分发。如需更高级的混淆或授权校验，可在此基础上扩展 `build.py` 各阶段逻辑。祝构建顺利！
