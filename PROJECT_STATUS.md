# 双猫生活行为监测 · PROJECT STATUS

更新于 2026-11-14（北京时间）。项目背景、11 个代码模块与后续路线见 [ROADMAP.md](ROADMAP.md)。

## 进展时间线

| 日期 | 完成与验证 | 仍待验证 |
| --- | --- | --- |
| 11-10 · Mac 原型 | 验证 YOLO 分割、区域事件、SQLite 和 Streamlit 复核。YOLO11 原型切换为 YOLO26n-seg，Mac 回归从 13 项增至 16 项。准备 CUDA 安装和 Windows 接续脚本。 | 当时尚未用 Windows/C920 验证。仓库中的 Windows ZIP 为这一阶段的历史安装包。 |
| 11-10～12 · Windows 接续 | 验证 RTX 4060 CUDA 推理和 C920 实际取帧。重新框选纸板上的白色粮碗，记录冲冲与白猫的候选进食；WebApp 展示实时画面、事件和身份。增加机位检查开关、数值对焦、复核与 CSV 导出。 | 长时间在线、真实功耗、温升和物理拔插恢复。 |
| 11-12 · 夜间识别 | 登记冲冲 6 张、白猫 3 张。白猫包含一张全身与两张局部照。逐张留出：冲冲 6/6 判对，白猫 2/3 判对、1 张未知；冲冲按批次留出 6/6。确认实时自动进入夜间模式，25 项测试通过。先前错记为冲冲的白猫事件已人工修正。 | 同批样本验证覆盖有限，整夜错名、漏检和未知比例仍待实测。 |
| 11-12 22:25 · 首次夜测 | 机位检查关闭，C920 手动焦点 15。现场观察白猫一次进食被拆成 #3–#5 三条未知事件，有效观测合计 23.5 秒；记录间隔约 43.5 秒和 3 秒。 | 没有保留长间隔的逐帧证据，无法确定是漏检、移出粮区还是其他情况。三条原始事件保留。 |
| 11-12 22:34 · PC 连续性修正 | 夜间宽限由 3 秒增至 10 秒，事件身份门槛由 80% 降至 60%。看板同时展示逐帧身份和事件暂定身份，28 项测试通过。 | 修正上线后至停机没有新增入库事件，实际进食效果待验证。 |
| 11-12 22:51:29 · 异常中断 | 状态文件记下 `PermissionError`，首轮未跑完整夜。 | 当晚只保留异常类型，无法确认持有文件的具体进程。 |
| 11-13 · PC 修复与复测 | 用同一个写入函数在 Windows 复现：读者打开 `status.json` 时替换可报 WinError 5。PC 本地加入有限重试，持续占用时跳过该次心跳，下一次继续写；其他退出尽可能保留异常详情。29 项测试通过，真实文件占用与解除后恢复写入已验证；C920 短测完成取帧与正常退出。 | 正式采集尚未重启，整夜复测待做。 |
| 11-13～14 · 第一次正式测试 | 清零后从 21:57 开始，22:54 保存一条 39.5 秒的未知身份事件。现场确认夜灯随后异常关闭，画面进入无灯光状态。系统于 11 月 14 日 02:43 随电脑意外关机停止。 | 无光阶段不具备用 C920 验证 YOLO、ByteTrack 或毛色身份识别的条件，本次不能作为正常夜间灯光准确率结论。 |
| 11-13～14 · ByteTrack 与事件截图 | 接入 ByteTrack，低分检测可续接已有轨迹；同一轨迹的可靠身份可短时延续。候选进食累计 5 秒有效观测且身份已确认时，把带 YOLO 分割、ByteTrack 框和粮区框的 JPEG 写入事件。白猫现场事件 #2、#3 已成功保存截图。回归测试增至 33 项。 | 仍需在夜灯稳定开启的整晚测试中核对错名、未知、断轨、事件拆分和截图覆盖率。 |
| 11-13 · Mac / PC 文档接续 | Mac 梳理了夜间轨迹方案、长期产品架构和 11 模块代码地图，已并入 [路线图](ROADMAP.md)。 | 逐帧诊断、ByteTrack 和轨迹级融合仍是计划。 |

## 代码版本与运行状态

一次候选进食累计至少 5 秒有效观测，且当前画面与事件身份一致时，抓取一帧，叠加 YOLO 分割轮廓、ByteTrack 框与轨迹编号、粮区蓝框。事件结算时将 JPEG 和拍摄时间一并写入 SQLite，工作台可按事件编号查看。回放和白猫现场事件均已验证截图入库。

ByteTrack 的低分检测只可续接既有轨迹，且仅能延续已有的粮区事件。可靠身份在同一轨迹上经三次同名识别后可延续最多五秒，沿用结果不重复计作身份票。可信检测显示同一轨迹离开粮区时结算事件；粮区出现明确的另一个轨迹编号时也分段。完全漏检时维持原有宽限，漏检时长不计入有效观测。看板显示轨迹编号及身份沿用状态。

