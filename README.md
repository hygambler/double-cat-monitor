# 冲冲与白猫 · 家庭吃猫粮监测

完整产品目标与分阶段设计见 [双猫生活行为监测架构](docs/PRODUCT_ARCHITECTURE.md)（2026-11-13）：低功耗、故障恢复、多站点、手机工作台及可选主动追踪。该文档记录新增长期目标，实施状态以 PROJECT_STATUS.md 为准。

下一步研究与实施建议见 [夜间身份连续性与轨迹级识别](docs/NEXT_STEPS_RESEARCH.md)（2026-11-13）。由 **Mac 端 agent（Codex）** 整理；Mac 与 PC 两端 agent 将共同参与后续算法设计、代码更新、测试和文档维护。推荐方案尚未实现，现场验收在 Windows PC 上完成。

当前 Windows PC 版本的功能、运行命令、夜间样本验证和待验收事项见 [项目说明与进展](PROJECT_STATUS.md)。本页后续内容包含早期 Mac 部署流程。

第一阶段只用现有 **MacBook Air + Logitech C920 Pro USB 摄像头**。本地 Python/OpenCV → YOLO 猫实例分割 → 现场毛色样本匹配 → 区域事件状态机 → SQLite → Streamlit。无需购买硬件，无需云端 AI 服务或 API Key。

**粮碗区域的持续停留记为候选进食。看板按猫汇总次数和有效观测时长，并支持人工确认进食。** 默认不录视频、不保存事件截图，也不监听麦克风。现场校准照片和模型特征仅保存在本地；首次安装依赖和模型需要联网。YOLO 通用猫类别不会自动认识冲冲和白猫。

## 已提供

- 可安装项目、Python 版本选择、`uv.lock` 依赖锁文件。
- C920/USB 摄像头区域框选、校准照片采集、双猫毛色样本登记。
- YOLO26 nano 实例分割，以猫的前景掩膜提取 LAB 颜色直方图，减少背景干扰。
- 保守身份匹配：距离太远、两只猫样本太相似、未完成校准都返回 `unknown`。
- 单个进食点的连续占用事件；两猫同时进入或连续身份切换，整段归为未知。
- 默认 2 次/秒推理，实时输入仅保留最新帧；摄像头读取失败自动重连。
- 区域停留最少有效观测 3 秒，超过 3 秒没有有效区域检测则结束事件。
- SQLite WAL、人工复核、修正身份、CSV 导出、状态心跳与推理耗时。
- 独立模拟库、真实视频回放入口、核心逻辑与看板测试。

## 目录

```text
cat-water-monitor/
  README.md                 本指南
  ROADMAP.md                布置、验收、后续扩展
  VALIDATION.md             本次验证结果
  pyproject.toml / uv.lock   依赖与锁文件
  config.json               摄像头、区域、身份阈值
  dashboard.py              本地看板
  catwatch/
    core.py                 状态机、SQLite、配置
    capture.py              最新帧采集与断流重试
    vision.py               YOLO 分割与毛色匹配
    __main__.py             采集/框选/校准/演示命令
  tests/                    自动测试
  data/                     模型、照片、数据库、心跳（不入版本库）
```

## Windows PC 部署

Windows 10 / RTX 4060 用户先阅读 [WINDOWS_SETUP.md](WINDOWS_SETUP.md)，使用 `config.windows.json` 和 `scripts/` 下的 Windows 脚本。Mac 的 `.venv` 不可复制到 PC 使用。

## 1. 安装与检查

本机已创建 `.venv` 并安装依赖。也可以双击 `打开看板.command` 启动看板；完成现场校准后双击 `开始监测.command` 启动预览采集（尚未选区域会先打开框选）。首次运行先进入本目录（将终端切到本 README 所在目录）：

```bash
source .venv/bin/activate
python -m catwatch --help
python -m pytest -q
```

迁移到另一台机器，推荐使用 Python 3.12 与 uv：

```bash
uv sync --frozen --dev
source .venv/bin/activate
```

也可用 Python 3.12 创建环境再 `python -m pip install -e . pytest`，但这样不会按 uv.lock 的精确版本安装。不要用当前系统的 Python 3.14 直接安装本项目。

## 2. 不接摄像头也能先看界面

```bash
python -m catwatch demo
python -m streamlit run dashboard.py
```

打开终端显示的本机地址（通常是 http://127.0.0.1:8501），在侧栏勾选 **查看演示数据（模拟）**。三条事件写在 `data/demo.sqlite3`，不会混入实际采集的 `data/events.sqlite3`。重复执行 demo 不重复追加。

看板默认只监听本机。页面刷新按钮重新读取数据库；不自动持续刷新，以减少资源使用。

## 3. C920 放置与权限

先把 C920 固定在粮碗侧上方，以能看清头部靠近粮碗、身体毛色、并且不易被碗沿挡住为准。使用现有夹具/稳定台面即可，不先买云台。以吃猫粮区清晰为优先，无需一次拍到客厅、卧室和厨房全屋。

连接 USB。macOS 若提示相机访问，请允许启动此程序的终端/应用访问相机。关闭正在占用摄像头的会议或录制软件。运行时保持 Mac 唤醒，合盖或睡眠通常会中断采集。

编辑 `config.json` 的 `source`：默认 `0` 仅是 OpenCV 设备编号，**不保证是 C920**。在有内置相机的 Mac 上可能需要 `1` 或其他编号。用下一步预览确认看到的是 C920 的吃猫粮区画面；不要依赖设备顺序长期不变。

