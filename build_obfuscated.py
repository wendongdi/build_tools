import os
import sys
import shutil
import time
import argparse
import subprocess
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from Cython.Build import cythonize


def get_files_to_compile(
    src_dir, target_dirs=None, exclude_files=None, exclude_dirs=None
):
    """
    Walks through the directory and gathers .py files to compile.
    """
    src_path = Path(src_dir).resolve()
    files_to_compile = []

    # Normalize inputs
    if target_dirs:
        target_dirs = [src_path / d for d in target_dirs]
    if exclude_files:
        exclude_files = set(exclude_files)
    else:
        exclude_files = set()

    if exclude_dirs:
        exclude_dirs = [src_path / d for d in exclude_dirs]
    else:
        exclude_dirs = []

    for root, dirs, files in os.walk(src_path):
        root_path = Path(root)

        # Check if we should skip this directory based on target_dirs
        if target_dirs:
            is_target = False
            for td in target_dirs:
                if root_path == td or td in root_path.parents:
                    is_target = True
                    break
            if not is_target:
                continue

        # Check if we should exclude this directory
        is_excluded = False
        for ed in exclude_dirs:
            if root_path == ed or ed in root_path.parents:
                is_excluded = True
                break
        if is_excluded:
            continue

        # Common exclusions
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
        if ".git" in dirs:
            dirs.remove(".git")
        if ".idea" in dirs:
            dirs.remove(".idea")

        for file in files:
            if file.endswith(".py"):
                file_path = root_path / file

                # Check exclusions
                if file in exclude_files:
                    print(f"Skipping excluded file: {file_path}")
                    continue
                if file == "__init__.py":
                    # Usually safe to keep __init__.py as pure python for package recognition,
                    # or compile carefully. For robustness, let's skip obfuscating __init__.py
                    # by default unless requested, but user asked to encrypt core code.
                    # Compiling __init__.py is valid but can sometimes cause issues if it uses certain globals.
                    # We will compile it but be aware.
                    pass

                # Calculate module name relative to src_dir
                rel_path = file_path.relative_to(src_path)
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

                files_to_compile.append(str(file_path))

    return files_to_compile


def cleanup_files(src_dir, compiled_files, keep_source=False):
    """
    Removes .py and .c files after compilation.
    """
    if keep_source:
        print("Skipping cleanup (--keep-source is set)")
        return

    print("Cleaning up source files...")
    for original_file in compiled_files:
        original_path = Path(original_file)
        c_file = original_path.with_suffix(".c")

        # Remove .py
        if original_path.exists():
            original_path.unlink()
            print(f"Removed: {original_path}")

        # Remove .c
        if c_file.exists():
            c_file.unlink()
            # print(f"Removed: {c_file}")

    # Clean build directories created by setuptools
    build_dir = Path(src_dir) / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("Removed build/ directory")


def run_compilation(src_dir, files_to_compile):
    """
    Runs the Cython build process.
    """
    if not files_to_compile:
        print("No files to compile.")
        return

    # Change working directory to src_dir so setup builds in-place correctly relative to root
    original_cwd = os.getcwd()
    os.chdir(src_dir)

    try:
        # Convert absolute paths to relative to src_dir
        rel_files = [os.path.relpath(f, src_dir) for f in files_to_compile]

        print(f"Compiling {len(rel_files)} files...")

        extensions = []
        for f in rel_files:
            # Construct module name from path: risk/bots/bot.py -> risk.bots.bot
            module_name = str(Path(f).with_suffix("")).replace(os.sep, ".")
            extensions.append(Extension(module_name, [f]))

        try:
            ext_modules = cythonize(
                extensions,
                compiler_directives={
                    "language_level": "3",
                    "always_allow_keywords": True,
                    "annotation_typing": False,
                },
                build_dir="build",
                quiet=False,
            )
        except Exception as e:
            print(f"Cythonize failed: {e}")
            sys.exit(1)

        # Now run setup to build these extensions
        # We pretend we are running: python setup.py build_ext --inplace
        script_args = ["build_ext", "--inplace"]

        # Clean previous args
        original_argv = sys.argv[:]
        sys.argv = ["setup.py"] + script_args

        try:
            setup(ext_modules=ext_modules, script_args=script_args)
        except Exception as e:
            print(f"Build failed: {e}")
            sys.exit(1)
        finally:
            sys.argv = original_argv

    finally:
        os.chdir(original_cwd)


