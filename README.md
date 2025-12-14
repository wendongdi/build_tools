# Python 打包保护工具链

使用 **python-minifier + Cython + Nuitka** 在本地一键完成 Python 项目的混淆、二进制扩展编译与可执行产物生成。全流程仅依赖免费开源组件，可在任何项目内复用。

> **建议**：将 `build_tools` 仓库单独放置在任意目录，通过 `build_config.json` 内的 `project_root` 字段指定需要打包的目标项目路径。

---

## 🚀 流程概览

```
原始项目
   │
   ├─▶ Stage：复制到隔离临时目录
   │
   ├─▶ python-minifier：批量混淆 .py 文件
   │
   ├─▶ Cython：编译选定模块为 .so/.pyd
   │
   └─▶ Nuitka：生成单文件或独立目录可执行程序
```

默认情况下，构建输出位于 `<项目根>/dist/`，临时目录会在流程结束后自动清理。

---

## 📂 目录说明

- `build.py`：主 orchestrator，串联混淆/Cython/Nuitka 阶段
- `build.sh` / `build.bat`：跨平台启动脚本
- `build_config.json`：配置入口文件、排除项、Cython/Nuitka 选项
- `requirements.txt`：最小依赖（python-minifier、Cython、Nuitka）
- `QUICKSTART.md`：3 分钟上手指南
- `USAGE_CN.md`：中文使用手册（含离线安装、故障排查）
- `wheels/`：建议存放离线安装包（如 `nuitka` wheel），仓库内仅提供 `.gitkeep`

---

## ⚙️ 安装依赖

```bash
cd build_tools
pip install -r requirements.txt  # 可选；build.sh/build.bat 会自动安装
```

也可以直接执行 `build.sh`/`build.bat`，脚本会自动检测依赖：
- 默认使用 `pip install -r requirements.txt`
- 检测到 `wheels/` 目录存在离线包时，自动改用 `--no-index --find-links`
- 如果网络/离线安装均失败，将检测现有环境中是否已安装 `python-minifier`、`Cython`、`Nuitka`

推荐在独立虚拟环境或 Conda 环境中执行。若构建机无法访问公网，可在联网机器运行 `pip download python-minifier cython nuitka -d build_tools/wheels`，再通过 `build.sh` 的离线模式安装。需要自定义解释器时，可在运行脚本前设置 `PYTHON_BIN=/path/to/python`。

---

## 🔧 配置示例 (`build_config.json`)

```json
{
  "project_root": "/abs/path/to/your/project",
  "project_name": "ft_futures_risk_ctrl",
  "entry": "main.py",
  "output_dir": "dist",
  "copy": {
    "exclude": [".git", "__pycache__", "dist", "logs", "*.egg-info", "risk_original_backup"]
  },
  "obfuscate": {
    "enabled": true,
    "rename_globals": true,
    "rename_locals": true,
    "remove_literals": true,
    "remove_annotations": true,
    "include_dunder": false,
    "exclude": ["build_tools", "tests"],
    "skip_files": []
  },
  "cython": {
    "enabled": true,
    "targets": ["collect", "risk"],
    "exclude": ["build_tools", "tests"],
    "language_level": "3",
    "nthreads": 0,
    "remove_python": false
  },
  "nuitka": {
    "enabled": true,
    "standalone": true,
    "onefile": true,
    "remove_output": true,
    "assume_yes_for_downloads": true,
    "include_package": ["pandas", "numpy", "sqlalchemy"],
    "include_module": [],
    "include_data_dir": [],
    "include_data_files": [],
    "plugin_enable": [],
    "nofollow_imports": [],
    "extra_args": [],
    "cache_dir": ".nuitka_cache"
  }
}
```

### 关键字段

- `project_root`：待打包项目所在路径（绝对或相对 `build_config.json` 的路径）
- `project_name`：输出文件名，默认使用项目目录名
- `entry`：入口脚本（相对项目根目录）
- `output_dir`：最终产物目录
- `copy.exclude`：Stage 阶段忽略的文件/目录模式
- `obfuscate`：python-minifier 参数，可排除目录/文件
- `rename_globals` 已默认设为 `false`，避免因函数/类名被重命名导致运行时 `AttributeError`
- `cython.targets`：需要转换为二进制扩展的路径（文件或目录）
- `cython.remove_python`：是否在编译成功后删除对应 `.py`
- `nuitka.*`：Nuitka 打包选项：依赖、插件、资源、缓存目录等