本次同步把 Windows PC 已验证的夜间连续性、心跳写入重试、ByteTrack、事件截图、依赖锁文件和 33 项测试推送到 GitHub `main`。猫照片、身份特征、SQLite 记录和模型权重继续保存在本机。

## 本地服务器、监控与工作台

项目中的“本地服务器”是 Streamlit 后台，只监听本机 `127.0.0.1:8501`。工作台是浏览器访问该服务器后显示的页面。浏览器负责展示实时画面、状态、SQLite 统计、人工复核和截图，本身不控制摄像头、不运行 YOLO，也不直接保存事件。

正式监控使用 [`scripts/webapp_windows.bat`](scripts/webapp_windows.bat)。无需打开 Codex，双击该脚本即可执行 `python -m catwatch --config config.windows.json web`。该命令在同一个启动终端中运行采集、YOLO、ByteTrack、事件状态机和 SQLite，并启动 Streamlit 子进程。然后打开 [本机工作台](http://127.0.0.1:8501/)。

- 关闭浏览器标签或浏览器，不影响已经运行的监控。
- 保持启动脚本弹出的终端窗口运行。终端中按 Ctrl+C、关闭终端或停止 Streamlit 后台，会结束一体化监控。
- 电脑睡眠、关机或重启会中断采集。恢复后重新双击 `webapp_windows.bat`。
- 如果本地服务已经运行，只打开工作台地址即可。重复启动会因端口或采集锁冲突而失败。
- [`scripts/monitor_windows.bat`](scripts/monitor_windows.bat) 只运行带 OpenCV 预览窗口的采集，适合现场调试。
- [`scripts/dashboard_windows.bat`](scripts/dashboard_windows.bat) 会生成独立模拟库并运行展示页，用于界面演示。正式监控使用 `webapp_windows.bat`。

```text
C920 → YOLO 分割 → ByteTrack → 身份与粮区事件 → data/events.sqlite3
                                                       ↓
采集进程 → data/status.live.json → Streamlit 127.0.0.1:8501 → 浏览器工作台
```

## 数据地址与格式

项目根目录为 `C:\Users\yuhey\Documents\Codex\2026-11-10\new-chat\work\cat-water-monitor`。运行数据位于其 `data\` 子目录，并由 `.gitignore` 排除，不会随源码推送到 GitHub。

| 地址 | 格式 | 内容与使用方式 |
| --- | --- | --- |
| `data/events.sqlite3` | SQLite 3 | 正式候选进食事件、模型身份、人工复核、有效观测时长。截图保存在 `events.snapshot_jpeg` BLOB，时间在 `snapshot_ts`；可用工作台或 DB Browser 查看。 |
| `data/events.sqlite3-wal`、`-shm` | SQLite WAL 临时文件 | 监控运行时的事务日志和共享内存。备份时使用 SQLite backup API，或停机后复制主库；不要只复制运行中的主文件。 |
| `data/backups/*.sqlite3` | SQLite 3 | 人工清零或阶段测试前保存的历史数据库备份。 |
| `data/demo.sqlite3` | SQLite 3 | 工作台演示数据，与正式记录隔离。 |
| `data/profiles.json` | JSON 数值数组 | 冲冲和白猫的日间 LAB 毛色与相对花纹特征。 |
| `data/night-profiles.json` | JSON 数值数组 | 两只猫的夜间身份特征。当前本机冲冲、白猫各 6 张有效样本。 |
| `data/calibration/**/*.jpg` | JPEG | C920 采集的日间、夜间单猫校准照片。部分人工复核拼图为 PNG。 |
| `data/yolo26n-seg.pt` | PyTorch 权重 | YOLO26 nano 分割模型。体积较大，部署时单独准备，不上传本仓库。 |
| `data/status.json` | JSON | 采集心跳、运行状态、帧数、当前模式、亮度、活动事件和推理耗时。 |
| `data/status.live.json` | JSON + Base64 JPEG | 工作台最近一帧预览、检测结果、轨迹信息和推理时间；持续覆盖，不是历史录像。 |
| `data/status.alignment.json` | JSON + Base64 JPEG | 手动框选时的机位基准、粮区坐标和参考画面。 |
| `data/status.alignment-switch.json` | JSON | 工作台的机位检查开关。对应 `.lock` 文件用于防止并发写入。 |
| `data/status.focus-request.json`、`status.focus-result.json` | JSON | 工作台提交的焦点请求及 C920 回读结果。 |
| `data/first-formal-test.json`、`night-trial-*.json` | JSON | 阶段测试的起点、配置和现场结论。 |
| `data/windows-installed.txt` | UTF-8 文本 | Windows 环境安装完成时记录的 Python 包版本。 |
| `config.windows.json` | JSON | C920、YOLO、日夜阈值、粮区、数据库和状态文件路径。 |
| `.venv\` | Python 虚拟环境 | Windows 本机依赖和可执行文件，不上传 GitHub，也不能跨操作系统复制。 |

源码由 `catwatch/*.py`、`dashboard.py`、`scripts/*.bat`、配置、测试和 `uv.lock` 组成。GitHub 用于同步这些可复现文件；家庭画面、猫身份样本、事件截图和正式数据库只留在本机。

## 现场规则

- Windows 请求 1280×720、10 FPS，默认每秒推理 2 次、输入尺寸 640、YOLO 猫检测门槛 0.45。粮区覆盖至少 8% 的猫掩膜才视为入区，至少累计 3 秒有效观测才保存事件。
- 画面灰度中位数大于 75 用日间样本，24–75 用夜间样本；低于 24 时仍检测猫，身份未知。夜间毛色和相对花纹须指向同一只猫。整段至少三次同名识别才可命名，未知帧计入投票分母，两猫重叠或同段名字冲突则保留未知。PC 本地短时漏检可延续事件，但漏掉的时间不计入有效观测时长。
- 开启机位检查时，启动即检查，此后每小时复查。X/Y 为画面归一化平移，Z 为画面尺度变化估计。低于 2% 保持蓝框，达到 2% 且各项小于 20% 时重新匹配白碗；任一项达到 20% 停机。无法确认时暂停统计，每 10 秒重试，持续 120 秒停机。恢复时重新框选并手动启动。
- 对焦滑块为 0–250 整数档位，点击应用后看设备回读，也可切回自动。C920 读帧失败约 2 秒后尝试重连。已备好依赖和权重时，本地 USB 采集、推理和入库无需互联网。睡眠、关机和进程退出会中断监控。

## Windows 安装、启动和恢复

1. 在当前源码目录准备 Python 3.12（包含 launcher）、兼容 CUDA 12.8 的 NVIDIA 驱动和 `data/yolo26n-seg.pt`。可从 [Ultralytics 模型页](https://docs.ultralytics.com/models/yolo26/) 获取权重，或从历史 ZIP 中只提取权重。运行 [安装脚本](scripts/install_windows.bat)，它会创建 Windows 虚拟环境，验证 CUDA、GPU 推理并运行测试。已有可用虚拟环境时可直接继续配置。
2. 将 C920 固定对准白色粮碗。停止占用摄像头的采集后运行 [框选脚本](scripts/setup_camera_windows.bat)，拖框并按 Enter，保存区域和机位基准。若无画面，检查 USB、相机权限和设备编号。
3. 在采集停止时，用 `snapshot` 保存单猫照片。每只猫在相应光照下至少登记三张不同姿势的照片。相同猫名重复登记会替换对应样本库里的该猫样本，重启采集后生效。以下以夜间登记为例，白天登记时省略 `--night`。

   ```powershell
   .\.venv\Scripts\python.exe -m catwatch --config config.windows.json snapshot data/calibration/night-chong-01.jpg
   .\.venv\Scripts\python.exe -m catwatch --config config.windows.json enroll --night 冲冲 "data/calibration/night-chong-*.jpg"
   .\.venv\Scripts\python.exe -m catwatch --config config.windows.json enroll --night 白猫 "data/calibration/night-white-*.jpg"
   ```

4. 用 [一体化启动脚本](scripts/webapp_windows.bat) 开始采集和看板，打开 [本机工作台](http://127.0.0.1:8501/)，检查实时画面、蓝框、模式和焦点回读。终端按 Ctrl+C 正常退出。若已有独立历史看板占用 8501，先退出该服务再启动一体化模式。GPU 自检、测试及独立看板命令如下。

   ```powershell
   .\.venv\Scripts\python.exe -m catwatch --config config.windows.json doctor --model
   .\.venv\Scripts\python.exe -m pytest -q
   $env:CATWATCH_CONFIG = (Resolve-Path config.windows.json).Path
   .\.venv\Scripts\python.exe -m streamlit run dashboard.py
   ```

`data/events.sqlite3` 保存正式事件与复核，`data/demo.sqlite3` 保存独立模拟数据。备份运行中的数据库用 SQLite backup API，也可停机后复制。日夜样本特征、校准照片、预览、焦点与机位基准均存于本机 `data/`；更换机位后重新框选。录像回放使用 `run --video`，给回放配置单独的数据库、状态文件和适用区域，时长按视频时间计算。

## 下一次验收

先用已修复的 PC 版本做整夜复测，核对新增事件、在线时长和日志。按路线图收集经标注的短片段，定位漏检、身份变化和事件拆分，再对照评估跟踪与身份融合。同步测量实际墙上功耗、C920 温升及 USB 重连。
