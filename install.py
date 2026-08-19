import sys
import subprocess
import time
import tkinter as tk
from tkinter import messagebox
import os

os.system("")

libs_with_deps = [
    "pyside6==6.10.2",
    "av==17.0.0",
    "pytubefix==10.11.0",
    "python-vlc==3.0.21203",
    "adblock==0.6.0"
]

libs_no_deps = []

start_time = time.time()


def enable_ansi_colors():
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        stdout_handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
        mode.value |= 0x0004
        kernel32.SetConsoleMode(stdout_handle, mode)


def tkinter_message_box(title, message, type="info", yes_no=False):
    root = tk.Tk()
    root.withdraw()
    if yes_no:
        result = messagebox.askyesno(title, message)
    elif type == "error":
        messagebox.showerror(title, message)
        result = False
    else:
        messagebox.showinfo(title, message)
        result = True
    root.destroy()
    return result


def check_python_version_and_confirm():
    major, minor = sys.version_info[:2]
    if major == 3 and minor in [11, 12, 13]:
        return tkinter_message_box(
            "Confirmation",
            f"Python version {sys.version.split()[0]} detected.\n\n"
            "Click YES to install dependencies or NO to exit.",
            yes_no=True
        )
    else:
        tkinter_message_box(
            "Python Version Error",
            "This program requires Python 3.11, 3.12, or 3.13.\n\nExiting...",
            type="error"
        )
        return False


def upgrade_pip_setuptools_wheel(max_retries=3, delay=3):
    packages = ["pip", "setuptools", "wheel"]
    for package in packages:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", package, "--no-cache-dir"]
        for attempt in range(max_retries):
            try:
                print(f"\nUpgrading {package} (attempt {attempt + 1}/{max_retries})...")
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
                print(f"\033[92mSuccessfully upgraded {package}\033[0m")
                break
            except subprocess.CalledProcessError as e:
                print(f"Attempt {attempt + 1} failed: {e.stderr.strip()}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)


def install_uv():
    print("\n\033[92mInstalling uv package manager...\033[0m")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        print("\033[92mSuccessfully installed uv\033[0m")
    except subprocess.CalledProcessError as e:
        print(f"\033[91mFailed to install uv: {e.stderr.strip()}\033[0m")
        raise


def install_libraries(libraries, with_deps=True, max_retries=3, delay=3):
    failed = []
    multiple_attempts = []

    for library in libraries:
        for attempt in range(max_retries):
            try:
                print(f"\nInstalling {library} (attempt {attempt + 1}/{max_retries})...")
                if with_deps:
                    command = ["uv", "pip", "install", library]
                else:
                    command = ["uv", "pip", "install", library, "--no-deps"]

                subprocess.run(command, check=True, capture_output=True, text=True, timeout=480)
                print(f"\033[92mSuccessfully installed {library}\033[0m")
                if attempt > 0:
                    multiple_attempts.append((library, attempt + 1))
                break
            except subprocess.CalledProcessError as e:
                print(f"Attempt {attempt + 1} failed: {e.stderr.strip()}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    failed.append(library)

    return failed, multiple_attempts


def main():
    enable_ansi_colors()

    if not check_python_version_and_confirm():
        sys.exit(1)

    print("\n" + "=" * 50)
    print("YouTube Downloader - Development Setup")
    print("=" * 50)

    print("\n\033[92mUpgrading pip, setuptools, and wheel...\033[0m")
    upgrade_pip_setuptools_wheel()

    install_uv()

    print("\n\033[92mInstalling libraries with dependencies...\033[0m")
    failed1, multiple1 = install_libraries(libs_with_deps, with_deps=True)

    print("\n\033[92mInstalling libraries without dependencies...\033[0m")
    failed2, multiple2 = install_libraries(libs_no_deps, with_deps=False)

    all_failed = failed1 + failed2
    all_multiple = multiple1 + multiple2

    print("\n" + "-" * 50)
    print("Installation Summary")
    print("-" * 50)

    if all_failed:
        print("\033[91m\nFailed to install:\033[0m")
        for lib in all_failed:
            print(f"\033[91m  - {lib}\033[0m")

    if all_multiple:
        print("\033[93m\nRequired multiple attempts:\033[0m")
        for lib, attempts in all_multiple:
            print(f"\033[93m  - {lib} ({attempts} attempts)\033[0m")

    if not all_failed and not all_multiple:
        print("\033[92mAll libraries installed successfully on first attempt.\033[0m")
    elif not all_failed:
        print("\033[92mAll libraries eventually installed successfully.\033[0m")

    end_time = time.time()
    total_time = end_time - start_time
    minutes, seconds = divmod(total_time, 60)
    print(f"\n\033[92mTotal time: {int(minutes):02d}:{seconds:05.2f}\033[0m")

    if all_failed:
        tkinter_message_box(
            "Installation Warning",
            f"Some packages failed to install:\n{', '.join(all_failed)}\n\n"
            "Please check the console output for details.",
            type="error"
        )
    else:
        tkinter_message_box(
            "Installation Complete",
            "All dependencies have been installed successfully!\n\n"
            "You can now run the application with:\n  python main.py"
        )


if __name__ == "__main__":
    main()