所有阶段均可通过配置或命令行开关禁用。

---

## 🏃 常用命令

```bash
# 完整流程（混淆 + Cython + Nuitka，可选备份或复用 Stage）
conda run -n vnpy python build.py --backup /path/to/backup        # 建议：保存当前项目快照
conda run -n vnpy python build.py --restore /path/to/backup       # 可选：从备份恢复
conda run -n vnpy python build.py --reuse-stage /tmp/pybundle_xxx # 已有 stage，仅执行打包

# 调试：跳过某些阶段
python build.py --skip-obfuscate
python build.py --skip-cython
python build.py --skip-package

# 指定入口或配置
python build.py --entry src/app.py --config build_tools/custom.json

# 保留临时目录排查问题
python build.py --keep-stage

# 输出调试日志
python build.py --debug

# 仅恢复备份
python build.py --restore /path/to/backup

> 恢复操作会覆盖备份中的文件，但不会自动删除备份之后新增的文件，请在恢复后自行检查项目目录。若未指定 `--backup`，会提示跳过备份。构建完成后会输出各阶段耗时，便于分析性能瓶颈。
```

执行成功后，可执行文件或目录位于 `<项目根>/<output_dir>/`。

---

## 🧪 Nuitka 使用提示

- **单文件产物**：保持 `"onefile": true`；如需多文件输出，可改为 `false`
- **依赖收集**：
  - `include_package`：等同 `--include-package`
  - `include_module`：等同 `--include-module`
  - `plugin_enable`：启用官方插件（如 `numpy`, `multiprocessing`）
- **资源文件**：
  - `include_data_dir`: `"source=dest"`
  - `include_data_files`: `"path=target"`
- **缓存目录**：`cache_dir` 默认写入项目根 `.nuitka_cache`，避免 `/root/.cache` 权限问题
- **额外参数**：在 `extra_args` 中直接追加 Nuitka CLI 选项

---

## 🐛 调试模式

- 通过 `python build.py --debug`（或在 `build.sh`/`build.bat` 调用时追加 `--debug`）可输出额外步骤信息：stage 目录、跳过文件、Cython 目标、Nuitka 命令等。
- 可配合 `--keep-stage` 查看混淆后的源码与 Cython 产物。
- 更详细的 Nuitka 日志可在 `nuitka.extra_args` 中加入 `--verbose`、`--show-modules` 等参数。

---

## ✅ 当前项目验证

| 命令 | 结果 |
| --- | --- |
| `python build.py --skip-package --skip-cython` | ✅ 仅混淆阶段通过，生成 87 个混淆文件后清理临时目录 |
| `python build.py --skip-package` | ✅ 混淆 + Cython 编译完成 |
| `python build.py --skip-cython` | ⏳ 需等待 Nuitka 打包（可同时启用 `--skip-package` 在资源不足时跳过） |

> 默认配置假设已安装 Nuitka。若目标环境无法联网，请提前把 `nuitka` wheel 放入 `build_tools/wheels/` 并通过 `pip install` 安装后再执行打包。

---

## 🔧 故障排查

| 问题 | 可能原因 | 解决方案 |
| --- | --- | --- |
| `python-minifier` / `Cython` 未安装 | 依赖未部署 | 重新运行 `pip install -r requirements.txt` 或手动安装 wheel |
| Nuitka 缺失或版本过旧 | 未安装或离线环境 | 安装对应 wheel：`pip install build_tools/wheels/Nuitka-*.whl` |
| Nuitka 编译失败 | 依赖缺失、插件未启用 | 根据报错补充 `include_package`、`plugin_enable` 或 `extra_args` |
| 生成结果为空 | 打包被提前终止或输出目录被清理 | 查看日志、确认 `output_dir` 权限，必要时传 `--keep-stage` 调试 |
| 产物体积较大 | 打包包含完整解释器 | 使用精简虚拟环境编译，或关闭 `onefile` 以获得目录输出 |

---

## 📚 参考资料

- [python-minifier](https://github.com/dflook/python-minifier)
- [Cython](https://cython.readthedocs.io/)
- [Nuitka User Manual](https://nuitka.net/doc/user-manual.html)

如需更高级的保护（自定义混淆规则、授权验证等），可在现有框架基础上扩展 `build.py` 各阶段逻辑。祝使用顺利！
