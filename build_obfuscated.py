import os
import sys
import shutil
import time
import argparse
import subprocess
import fnmatch
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from Cython.Build import cythonize


def is_match(rel_path_obj, pattern):
    """
    Helper to check if a file matches a pattern based on strict rules:
    - If pattern starts with './', match against relative path. 
      Supports directory matching (e.g., './core' matches './core/*').
    - Otherwise, match against filename.
    """
    # Normalize path separator to forward slash for consistency
    rel_path_str = rel_path_obj.as_posix()
    filename = rel_path_obj.name
    
    if pattern.startswith("./"):
        # Match against full relative path
        # Remove ./ prefix
        pat_clean = pattern[2:].rstrip("/")
        
        # 1. Exact match (or wildcard match if * is present)
        if fnmatch.fnmatch(rel_path_str, pat_clean):
            return True
        
        # 2. Directory content match: if pat_clean is a directory, 
        # it should match all files inside.
        if not pat_clean.endswith("*"):
            if fnmatch.fnmatch(rel_path_str, pat_clean + "/*"):
                return True
        
        return False
    else:
        # Match against filename only (recursive)
        return fnmatch.fnmatch(filename, pattern)


def get_files_to_compile(src_dir, include_patterns=None, exclude_patterns=None):
    """
    Walks through the directory and gathers .py files to compile.
    Supports strict glob patterns for inclusion and exclusion.
    """
    src_path = Path(src_dir).resolve()
    files_to_compile = []

    if include_patterns is None:
        include_patterns = []
    if exclude_patterns is None:
        exclude_patterns = []

    for root, dirs, files in os.walk(src_path):
        root_path = Path(root)

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
                rel_path = file_path.relative_to(src_path)
                
                # Logic:
                # 1. If include_patterns exist, file must match at least one.
                # 2. File must NOT match any exclude_patterns.
                
                # Step 1: Inclusion
                if include_patterns:
                    included = False
                    for pat in include_patterns:
                        if is_match(rel_path, pat):
                            included = True
                            break
                    if not included:
                        # Did not match any include pattern
                        continue

                # Step 2: Exclusion (Higher priority, overrides inclusion)
                excluded = False
                for pat in exclude_patterns:
                    if is_match(rel_path, pat):
                        excluded = True
                        break
                
                if excluded:
                    print(f"Skipping excluded file: {file_path}")
                    continue

                if file == "__init__.py":
                    # Usually safe to keep __init__.py as pure python for package recognition,
                    # or compile carefully. For robustness, let's skip obfuscating __init__.py
                    # by default unless requested, but user asked to encrypt core code.
                    # Compiling __init__.py is valid but can sometimes cause issues if it uses certain globals.
                    # We will compile it but be aware.
                    pass

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
                    "emit_code_comments": False,
                    "boundscheck": False,
                    "wraparound": False,
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
        help="Patterns to exclude (e.g., 'main.py', 'tests/*').",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        help="Patterns to include (e.g., 'core/*', '*.py'). If specified, only matching files are compiled.",
    )
    parser.add_argument(
        "--dirs", nargs="*", help="Specific subdirectories to obfuscate (legacy support, converts to include patterns)"
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
    include_patterns = args.include if args.include else []
    
    # Support legacy --dirs by converting to include patterns
    if args.dirs:
        for d in args.dirs:
            # Assumes d is a directory name relative to src
            # We append '*' to match contents if it looks like a directory
            # Clean trailing slash and ensure it starts with ./
            d_clean = d.strip().rstrip(os.sep)
            if d_clean.startswith("./"):
                # Already has prefix
                pat = os.path.join(d_clean, "*")
            else:
                pat = "./" + os.path.join(d_clean, "*")
            include_patterns.append(pat)

    files = get_files_to_compile(
        target_dir, include_patterns=include_patterns, exclude_patterns=args.exclude
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
