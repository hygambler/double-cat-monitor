#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo '请先按 README 安装项目运行环境。'
  read '?按回车关闭'
  exit 1
fi
if .venv/bin/python -c 'from catwatch.core import load_config; import sys; sys.exit(load_config()["zone"] is not None)'; then
  echo '先框选饮水机区域；如果看到内置相机，请取消并按 README 修改 source 编号。'
  .venv/bin/python -m catwatch setup || exit 1
fi
.venv/bin/python -m catwatch run --preview
