# 双猫生活行为监测 · PROJECT STATUS

更新于 2026-11-13（北京时间）。项目背景、11 个代码模块与后续路线见 [ROADMAP.md](ROADMAP.md)。

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
| 11-13 · Mac / PC 文档接续 | Mac 梳理了夜间轨迹方案、长期产品架构和 11 模块代码地图，已并入 [路线图](ROADMAP.md)。 | 逐帧诊断、ByteTrack 和轨迹级融合仍是计划。 |

## 代码版本与运行状态

GitHub 当前运行代码以 [`454498d`](https://github.com/hygambler/double-cat-monitor/commit/454498dbbe501eed0da5d383e5b7647c81b0275c) 为基线，其夜间事件仍按 3 秒宽限与 80% 投票处理。上述连续性与心跳修正已在 Windows PC 本地验证，**尚未同步到 GitHub**。两端做实验时记录实际使用的代码版本。

Windows 工作台可单独启动来查看历史。关闭浏览器标签不会停止已经启动的采集。一体化模式的采集终端或 Streamlit 服务退出时，监控也会结束。

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
