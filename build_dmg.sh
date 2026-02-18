#!/bin/bash
# ByteFarm 构建 - 调用 Python 脚本（确保使用当前 Python 环境）
cd "$(dirname "$0")"
exec python build.py
