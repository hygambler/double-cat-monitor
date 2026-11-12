# Windows PC 接续指南

目标机器：用户现有 Windows 10、RTX 4060、i7-9700KF；摄像头仍使用 C920。

迁移包最早在 Mac 上准备，现已在 Windows PC 上验证 RTX 4060 推理、C920 取帧和 WebApp。当前版本的状态、夜间校准和完整运行说明见 [项目说明与进展](PROJECT_STATUS.md)。

## 1. 将文件放到 PC

解压 `cat-water-monitor-windows.zip` 到固定位置，例如 `D:\Projects\cat-water-monitor`。请进入真正包含 `pyproject.toml`、`config.windows.json` 的目录，不要在 ZIP 内直接运行脚本。

早期 ZIP 包包含源码和 YOLO26 nano 分割权重。从 GitHub 获取新版源码时，请将模型权重单独放到 `data/yolo26n-seg.pt`。首次在新 PC 部署需建立 Windows 虚拟环境、框选当前机位的粮区并登记两只猫的样本。

## 2. 安装并验证环境

先安装 Python 3.12（包含 Python launcher），确认 NVIDIA 驱动已安装。然后双击 `scripts\install_windows.bat`。

脚本会在项目自己的 `.venv` 中：

1. 安装官方 CUDA 12.8 索引提供的 PyTorch 与 torchvision。
2. 安装项目依赖和测试工具。
3. 检查 CUDA 是否可用，并实际在 GPU 上执行矩阵运算。
4. 用配置 `device="0"` 加载 YOLO26 并做一次空白帧推理。
5. 执行测试；成功后将 Windows 的具体依赖版本写入 `data\windows-installed.txt`。

GPU 不可用时脚本会报错停止，不能把安装成功当作已使用 4060。若 CUDA 12.8 对应的驱动要求不满足，先在 PC 上检查 `nvidia-smi`，再按 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/) 选择合适的构建或更新驱动，不要盲目反复重装。

Windows 安装脚本使用 pip 单独解析适配 Windows / CUDA 的依赖，**不声称与 Mac 的 uv.lock 形成同一个已验证 GPU 环境**。不要在 CUDA 安装后直接执行普通 `uv sync` 来覆盖 GPU 软件包；待 PC 端验证后再固化专用 GPU 锁定方案。

可手动在项目目录终端检查：

```powershell
.venv\Scripts\python.exe -m catwatch --config config.windows.json doctor --model
```

应显示 `CUDA available: True`、RTX 4060、`GPU computation: PASS` 和 `inference: PASS`。单次通过不代表长期稳定或功耗合格。

## 3. 接 C920、框选吃猫粮区

连接 C920，先固定在粮碗旁。停止采集后双击 `scripts\setup_camera_windows.bat`，等猫离开画面，紧贴白碗四周拖框并按 Enter，保存吃猫粮区和机位基准。Esc 取消。

启动时和此后每小时检查机位。水平、垂直偏移按画面宽高归一化，深度方向用画面尺度变化估计。任一项达到 20% 时停止采集并关闭网页服务。偏移低于 20% 时会在新画面重新匹配白碗，达到 2% 才移动蓝框。暂时无法确认位置时暂停写入事件，每 10 秒重试，持续 2 分钟仍无法确认则停止。停机后先重新框选，再手动启动 `scripts\webapp_windows.bat`。

`config.windows.json` 中 `source=0` 只是默认编号，必须确认画面确为 C920。如无画面，检查 USB、Windows 相机隐私设置是否允许桌面应用、是否被视频会议程序占用，再按实际设备尝试其他编号。

## 4. 校准冲冲和白猫

打开项目目录的 PowerShell。每张照片只拍一只猫，各拍 5–10 张不同姿势。以下只示范一个文件名，请每次换成 02、03 等，以免覆盖。

```powershell
.venv\Scripts\python.exe -m catwatch --config config.windows.json snapshot data/calibration/chong_01.jpg
.venv\Scripts\python.exe -m catwatch --config config.windows.json snapshot data/calibration/moli_01.jpg
```

完成至少三张/猫后：

```powershell
.venv\Scripts\python.exe -m catwatch --config config.windows.json enroll 冲冲 "data/calibration/chong_*.jpg"
.venv\Scripts\python.exe -m catwatch --config config.windows.json enroll 白猫 "data/calibration/moli_*.jpg"
```

程序已支持自行展开通配符。未完成双猫样本登记时，采集可以运行，但身份为 unknown。

## 5. 试跑与看板

双击 `scripts\webapp_windows.bat` 启动采集和看板，然后在浏览器打开 [本机看板](http://127.0.0.1:8501/)。也可以分别运行：

- `scripts\monitor_windows.bat`：GPU 采集与预览；Q 或 Ctrl+C 停止。
- `scripts\dashboard_windows.bat`：生成独立模拟库并打开看板服务。浏览器访问终端显示的 `http://127.0.0.1:8501`；侧栏可以切换模拟数据。

默认 2 次/秒推理、640 输入，保持第一阶段负载设定。粮碗区域停留记为候选进食，看板按猫统计次数与有效观测时长，并支持人工确认进食。

先做 10 分钟现场观察，再做 2 小时、24 小时测试。Windows 自动启动、任务守护和电源设置在实测稳定后再配置；此包不会自动修改系统设置。

## 给 PC 端 Codex 的接续信息

在 PC 的 Codex 中打开解压目录后，告诉它：

> 继续家庭双猫吃猫粮监控项目。Windows 10 / RTX 4060 / i7-9700KF，现有 C920。先阅读 WINDOWS_SETUP.md 和 VALIDATION.md，确认当前确实是 Windows 环境，再验证 Python 3.12、NVIDIA 驱动、CUDA PyTorch 与 YOLO26n-seg。用 config.windows.json；先框选吃猫粮区，再采集冲冲/白猫样本。不要把模拟事件当成实测，也不要先买硬件。
