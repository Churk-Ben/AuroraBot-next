"""以参数列表执行项目工具，并保留输出和退出码。"""

import shutil
import subprocess
from pathlib import Path
from typing import TextIO


def run_process(command: list[str], *, root: Path, output: TextIO) -> int:
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(f"找不到工具：{command[0]}")
    print(f"$ {' '.join(command)}", file=output, flush=True)
    with subprocess.Popen([executable, *command[1:]], cwd=root) as process:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # 等子进程结束后再交回调用方，避免文件回滚与工具写入并行。
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
