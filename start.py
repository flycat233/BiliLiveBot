# -*- coding: utf-8 -*-
"""
启动脚本
自动检查依赖并启动服务
"""

import sys
import os
import signal

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("=" * 60)
    print(" " * 15 + "B站直播弹幕获取工具")
    print(" " * 20 + "v1.0.0")
    print("=" * 60)
    print()

    # 检查依赖
    print("步骤 1/3: 检查依赖...")
    try:
        import test_install
        if not test_install.check_dependencies():
            print("\n请先安装依赖:")
            print("  pip install -r requirements.txt")
            return
    except Exception as e:
        print(f"检查依赖失败: {e}")
        return

    print()

    # 创建必要的目录
    print("步骤 2/3: 初始化目录...")
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./data/plugins", exist_ok=True)
    print("✓ 目录初始化完成")
    print()

    # 启动服务
    print("步骤 3/3: 启动服务...")
    print()
    print("=" * 60)
    print("服务启动成功!")
    print("请在浏览器中访问: http://127.0.0.1:8001")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    try:
        import uvicorn

        # 创建配置
        config = uvicorn.Config(
            "server:app",
            host="127.0.0.1",
            port=8001,
            reload=False,
            log_level="info"
        )

        # 创建服务器
        server = uvicorn.Server(config)

        # 设置信号处理器（仅对 Windows 有效）
        # 注意：uvicorn 内部会处理信号，这里主要是为了更好的用户体验
        def handle_signal(signum, frame):
            print("\n\n接收到停止信号，正在关闭服务...")
            # 这里不直接退出，让 uvicorn 自己处理清理

        signal.signal(signal.SIGINT, handle_signal)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, handle_signal)

        # 运行服务器
        server.run()

    except KeyboardInterrupt:
        print("\n\n服务已停止")
    except Exception as e:
        print(f"\n启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
