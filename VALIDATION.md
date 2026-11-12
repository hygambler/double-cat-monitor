# 验证记录

以下为 2026-11-10 的历史验证。Windows 实机和夜间模式的最新验证见 [项目说明与进展](PROJECT_STATUS.md)。

日期：2026-11-10（Asia/Shanghai）

## 当前模型：YOLO26 nano 分割版

已将默认配置切换为 `data/yolo26n-seg.pt`，权重已下载并实际加载。现有锁定的 Ultralytics 8.4.208 可直接运行，无需更换环境。

- 任务：instance segmentation；cat 类 ID 15。
- 640×480 空白帧：0 猫。
- 同一公开双猫样例：2 猫，掩膜像素数 53231 / 60784。
- 预热后 CPU 推理 5 次：P50 32.5 ms、P95 35.0 ms。短测不足以推断现场准确率或长期功耗，也未证明比 YOLO11 更快。
- 切换后完整测试：**13 passed**（包括事件入库、视频回放、看板复核）。
- 现场饮水区与冲冲/茉莉身份准确率仍待 C920 校准验收。

模型文件名称核对自 [Ultralytics 官方 YOLO26 文档](https://docs.ultralytics.com/models/yolo26/)。下面保留初版记录，避免混淆两次模型测量。

## 初版 YOLO11 验证记录（历史）

- 在项目 `.venv` 安装 Python 3.12.14 环境与全部依赖，生成 `uv.lock`。
- 关键版本：Ultralytics 8.4.208、OpenCV 4.14.0.94、PyTorch 2.15.0、Streamlit 1.67.0。
- `python -m pytest -q`：**13 passed**。
- 真实 YOLO11n-seg 权重下载到 `data/yolo11n-seg.pt`，确认 segmentation 任务与 COCO cat 类 ID 15。
- 空白 640×480 图像推理：0 猫。
- 公开 COCO 双猫样例（640×480）推理：2 猫，两张非空实例掩膜，像素数分别 54371、61884。
- 同一样例预热后 CPU 推理 5 次：P50 29.2 ms，P95 29.3 ms。只是当前执行环境、单图短测，不含完整摄像头解码成本，不代表 24 小时功耗或现场性能。
- 模拟库独立生成 3 条事件，不包含真实家庭观测。
- Streamlit 已成功监听 `127.0.0.1:8501`，浏览器核对标题、模拟数据入口及未启动采集的空状态。

公开测试图来源：[Hugging Face documentation-images / coco_sample.png](https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png)。测试图留在工作区临时目录，未作为家庭样本登记，也未加入交付源码包。

## 测试覆盖

- 停留时长、离开宽限、短暂路过丢弃。
- 漏检不累计有效观测秒数，长间断拆段。
- 两猫重叠、连续身份交接、unknown 投票降级。
- 正常停止结算一次，时间倒退拒绝。
- SQLite 并发读取、重新打开保留数据。
- 非法 ROI 配置拒绝。
- 掩膜排除背景、黑白毛色合成样本区分、近似身份返回 unknown。
- 实际生成 AVI 并走 OpenCV 读取 → 模拟检测器 → 真实毛色匹配 → 真实事件逻辑 → SQLite。验证按视频时间而非处理速度计时，两猫分开入库。这个测试不证明真实 YOLO 检测准确率。
- Streamlit AppTest：读取临时真实 SQLite、显示统计、提交喝水复核与修正猫名后核对数据库。

## 尚未完成的现场验收

系统相机信息检查未列出设备，尚未读取 C920 真实画面；这不能证明设备一定未连接，也可能是当前环境的设备可见性限制。

- C920 设备编号、macOS 权限、实际分辨率/FPS。
- 饮水区域坐标（配置初始为 null，不会用任意区域开始统计）。
- 冲冲、茉莉各自现场样本（尚未提供照片，无真实身份特征文件）。
- 饮水区事件精确率/召回率、错名率、unknown 比例。
- 夜间效果、断开/恢复真实 USB 摄像头、24 小时在线率、功耗和内存趋势。
- RTSP/Reolink 实机、多路输入、云台、自动开机启动。

这些项目应按 README 和 ROADMAP 逐项实测；不能用上述单元测试或公开猫图片替代。

## Windows 迁移支持（准备完成，实机待验）

- 新增 `config.windows.json`（YOLO26n-seg，device=0）与 Windows 安装/框选/采集/看板脚本。
- 用跨平台进程锁替换直接导入 fcntl，Windows 分支使用 msvcrt。
- 配置/心跳/毛色特征显式 UTF-8 读写；校准命令自行展开照片通配符。
- 新增 doctor：检查 PyTorch、CUDA、GPU 实际矩阵计算与可选模型推理。
- Mac 回归：16 passed；Mac CPU 模型检查 PASS。进程锁测试验证跨进程互斥与释放。
- 当前没有连接 Windows 运行环境，Windows 锁分支、BAT 脚本、驱动兼容、4060 推理、C920 实机均未验证。
- Windows 安装脚本采用 PyTorch 官方 cu128 wheel 索引，需 PC 上验证驱动/软件包适配。Mac 验证不等于 Windows 验证。
