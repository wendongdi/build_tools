#!/bin/bash
# 通用 Python 打包工具链 - Linux/macOS 启动脚本
# python-minifier + Cython + Nuitka (全部免费)

set -euo pipefail

echo "================================================"
echo "Python 项目打包工具链"
echo "python-minifier + Cython + Nuitka"
echo "================================================"
echo ""

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python
fi

if [ -z "${NO_CONDA_ACTIVATE:-}" ] && command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base 2>/dev/null)" || CONDA_BASE=""
    if [ -n "$CONDA_BASE" ] && [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        # shellcheck source=/dev/null
        source "$CONDA_BASE/etc/profile.d/conda.sh"
        if conda env list 2>/dev/null | grep -q "^vnpy"; then
            echo ">> 激活 conda 环境: vnpy"
            CONDA_NO_PLUGINS=true conda activate vnpy || {
                echo "⚠️ 无法自动激活 'vnpy'，继续使用系统 Python"
            }
        fi
    fi
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "✗ 错误: 未找到 Python 解释器，请设置 PYTHON_BIN 或安装 Python"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "build.py" ]; then
    echo "✗ 错误: 找不到 build.py 文件"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo "✗ 错误: 缺少 requirements.txt"
    exit 1
fi

REQUIRE_CMD=("$PYTHON_BIN" -m pip install --upgrade -r requirements.txt)
WHEEL_DIR="$SCRIPT_DIR/wheels"

echo ">> 检查/安装依赖 (python-minifier, Cython, Nuitka)"
"$PYTHON_BIN" -m pip install --upgrade pip >/dev/null 2>&1 || true

if compgen -G "$WHEEL_DIR/*.whl" >/dev/null 2>&1; then
    echo "   使用离线 wheel 安装依赖: $WHEEL_DIR"
    if ! "$PYTHON_BIN" -m pip install --upgrade --no-index --find-links "$WHEEL_DIR" -r requirements.txt; then
        echo "⚠️ 离线安装失败，尝试在线安装..."
        if ! "${REQUIRE_CMD[@]}"; then
            echo "⚠️ 在线安装失败，检查已安装环境..."
        fi
    fi
else
    echo "   尝试在线安装依赖..."
    if ! "${REQUIRE_CMD[@]}"; then
        echo "⚠️ 在线安装失败，将确认现有环境"
    fi
fi

CHECK_SCRIPT=$(
cat <<'PY'
import sys
missing = []
for mod in ("python_minifier", "Cython", "nuitka"):
    try:
        __import__(mod)
    except Exception:
        missing.append(mod)
if missing:
    print("✗ 缺少依赖: {}".format(", ".join(missing)))
    sys.exit(1)
PY
)

if ! "$PYTHON_BIN" - <<PY
$CHECK_SCRIPT
PY
then
    echo "✗ 依赖安装失败，请检查网络或在 wheels/ 目录放置离线包"
    exit 1
fi

OUTPUT_DIR="$PROJECT_ROOT/dist"
if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
fi

echo ""
echo ">> 启动构建流程"
"$PYTHON_BIN" build.py "$@"

EXIT_CODE=$?
echo ""

if [ $EXIT_CODE -ne 0 ]; then
    echo "✗ 构建失败！退出码: $EXIT_CODE"
    exit $EXIT_CODE
fi

echo "✓ 构建成功！产物位于: $OUTPUT_DIR"
