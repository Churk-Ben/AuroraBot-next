"""启动相互隔离的 Panel 离线演示；令牌仅保留在运行期。"""

import argparse
import asyncio
import os
import runpy
import secrets
import shutil
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def run(variant: str, *, open_browser: bool = True) -> None:
    """复用默认 Bot 示例，在退出时等待宿主清理并关闭自有前端。"""
    frontend_port, api_port = (5173, 10271) if variant == "naive" else (5174, 10272)
    origin = f"http://127.0.0.1:{frontend_port}"
    page = f"{origin}/{'kun.html' if variant == 'kun' else ''}"
    api = f"http://127.0.0.1:{api_port}"
    pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
    if not pnpm:
        raise RuntimeError("未找到 pnpm，请先安装项目要求的 Node 与 pnpm。")
    if not (ROOT / "apps/aurora_panel/node_modules/vite").exists():
        raise RuntimeError("缺少前端依赖，请先在仓库根目录执行 pnpm install --frozen-lockfile。")
    for port in (frontend_port, api_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(f"端口 {port} 已被占用，请先关闭占用它的演示窗口。") from error

    data_dir = ROOT / "build" / f"panel-demo-{variant}"
    data_dir.mkdir(parents=True, exist_ok=True)
    token_env = f"AURORA_PANEL_DEMO_{variant.upper()}_TOKEN"
    previous_token = os.environ.get(token_env)
    token = secrets.token_urlsafe(32)
    example_dir = str(ROOT / "examples/default_bot")
    sys.path.insert(0, example_dir)
    try:
        example = runpy.run_path(str(Path(example_dir) / "main.py"))
    finally:
        sys.path.remove(example_dir)
    os.environ[token_env] = token
    args = argparse.Namespace(
        data_dir=data_dir / "data",
        profile=None,
        serve=True,
        port=api_port,
        token_env=token_env,
        allowed_origin=[origin],
        edit_config=False,
        text=None,
        activate=False,
    )
    backend = asyncio.create_task(example["run"](args))
    frontend = None
    try:
        with (data_dir / "vite.log").open("w", encoding="utf-8") as log:
            frontend_env = os.environ.copy()
            frontend_env.pop(token_env, None)
            frontend = await asyncio.create_subprocess_exec(
                pnpm,
                "--filter",
                "@aurorabot/panel",
                "dev",
                "--port",
                str(frontend_port),
                cwd=ROOT,
                env=frontend_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            async with asyncio.timeout(45):
                for port in (api_port, frontend_port):
                    while True:
                        if backend.done():
                            await backend
                            raise RuntimeError("演示后端已退出。")
                        if frontend.returncode is not None:
                            raise RuntimeError(f"前端启动失败，请检查 {data_dir / 'vite.log'}。")
                        try:
                            _, writer = await asyncio.open_connection("127.0.0.1", port)
                        except OSError:
                            await asyncio.sleep(0.1)
                        else:
                            writer.close()
                            await writer.wait_closed()
                            break
            print(f"\n{variant.upper()} Panel 已就绪（离线回显模型，无需供应商密钥）")
            print(f"页面：{page}\nAPI 地址：{api}\n访问令牌：{token}")
            print("在页面连接设置中填写上述 API 地址与令牌。按 Ctrl+C 停止本窗口的演示。", flush=True)
            if open_browser:
                webbrowser.open(page)
            while frontend.returncode is None:
                if backend.done():
                    await backend
                    break
                await asyncio.sleep(0.5)
    finally:
        backend.cancel()
        try:
            await asyncio.gather(backend, return_exceptions=True)
        finally:
            if frontend is not None and frontend.returncode is None:
                if os.name == "nt":
                    cleanup = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/PID",
                        str(frontend.pid),
                        "/T",
                        "/F",
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    await cleanup.wait()
                else:
                    frontend.terminate()
                await asyncio.wait_for(frontend.wait(), timeout=10)
            if previous_token is None:
                os.environ.pop(token_env, None)
            else:
                os.environ[token_env] = previous_token


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Naive UI 或 KunUI 的离线 Panel 演示")
    parser.add_argument("variant", choices=("naive", "kun"))
    parser.add_argument("--no-browser", action="store_true", help="仅启动服务，不自动打开浏览器")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.variant, open_browser=not args.no_browser))
    except KeyboardInterrupt:
        print("\n演示已停止。")
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