若没有读到画面，先检查 macOS 相机权限、USB 连接、其他占用程序，再更换编号。当前测试环境没有列出可用相机，尚未完成 C920 实机测试。

## 4. 框选吃猫粮区

```bash
python -m catwatch setup
```

在预览上拖动矩形，回车确认，Esc 取消。区域保存为 0–1 的归一化坐标。**初始 zone 为 null，程序会拒绝开始真实统计，直到完成此步骤。**

矩形应包含粮碗和猫头接近碗口的区域，尽量避免覆盖旁边过道或休息地。当前触发条件是“区域覆盖至少 8% 的猫前景像素”，猫身体靠近仍可能触发；需要靠摆位和人工验收确定可用阈值。它没有猫头姿态或咀嚼动作模型。

摄像头移动、画面旋转、位置/朝向改变后重新框选，并检查校准。

## 5. 采集冲冲/白猫样本

每只猫单独出现在镜头中，吃猫粮区现场白天光照下各拍 5–10 张，包含侧面、背面、低头等姿态。也可使用手机拍的照片，但相同摄像头/位置/光线的样本更接近实际分布。每张照片只允许检测到一只猫。

```bash
python -m catwatch snapshot data/calibration/chong_01.jpg
python -m catwatch snapshot data/calibration/chong_02.jpg
python -m catwatch snapshot data/calibration/chong_03.jpg
```

移动猫或等它换姿势再执行下一次拍摄，避免三张完全相同。用不同文件名保存白猫的照片后登记：

```bash
python -m catwatch enroll 冲冲 data/calibration/chong_*.jpg
python -m catwatch enroll 白猫 data/calibration/moli_*.jpg
```

每只至少 3 张，登记同一个名字会替换其旧样本。两个名字必须与配置一致；登记完两只猫才启用身份输出。预览框用 cat_1 / cat_2 显示，对应配置顺序的冲冲/白猫；数据库和看板保留中文名字。

身份基于粗粒度毛色，不是可靠的生物身份认证。深色/浅色差异明显且固定光照时更有希望；遮挡、湿毛、阴影、逆光、夜视灰度、相似背景都可能失败。不确定就保留 unknown。等积累现场数据后再评估是否需要专门训练分类器。

## 6. 试跑，再持续运行

开两个终端并分别激活环境。采集端先试跑 10 分钟：

```bash
python -m catwatch run --preview --seconds 600
```

看板端：

```bash
python -m streamlit run dashboard.py
```

采集窗口 Q 或终端 Ctrl+C 停止。正常停止会结算已满足时长的当前候选事件，标记 `stopped`。正式观察去掉预览，以减少图形渲染：

```bash
python -m catwatch run
```

一个数据库只允许一个采集进程。强制杀死进程/突然断电时，最后尚未结束的事件会丢失；已提交 SQLite 事件保留。看板展示已结束事件，当前活动状态由心跳显示。没有视频留存时，复核需依据现场记录，不能回头查看事件画面。

## 7. 用录制视频做可重复验收

手动准备现场视频，复制配置到 `replay.json`，重新为这段视频填写对应的 zone，将 `db` 改为 `data/replay.sqlite3`，`status` 改为 `data/replay-status.json`。然后：

```bash
python -m catwatch --config replay.json run --video /absolute/path/test.mp4
CATWATCH_CONFIG=replay.json python -m streamlit run dashboard.py --server.port 8502
```

回放按视频帧号/FPS 计算事件间隔，运行速度不影响时长。事件时间以回放开始时间为基准，**不是视频原始拍摄时间**。同一视频重跑会新增事件，请每次使用新的回放数据库。不要把回放写到真实库里。

## 参数调整

- `capture_fps=10`, `inference_fps=2`, `imgsz=640`, `device=cpu`：保守起点，不是本机性能保证。
- Apple Silicon 可实测 `device=mps`，与 CPU 比较事件漏检、推理 P95、CPU/内存和功耗后决定。硬件和模型不同，不保证 MPS 更省电。
- `identity_max_distance=.55`：最佳样本距离的上限，调小更保守。
- `identity_margin=.12`：两猫距离差的下限，调大更容易返回 unknown。
- `identity_vote_ratio=.8`：整段事件身份投票比例，unknown 也进入分母。出现两种已知身份则整段未知。
- `min_observed_seconds=3`, `exit_grace_seconds=3`：短路过过滤、短暂遮挡容忍。两个动作间隔过短可能合并；两猫交接会降为未知，不保证一猫一事件。
- 所有参数都必须经过实拍样本验证，不能把默认值当作测得的准确率。

## 数据与隐私

`data/events.sqlite3` 是实际事件库；`data/profiles.json` 是毛色特征；`data/calibration/` 是你主动拍的照片；`data/status.json` 是心跳，不含相机地址和照片。备份运行中的数据库应使用 SQLite backup API，或停止程序后复制，避免只拷贝主文件漏掉 WAL。

第一版数据库无自动清理；仅事件元数据通常增长较慢，仍应定期检查磁盘空间。原始校准照片可在确认样本生成后手动删除；本项目不会主动上传家庭画面。不要把含 RTSP 密码的地址提交到配置/版本库。

## 参考

- YOLO26 模型与分割权重：https://docs.ultralytics.com/models/yolo26/
- Ultralytics Python 预测接口：https://docs.ultralytics.com/modes/predict/
- Streamlit 安装与启动：https://docs.streamlit.io/get-started/installation/command-line

使用开源模型/依赖的许可由各上游提供。若后续做商业分发，再检查 Ultralytics 等依赖的授权条件。
