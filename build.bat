@echo off
REM Python 项目打包工具链 - Windows 启动脚本
REM python-minifier + Cython + Nuitka (全部免费)

setlocal enabledelayedexpansion

if "%PYTHON_BIN%"=="" (
    set "PYTHON_BIN=python"
)

%PYTHON_BIN% --version >nul 2>&1
if errorlevel 1 (
    echo X 错误: 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

if not exist "build.py" (
    echo X 错误: 找不到 build.py 文件
    popd
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo X 错误: 缺少 requirements.txt
    popd
    pause
    exit /b 1
)

echo ================================================
echo Python 项目打包工具链
echo python-minifier + Cython + Nuitka
echo ================================================
echo.

echo >> 检查/安装依赖 (python-minifier, Cython, Nuitka)
%PYTHON_BIN% -m pip install --upgrade pip >nul 2>&1

set "WHEEL_DIR=%SCRIPT_DIR%wheels"
if exist "%WHEEL_DIR%\*.whl" (
    echo    使用離線 wheel 安装依赖: %WHEEL_DIR%
    %PYTHON_BIN% -m pip install --upgrade --no-index --find-links "%WHEEL_DIR%" -r requirements.txt
    if errorlevel 1 (
        echo    離線安装失败，尝试在线安装...
        %PYTHON_BIN% -m pip install --upgrade -r requirements.txt
    )
) else (
    %PYTHON_BIN% -m pip install --upgrade -r requirements.txt
)

%PYTHON_BIN% -c "import importlib.util,sys;missing=[m for m in('python_minifier','Cython','nuitka')if importlib.util.find_spec(m) is None];\
import importlib;importlib.invalidate_caches();missing=[m for m in('python_minifier','Cython','nuitka')if importlib.util.find_spec(m) is None];\
print('✗ 缺少依赖: ' + ', '.join(missing)) if missing else None;sys.exit(1 if missing else 0)"
if errorlevel 1 (
    echo X 依赖安装失败，请检查网络或提供 wheels 目录
    popd
    pause
    exit /b 1
)

echo.
echo >> 启动构建流程
%PYTHON_BIN% build.py %*
if errorlevel 1 (
    echo.
    echo X 构建失败！
    popd
    pause
    exit /b %errorlevel%
)

echo.
echo √ 构建成功！
popd
pause
