#!/usr/bin/env bash
# 构建 ths 实时五档 sidecar（.NET 8）：dotnet publish -> sidecar/bin/
# 前置：同花顺 Linux 客户端 2.9.1.0 已装（/opt/apps/cn.com.10jqka/files/），
#       因为 csproj 直接引用客户端程序集。本脚本只构建、不启动。
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${DOTNET_ROOT:-}" ] && [ -x "${DOTNET_ROOT}/dotnet" ]; then
  DOTNET="${DOTNET_ROOT}/dotnet"
elif command -v dotnet >/dev/null 2>&1; then
  DOTNET="$(command -v dotnet)"
elif [ -x "$HOME/workspace/.dotnet/dotnet" ]; then
  DOTNET="$HOME/workspace/.dotnet/dotnet"; export DOTNET_ROOT="$HOME/workspace/.dotnet"
elif [ -x "$HOME/.dotnet/dotnet" ]; then
  DOTNET="$HOME/.dotnet/dotnet"; export DOTNET_ROOT="$HOME/.dotnet"
else
  echo "error: dotnet not found — install the .NET 8 SDK first" >&2
  exit 1
fi

if [ ! -d /opt/apps/cn.com.10jqka/files ]; then
  echo "error: 同花顺客户端未安装（缺 /opt/apps/cn.com.10jqka/files/），先装 cn.com.10jqka 2.9.1.0" >&2
  exit 1
fi

"$DOTNET" publish -c Release -o bin ThsSidecar.csproj
echo "built: $PWD/bin/ThsSidecar.dll"
