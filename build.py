#!/usr/bin/env python3
"""Universal Python project obfuscation + binary compilation + packaging tool.

Pipeline:
    1. Stage project sources into an isolated workspace.
    2. Obfuscate `.py` files with python-minifier.
    3. Compile selected modules to native extensions with Cython.
    4. Bundle the staged project into a standalone executable via Nuitka.

All pieces rely exclusively on free/open-source tooling and can be applied to
any Python project by editing the config file or passing CLI flags.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set


DEFAULT_CONFIG = {
    "project_name": None,
    "entry": "main.py",
    "output_dir": "dist",
    "copy": {
        "exclude": [
            ".git",
            "__pycache__",
            "dist",
            "build",
            "build_env",
            ".venv",
            "env",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".idea",
            "logs",
            "*.egg-info",
            "*.pyc",
            "*.pyo"
        ]
    },
    "obfuscate": {
        "enabled": True,
        "rename_globals": True,
        "rename_locals": True,
        "remove_literals": True,
        "remove_annotations": True,
        "include_dunder": False,
        "exclude": [
            "build_tools",
            "tests"
        ],
        "skip_files": []
    },
    "cython": {
        "enabled": True,
        "targets": [],
        "exclude": [
            "build_tools",
            "tests"
        ],
        "language_level": "3",
        "nthreads": 0,
        "remove_python": False
    },
    "nuitka": {
        "enabled": True,
        "standalone": True,
        "onefile": True,
        "remove_output": True,
        "assume_yes_for_downloads": True,
        "include_package": [],
        "include_module": [],
        "include_data_dir": [],
        "include_data_files": [],
        "plugin_enable": [],
        "nofollow_imports": [],
        "extra_args": [],
        "cache_dir": ".nuitka_cache"
    }
}


class BuildError(Exception):
    """Custom exception for build process errors."""


@dataclass
class BuildContext:
    project_root: Path
    build_dir: Path
    config: Dict
    stage_root: Path = field(default=None)
    staged_project: Path = field(default=None)


class PythonBundler:
    def __init__(self, ctx: BuildContext, args: argparse.Namespace):
        self.ctx = ctx
        self.args = args
        self.entry_rel = Path(self.ctx.config["entry"])
        self.entry_stage = None
        self.debug = getattr(args, "debug", False)
        self.backup_path: Path | None = None
        self.reuse_stage = False
        self._timings: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _log_header(self, title: str) -> None:
        print("\n" + "=" * 70)
        print(title)
        print("=" * 70)

    def _should_skip_dir(self, rel_parts: Sequence[str], excluded: Set[str]) -> bool:
        return any(part in excluded for part in rel_parts)

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}")

    # ------------------------------------------------------------------
    # Stage preparation
    # ------------------------------------------------------------------
    def stage_project(self) -> None:
        self._log_header("1. 准备隔离构建目录")

        import time
        start = time.perf_counter()

        stage_root = Path(tempfile.mkdtemp(prefix="pybundle_"))
        staged_project = stage_root / "project"

        excludes = set(self.ctx.config.get("copy", {}).get("exclude", []))

        def ignore_patterns(_, names: List[str]) -> Set[str]:
            ignored: Set[str] = set()
            for name in names:
                for pattern in excludes:
                    if Path(name).match(pattern):
                        ignored.add(name)
                        break
            return ignored

        shutil.copytree(
            self.ctx.project_root,
            staged_project,
            ignore=ignore_patterns,
            dirs_exist_ok=False
        )

        self.ctx.stage_root = stage_root
        self.ctx.staged_project = staged_project
        self.entry_stage = staged_project / self.entry_rel

        if not self.entry_stage.exists():
            raise BuildError(f"入口文件不存在: {self.entry_stage}")

        print(f"✓ 已复制项目到临时目录: {staged_project}")
        self._debug(f"Stage 根目录: {stage_root}")
        self._debug(f"入口文件（stage）: {self.entry_stage}")
        self._timings["stage"] = time.perf_counter() - start

    # ------------------------------------------------------------------
    # Backup & restore
    # ------------------------------------------------------------------
    def backup_project(self) -> None:
        if not self.args.backup:
            return

        backup_root = Path(self.args.backup).expanduser().resolve()
        if backup_root.exists():
            if any(backup_root.iterdir()):
                raise BuildError(f"备份目录非空: {backup_root}")
        else:
            backup_root.mkdir(parents=True, exist_ok=True)

        self._log_header("0. 备份当前项目")
        print(f"备份到: {backup_root}")

        shutil.copytree(
            self.ctx.project_root,
            backup_root,
            dirs_exist_ok=True
        )

        self.backup_path = backup_root
        print("✓ 备份完成")

    def restore_from_backup(self) -> None:
        if not self.args.restore:
            raise BuildError("执行恢复时必须提供 --restore <path> 指定备份目录")

        backup_root = Path(self.args.restore).expanduser().resolve()
        if not backup_root.exists():
            raise BuildError(f"备份目录不存在: {backup_root}")

        self._log_header("恢复项目到备份状态")
        print(f"恢复来源: {backup_root}")

        restored = 0
        for source in backup_root.rglob("*"):
            relative = source.relative_to(backup_root)
            target = self.ctx.project_root / relative
            if source.is_dir():
                try:
                    target.mkdir(parents=True, exist_ok=True)
                except PermissionError as exc:
                    raise BuildError(f"无法创建目录 {target}: {exc}") from exc
            else:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                except PermissionError as exc:
                    raise BuildError(f"无法创建目录 {target.parent}: {exc}") from exc
                try:
                    shutil.copy2(source, target)
                except PermissionError as exc:
                    raise BuildError(f"写入文件失败: {target} ({exc})") from exc
                restored += 1

        print(f"✓ 恢复完成，覆盖文件数量: {restored}")
        print("⚠️ 注意: 备份创建后新增的文件/目录不会自动删除，请手动检查。")

    def use_existing_stage(self, stage_root: Path) -> None:
        stage_root = Path(stage_root).expanduser().resolve()
        staged_project = stage_root / "project"

        if not stage_root.exists():
            raise BuildError(f"指定的 stage 目录不存在: {stage_root}")
        if not staged_project.exists():
            raise BuildError(f"stage 目录缺少 project 子目录: {staged_project}")

        self.ctx.stage_root = stage_root
        self.ctx.staged_project = staged_project
        self.entry_stage = staged_project / self.entry_rel
        if not self.entry_stage.exists():
            raise BuildError(f"stage 中入口文件不存在: {self.entry_stage}")

        self.reuse_stage = True
        self._log_header("使用已有 Stage 目录")
        print(f"Stage 路径: {stage_root}")
        self._debug(f"入口文件（stage）: {self.entry_stage}")

    # ------------------------------------------------------------------
    # Obfuscation stage
    # ------------------------------------------------------------------
    def obfuscate_sources(self) -> None:
        cfg = self.ctx.config.get("obfuscate", {})
        if self.args.skip_obfuscate or not cfg.get("enabled", True):
            print("跳过混淆阶段")
            return

        try:
            import python_minifier
        except ImportError as exc:
            raise BuildError("python-minifier 未安装，请运行 pip install python-minifier") from exc

        self._log_header("2. 混淆 Python 源代码")

        import time
        start = time.perf_counter()

        excluded_dirs = set(cfg.get("exclude", []))
        skip_files = {Path(p) for p in cfg.get("skip_files", [])}

        rename_globals = cfg.get("rename_globals", True)
        rename_locals = cfg.get("rename_locals", True)
        remove_literals = cfg.get("remove_literals", True)
        remove_annotations = cfg.get("remove_annotations", True)
        include_dunder = cfg.get("include_dunder", False)

        obfuscated_count = 0
        total_files = 0

        for py_path in self.ctx.staged_project.rglob("*.py"):
            rel_path = py_path.relative_to(self.ctx.staged_project)
            total_files += 1

            if rel_path in skip_files:
                self._debug(f"跳过文件 (skip_files): {rel_path}")
                continue

            if rel_path == self.entry_rel and not cfg.get("obfuscate_entry", True):
                self._debug(f"跳过入口文件混淆: {rel_path}")
                continue

            if self._should_skip_dir(rel_path.parts[:-1], excluded_dirs):
                self._debug(f"跳过目录 (exclude): {rel_path}")
                continue

            if py_path.name == "__init__.py" and not include_dunder:
                self._debug(f"跳过 __init__.py: {rel_path}")
                continue

            original = py_path.read_text(encoding="utf-8")
            try:
                minified = python_minifier.minify(
                    original,
                    rename_globals=rename_globals,
                    rename_locals=rename_locals,
                    remove_literal_statements=remove_literals,
                    remove_annotations=remove_annotations,
                    combine_imports=False
                )
            except Exception as exc:
                print(f"  ✗ 混淆失败 {rel_path}: {exc}")
                continue

            py_path.write_text(minified, encoding="utf-8")
            obfuscated_count += 1
            print(f"  ✓ 混淆 {rel_path}")

        print(f"完成混淆: {obfuscated_count}/{total_files} 个 Python 文件已处理")
        self._debug("混淆阶段完成")
        self._timings["obfuscate"] = time.perf_counter() - start

    # ------------------------------------------------------------------
    # Cython compilation
    # ------------------------------------------------------------------
    def compile_with_cython(self) -> None:
        cfg = self.ctx.config.get("cython", {})
        if self.args.skip_cython or not cfg.get("enabled", True):
            print("跳过 Cython 编译阶段")
            return

        try:
            import Cython  # noqa: F401
        except ImportError as exc:
            raise BuildError("Cython 未安装，请运行 pip install cython") from exc

        self._log_header("3. 使用 Cython 编译为二进制扩展")

        import time
        start = time.perf_counter()

        targets = cfg.get("targets") or ["."]
        excluded_dirs = set(cfg.get("exclude", []))
        skip_files = {Path(p) for p in cfg.get("skip_files", [])}
        language_level = cfg.get("language_level", "3")
        nthreads = cfg.get("nthreads", 0)
        remove_python = cfg.get("remove_python", False)
        self._debug(f"Cython 目标初始列表: {targets}")

        source_list: List[str] = []
        compiled_files: List[Path] = []

        for target in targets:
            target_path = (self.ctx.staged_project / target).resolve()
            if target_path.is_file() and target_path.suffix == ".py":
                rel = target_path.relative_to(self.ctx.staged_project)
                if rel in skip_files:
                    self._debug(f"跳过 Cython 文件 (skip_files): {rel}")
                    continue
                if self._should_skip_dir(rel.parts[:-1], excluded_dirs):
                    continue
                source_list.append(str(rel).replace(os.sep, "/"))
                compiled_files.append(rel)
            elif target_path.is_dir():
                for py_file in target_path.rglob("*.py"):
                    rel = py_file.relative_to(self.ctx.staged_project)
                    if rel in skip_files:
                        self._debug(f"跳过 Cython 文件 (skip_files): {rel}")
                        continue
                    if self._should_skip_dir(rel.parts[:-1], excluded_dirs):
                        continue
                    if rel == self.entry_rel:
                        continue
                    source_list.append(str(rel).replace(os.sep, "/"))
                    compiled_files.append(rel)
            else:
                print(f"  ⚠️ 跳过不存在的 Cython 目标: {target}")

        source_list = sorted(set(source_list))
        self._debug(f"Cython 实际编译文件数: {len(source_list)}")

        if not source_list:
            print("  ⚠️ 未找到需要编译的 Python 文件，跳过该阶段")
            return

        build_script = self.ctx.stage_root / "cython_build.py"
        build_script.write_text(
            textwrap.dedent(
                f"""
                import sys
                from pathlib import Path
                from setuptools import setup
                from Cython.Build import cythonize

                setup(
                    name="cython_staged_build",
                    ext_modules=cythonize(
                        {source_list!r},
                        language_level={language_level!r},
                        nthreads={nthreads!r},
                        compiler_directives={{'always_allow_keywords': True}}
                    ),
                )
                """
            ),
            encoding="utf-8"
        )

        command = [sys.executable, str(build_script), "build_ext", "--inplace", "--force"]
        env = os.environ.copy()
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

        print("运行 Cython 构建...")
        subprocess.run(command, cwd=str(self.ctx.staged_project), check=True, env=env)
        print("✓ Cython 编译完成")
        self._debug("Cython 构建命令已执行")
        self._timings["cython"] = time.perf_counter() - start

        if remove_python:
            removed = 0
            for rel in compiled_files:
                py_file = self.ctx.staged_project / rel
                if py_file.exists() and py_file != self.entry_stage:
                    py_file.unlink()
                    removed += 1
            print(f"  ✓ 已移除 {removed} 个原始 .py 文件")

    # ------------------------------------------------------------------
    # Packaging stage (Nuitka)
    # ------------------------------------------------------------------
    def build_with_nuitka(self) -> Path:
        cfg = self.ctx.config.get("nuitka", {})
        if self.args.skip_package or not cfg.get("enabled", True):
            print("跳过打包阶段")
            return None

        try:
            import nuitka  # noqa: F401
        except ImportError as exc:
            raise BuildError("Nuitka 未安装，请运行 pip install nuitka") from exc

        self._log_header("4. 使用 Nuitka 生成可执行文件")

        import time
        start = time.perf_counter()

        project_name = self.ctx.config.get("project_name") or self.ctx.project_root.name
        output_path = self.ctx.config.get("output_path")
        output_path.mkdir(parents=True, exist_ok=True)
        self._debug(f"Nuitka 输出目录: {output_path}")

        cache_dir = cfg.get("cache_dir") or ".nuitka_cache"
        cache_path = Path(cache_dir)
        if not cache_path.is_absolute():
            cache_path = (self.ctx.project_root / cache_path).resolve()
        cache_path.mkdir(parents=True, exist_ok=True)
        self._debug(f"Nuitka 缓存目录: {cache_path}")

        command: List[str] = [
            sys.executable,
            "-m",
            "nuitka"
        ]

        bool_flags = {
            "standalone": "--standalone",
            "onefile": "--onefile",
            "remove_output": "--remove-output"
        }

        for key, flag in bool_flags.items():
            if cfg.get(key, DEFAULT_CONFIG["nuitka"].get(key, False)):
                command.append(flag)

        if cfg.get("assume_yes_for_downloads", True):
            command.append("--assume-yes-for-downloads")

        command.append(f"--output-dir={output_path}")
        if project_name:
            command.append(f"--output-filename={project_name}")

        for pkg in cfg.get("include_package", []):
            if pkg:
                command.append(f"--include-package={pkg}")

        for module in cfg.get("include_module", []):
            if module:
                command.append(f"--include-module={module}")

        for data_dir in cfg.get("include_data_dir", []):
            if data_dir:
                command.append(f"--include-data-dir={data_dir}")

        for data_file in cfg.get("include_data_files", []):
            if data_file:
                command.append(f"--include-data-files={data_file}")

        for plugin in cfg.get("plugin_enable", []):
            if plugin:
                command.append(f"--plugin-enable={plugin}")

        for nofollow in cfg.get("nofollow_imports", []):
            if nofollow:
                command.append(f"--nofollow-import-to={nofollow}")

        command.extend(cfg.get("extra_args", []))

        command.append(str(self.entry_stage))

        printable_command = " ".join(str(part) for part in command)
        print("运行 Nuitka...")
        print(f"命令: {printable_command}")
        self._debug(f"执行目录: {self.ctx.staged_project}")

        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(self.ctx.staged_project))
        env["NUITKA_CACHE_DIR"] = str(cache_path)

        subprocess.run(command, cwd=str(self.ctx.staged_project), check=True, env=env)
        print("✓ Nuitka 打包完成")

        artifacts = sorted(output_path.iterdir()) if output_path.exists() else []
        if not artifacts:
            raise BuildError("Nuitka 未生成任何可执行文件")

        for artifact in artifacts:
            print(f"  ✓ 生成产物: {artifact}")

        self._timings["nuitka"] = time.perf_counter() - start
        return artifacts[0]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        if self.reuse_stage or self.args.keep_stage:
            print(f"保留临时构建目录: {self.ctx.stage_root}")
            return

        if self.ctx.stage_root and self.ctx.stage_root.exists():
            shutil.rmtree(self.ctx.stage_root)
            print("已清理临时目录")

    def print_timings(self) -> None:
        if not self._timings:
            return
        print("\n====== 阶段耗时（秒） ======")
        for key in ("stage", "obfuscate", "cython", "nuitka"):
            if key in self._timings:
                print(f"{key:>10}: {self._timings[key]:.2f}s")


def load_config(build_dir: Path, config_path: Path | None) -> Dict:
    if config_path is None:
        config_path = build_dir / "build_config.json"

    if not config_path.exists():
        raise BuildError(f"未找到配置文件: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)

    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep clone
    config.update(loaded)

    project_root_value = loaded.get("project_root")
    if not project_root_value:
        raise BuildError("build_config.json 缺少 project_root 字段（需指向待打包项目根目录）")

    project_root = Path(project_root_value).expanduser()
    if not project_root.is_absolute():
        project_root = (config_path.parent / project_root).resolve()

    if not project_root.exists():
        raise BuildError(f"项目根目录不存在: {project_root}")

    config["project_root"] = project_root

    config.setdefault("project_name", project_root.name)
    config.setdefault("entry", "main.py")
    config.setdefault("output_dir", "dist")

    # merge nested dicts
    for key in ("copy", "obfuscate", "cython", "nuitka"):
        defaults = DEFAULT_CONFIG.get(key, {})
        overrides = loaded.get(key, {}) if isinstance(loaded.get(key), dict) else {}
        merged = dict(defaults)
        merged.update(overrides)
        config[key] = merged

    entry_path = (project_root / config["entry"]).resolve()
    if not entry_path.exists():
        raise BuildError(f"入口文件不存在: {entry_path}")

    output_path = (project_root / config["output_dir"]).resolve()

    config["entry_path"] = entry_path
    config["output_path"] = output_path

    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通用 Python 打包工具链 (混淆 + Cython + Nuitka)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--config", type=Path, help="自定义配置文件路径", default=None)
    parser.add_argument("--entry", type=Path, help="覆盖入口文件路径", default=None)
    parser.add_argument("--backup", type=Path, help="在构建前将项目完整备份到该目录")
    parser.add_argument("--restore", type=Path, help="从备份目录恢复项目并退出")
    parser.add_argument("--reuse-stage", type=Path, help="使用已存在的 stage 目录（跳过备份/混淆/Cython）")
    parser.add_argument("--skip-obfuscate", action="store_true", help="跳过混淆阶段")
    parser.add_argument("--skip-cython", action="store_true", help="跳过 Cython 编译")
    parser.add_argument("--skip-package", action="store_true", help="跳过 Nuitka 打包")
    parser.add_argument("--keep-stage", action="store_true", help="保留中间临时目录")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    build_dir = Path(__file__).resolve().parent
    config = load_config(build_dir, args.config)
    project_root = config["project_root"]

    if args.entry:
        config["entry"] = str(args.entry)
        config["entry_path"] = (project_root / config["entry"]).resolve()
        if not config["entry_path"].exists():
            raise BuildError(f"入口文件不存在: {config['entry_path']}")

    ctx = BuildContext(
        project_root=project_root,
        build_dir=build_dir,
        config=config
    )

    bundler = PythonBundler(ctx, args)

    try:
        if args.restore:
            bundler.restore_from_backup()
            return 0

        if args.reuse_stage:
            bundler.use_existing_stage(args.reuse_stage)
        else:
            bundler.backup_project()
            bundler.stage_project()
            bundler.obfuscate_sources()
            bundler.compile_with_cython()
        artifact = bundler.build_with_nuitka()

        print("\n" + "=" * 70)
        print("构建流程完成")
        if artifact:
            print(f"可执行文件已生成: {artifact}")
        else:
            print("可执行文件未生成（可能手动跳过）")
        print("=" * 70)
        return 0

    except subprocess.CalledProcessError as exc:
        print(f"✗ 外部命令失败 (exit={exc.returncode}): {' '.join(str(p) for p in exc.cmd)}")
        return exc.returncode or 1
    except BuildError as exc:
        print(f"✗ 构建失败: {exc}")
        return 1
    finally:
        bundler.cleanup()
        bundler.print_timings()


if __name__ == "__main__":
    sys.exit(main())
