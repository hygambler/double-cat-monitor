#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo '请先按 README 安装项目运行环境。'
  read '?按回车关闭'
  exit 1
fi
.venv/bin/python -m streamlit run dashboard.py