def prepare_dist_directory(src_dir):
    """
    Copies the source directory to dists/{project_name}.
    Returns the path to the new directory.
    """
    src_path = Path(src_dir).resolve()
    project_name = src_path.name

    # Create dists directory in current working directory
    dists_root = Path.cwd() / "dists"
    dists_root.mkdir(exist_ok=True)

    dest_path = dists_root / project_name

    if dest_path.exists():
        print(f"Removing existing build at: {dest_path}")
        shutil.rmtree(dest_path)

    print(f"Copying project to: {dest_path}")
    # ignore hidden files/dirs like .git, .idea, __pycache__
    shutil.copytree(
        src_path,
        dest_path,
        ignore=shutil.ignore_patterns(
            "*.pyc", "__pycache__", ".git", ".idea", ".venv", "venv"
        ),
    )
    return dest_path


def strip_files(root_dir):
    """
    Runs 'strip' on all .so files in the directory to remove symbols.
    """
    strip_cmd = shutil.which("strip")
    if not strip_cmd:
        print("Warning: 'strip' command not found. Skipping binary stripping.")
        return

    print("Stripping compiler symbols from binaries...")
    count = 0
    for root, _, filest in os.walk(root_dir):
        for f in filest:
            if f.endswith(".so"):
                full_path = os.path.join(root, f)
                try:
                    # Use -x on macOS to be safe with shared libs, or safe default on Linux
                    cmd = [strip_cmd, full_path]
                    if sys.platform == "darwin":
                        cmd = [strip_cmd, "-x", full_path]

                    subprocess.run(
                        cmd,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    count += 1
                except Exception as e:
                    print(f"Failed to strip {f}: {e}")

    print(f"Stripped {count} binary files.")


def main():
    parser = argparse.ArgumentParser(
        description="Obfuscate Python project using Cython. (Builds in 'dists/' folder)"
    )
    parser.add_argument("src", help="Path to the source project directory")
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Specific files to exclude (e.g., main.py)",
    )
    parser.add_argument(
        "--dirs", nargs="*", help="Specific subdirectories to obfuscate (default: all)"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        default=True,
        help="Remove .py files after compilation (default: True)",
    )
    parser.add_argument(
        "--no-cleanup", dest="cleanup", action="store_false", help="Keep .py files"
    )

    args = parser.parse_args()

    original_src_dir = os.path.abspath(args.src)

    if not os.path.isdir(original_src_dir):
        print(f"Error: {original_src_dir} is not a directory.")
        sys.exit(1)

    # 1. Prepare dist directory (Copy)
    target_dir = prepare_dist_directory(original_src_dir)
    print(f"Processing build in: {target_dir}")

    # 2. Identify files IN THE TARGET DIR
    # Note: We must pass string path to get_files_to_compile
    files = get_files_to_compile(
        target_dir, target_dirs=args.dirs, exclude_files=args.exclude
    )

    if not files:
        print("No files found to compile matching criteria.")
        sys.exit(0)

    print(f"Found {len(files)} files to compile.")

    # 3. Compilation
    run_compilation(target_dir, files)

    # 3.5 Security: Strip binaries
    strip_files(target_dir)

    # 4. Cleanup
    if args.cleanup:
        cleanup_files(target_dir, files)

    print("Done. Obfuscation complete.")
    print(f"Build location: {target_dir}")


if __name__ == "__main__":
    main()
