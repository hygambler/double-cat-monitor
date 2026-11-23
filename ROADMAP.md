# 双猫生活行为监测 · ROADMAP

更新于 2026-11-13。实际开发、测试与部署状态见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

## 项目背景

最早在 MacBook Air 和 Logitech C920 上验证饮水区方案，随后迁移到 Windows 10 / i7-9700KF / RTX 4060。当前 C920 固定观察白色猫粮碗，记录冲冲与白猫的候选进食次数及有效观测时长。候选事件来自区域停留；实际进食由人工复核确认。长期目标是在单房间内监测两猫的吃粮、饮水和猫砂盆行为，支持低功耗常开、断流恢复、多镜头与手机访问，并研究排便／排尿分类和主动追踪。

```text
C920 最新帧 → YOLO26n-seg 猫分割 → 日夜样本匹配 → 粮区状态机 → SQLite → Streamlit
```

### 代码块、项目角色与知识点

| 代码块／主要文件 | 承担的项目角色 | 涉及的知识点 |
| --- | --- | --- |
| **① 启动与配置**：[__main__.py](catwatch/__main__.py)、[config.windows.json](config.windows.json) | 系统的“总指挥”：读取配置，启动摄像头、模型和看板，协调各模块，处理退出 | Python 函数、条件判断、循环；命令行参数；JSON 配置；文件路径；进程启动与停止 |
| **② 摄像头采集**：[capture.py](catwatch/capture.py) | 系统的“眼睛”：从 C920 连续取帧，保留最新画面，断流后尝试重连 | 图像是像素数组；分辨率、帧率；OpenCV；线程；共享数据与锁；时间戳 |
| **③ YOLO26n 猫咪检测与轮廓分割**：[vision.py](catwatch/vision.py#L97) 中的 `Detector` | 把摄像头画面交给 `yolo26n-seg.pt`，筛选 `cat` 类，得到每只猫的检测框、分割掩膜和检测分数 | Ultralytics 模型加载与推理、检测框、分割掩膜、置信度、CPU/GPU、模型输入尺寸 |
| **④ 特征提取与身份识别**：[vision.py](catwatch/vision.py) 中的 `descriptor`、`coat_pattern`、`identify`、`identify_night`，以及启动流程中的日夜模式选择 | 从猫身体提取毛色和花纹，与样本比较，判断“冲冲／白猫／未知”；按日夜使用相应识别方法 | LAB 颜色空间；直方图；灰度与相对亮度；局部图像分块；特征向量；相似度、距离与阈值 |
| **⑤ 样本采集与登记**：[__main__.py](catwatch/__main__.py) 中的 `snapshot`、`enroll` 命令处理 | 给两只猫建立日间、夜间“参考档案”，供身份程序匹配 | 图像读写；样本标签；特征保存；JSON；样本多样性；校准数据与测试数据的区别 |
| **⑥ 区域与事件判断**：[vision.py](catwatch/vision.py) 的 `in_zone`、[core.py](catwatch/core.py) 的 `VisitEngine` | 判断猫是否进入粮区，把连续画面整理成一次候选进食事件，计算有效观测时长并汇总身份 | 区域坐标；像素覆盖比例；状态机；时间间隔；短暂漏检容忍；身份投票；歧义处理 |
| **⑦ 机位校验与区域修正**：[alignment.py](catwatch/alignment.py) | 判断摄像头是否移动，尝试重新定位粮碗；无法确认或偏移过大时暂停或停止监测 | 图像特征点；特征匹配；SIFT；RANSAC；仿射变换；模板匹配；坐标变换；重试机制 |
| **⑧ 摄像头焦点控制**：[focus.py](catwatch/focus.py) | 接收网页上的对焦请求，由持有摄像头的采集程序执行，并回读结果 | 硬件接口；自动／手动对焦；请求与响应；进程间通信；轮询；设备状态确认 |
| **⑨ 数据保存与展示**：[core.py](catwatch/core.py)、[live.py](catwatch/live.py)、[dashboard.py](dashboard.py) | 保存事件、传递实时预览，并展示分猫统计、人工复核和 CSV 导出 | SQLite 数据库；SQL 查询；事务与 WAL；JPEG、Base64；Pandas 数据处理；Streamlit 网页；定时刷新 |
| **⑩ 自动测试**：[tests 目录](tests) | 检查修改后是否破坏原有功能，例如时长计算、夜间身份判断、机位保护和看板复核 | pytest；断言；测试样本；模拟设备；单元测试与流程测试；回归测试 |
| **⑪ 部署、保护与项目接续**：[process_lock.py](catwatch/process_lock.py)、[WINDOWS_SETUP.md](WINDOWS_SETUP.md)、[PROJECT_STATUS.md](PROJECT_STATUS.md) | 安装运行环境，避免重复启动采集，并记录项目进度供人或其他 agent 接手 | 虚拟环境；依赖管理；PyTorch/CUDA；Windows 启动脚本；文件锁；Git/GitHub；技术文档 |

### 从哪里读 YOLO26 代码

1. [config.windows.json](config.windows.json#L7) 指定本机模型权重 `data/yolo26n-seg.pt`、输入尺寸和检测阈值。[pyproject.toml](pyproject.toml#L6) 声明提供 YOLO 的 `ultralytics` 依赖。`.pt` 保存模型权重，模型实现随依赖安装。
2. [vision.py 的 `Detector`](catwatch/vision.py#L97) 用 `YOLO(...)` 加载权重。每次拿到一帧，[`_detect()`](catwatch/vision.py#L114) 调用 `self.model.predict(...)`。检测框表示猫在画面里的大致位置，分割掩膜标记该猫身体所占的像素，检测分数用于判断本次猫检测的可信度。
3. [监控主循环](catwatch/__main__.py#L231) 把检测结果交给后续逻辑。[ByteTrack](catwatch/tracking.py) 用检测框关联前后帧中的同一只猫。`descriptor()` 用掩膜提取毛色和花纹，`identify()` 或 `identify_night()` 再与样本比对，给出冲冲、白猫或未知。粮区规则和 `VisitEngine` 负责统计候选进食事件。

### 阅读与参与顺序

先读 `VisitEngine` 和对应测试，画出一次入区、漏检、重新出现和离开的时间线。然后阅读 `descriptor`、`identify_night` 和 `enroll`，比较毛色、白脖子或头部花纹能否从不同姿态中稳定提取。最后阅读检测、机位和部署逻辑。登记样本会更新身份参考特征；YOLO 权重由独立的训练流程产生。校准样本与测试片段按拍摄批次隔离。

## 整体路线图

| 阶段 | 交付 | 验收 |
| --- | --- | --- |
| A · 单路夜间可靠性 | 逐帧诊断、轻量跟踪、轨迹级身份和事件复核 | 用相同标注片段比较错名、未知、断轨、重复或误合并、时长误差与延迟 |
| B · 常开与手机初访 | 进程守护、断流退避、活动事件持久化、私有网络手机访问 | 拔插、断网、强制终止、休眠、重启与断电恢复；从 24 小时扩到 7 天，记录离线区间和墙上功耗 |
| C · 多站点 | 独立观察粮碗、水碗、猫砂盆，按画面遮挡与有效像素决定镜头数量 | 多路并发、单路离线隔离、两猫交接、同站点重复事件去重 |
| D · 行为与手机工作台 | 增加独立行为分类，本地 API 与手机 PWA | 区域到访、确认行为和未知可区分；手机能查看趋势、设备状态、复核和管理片段 |
| E · 低功耗迁移 | 用同一负载对照 PC、低功耗 Linux 主机、NPU 板或智能相机 | 端到端延迟、精度、整机功耗、恢复能力和成本可比较 |
| F · 主动追踪 | 可选云台，之后研究滑轨 | 丢失回预置位、限位、断线停机、人工接管与固定站点持续监测通过 |

### A · 夜间诊断与跟踪

1. 短时诊断先记录时间戳、检测框和分数、掩膜面积、亮度、身份距离和粮区状态。绿框消失先查检测、曝光与遮挡；有绿框但未知先查身份；名字跳变再查误识别或两猫交接。原始逐帧判断、算法融合和人工复核均保留来源。测试录像和数据留在本机。
2. 固定一组标注片段，覆盖低头、转身、短长遮挡、切灯、两猫重叠与交接、离开后重入。分别比较当前基线、只补样本、只加跟踪、跟踪加质量筛选和限时身份延续、事件结束后复核。同步记录处理帧率、P50/P95、显存与功耗，错名率、未知比例和漏记分别报告。
3. ByteTrack 作为首个候选。区分建轨、低分框续轨和确认猫名的门槛，核对项目约 2 FPS 下的真实超时时长。轨迹编号标识视频中持续关联的目标；猫名来自可靠的外观证据。已延续的身份不重复投票或自动入库，重叠、持续冲突、超时和重新入镜后重新确认。轨迹预测不计入有效观测时长。
4. 轨迹结束后可综合同一事件的清晰帧复核，记录最终归属延迟。跨断轨合并须有位置、时间和外观证据。优先补夜间低头、侧背身与遮挡照片，再分别评估动物外观模型和低光增强。低光增强须比较身份准确率与颜色偏移，复杂模型需独立测量开销。

研究参考（候选方法，现场效果待验证）：[Multi-Object Tracking by Associating Every Detection Box](https://arxiv.org/abs/2110.06864)，ECCV 2022；预印本 2021；[Simple Online and Realtime Tracking with a Deep Association Metric](https://arxiv.org/abs/1703.07402)，2017；[Robust Associations Multi-Pedestrian Tracking](https://arxiv.org/abs/2206.14651)，2022；2024，检测；2024，检测；2025，检测；2026，预印本，检测/分割等；2024，视频检测预印本；[作者代码](https://github.com/YuHengsss/YOLOV)；预印本 2024，CVPR 2025，跟踪；2025，动物视频个体识别；预印本 2023-11-15，WACV 2024，动物个体识别；2025，低光增强；[CVPR 论文页](https://openaccess.thecvf.com/content/CVPR2025/html/Yan_HVI_A_New_Color_Space_for_Low-light_Image_Enhancement_CVPR_2025_paper.html)。工程参考见 [Ultralytics 跟踪文档](https://docs.ultralytics.com/modes/track)。

### B–F · 产品与部署设计

- **常开与恢复**。每路单独记录健康状态和离线区间，活动事件带唯一 ID，异常中断保存最后有效观测，恢复后新建轨迹。写入与上传可安全重试。覆盖日志轮转、备份和恢复。Windows 摄像头服务会话先实测，低功耗 Linux 再适配守护。
- **多镜头与行为**。固定镜头持续覆盖关键区域，统一调度推理，按站点独立聚合。数据接口保留相机、站点、会话、轨迹、事件 ID、UTC 时间、证据级别、原始／融合／人工身份、结束原因和模型配置版本。猫砂盆先做独立到访，再标注动作序列和可见结果，区分排便、排尿、两者都有、其他和无法判断。蹲姿、刨砂、遮挡和砂团只作为可验证的线索。
- **手机工作台**。近期用 Streamlit 调试和复核，私有访问可评估 [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)。随后用本地 API 和 PWA 展示双猫卡片、时间轴、7／30 天趋势、设备在线、片段及复核。预览按需开启并限带宽；离线空窗单独显示，避免和零次事件混淆。账号认证与私网接入分别设计。
- **低功耗**。先测待机、单路、多路整机功耗，再对照低频巡视、触发升频、事件后降频。保留周期推理，覆盖低头静止的进食。月耗电约为平均功率（W）× 24 × 30 ÷ 1000 kWh。PC 休眠时需要另一台常开设备唤醒。视觉主机承担推理与存储，MCU 可承担电机、限位、看门狗或预筛选。硬件选型需按实测负载决定。[ESP-DL 模型与基准](https://github.com/espressif/esp-dl/blob/master/models/yolo26/README.md)
- **主动追踪**。云台和滑轨用于补充视角。每个预置位独立标定，移动期间暂停相关区域统计，停稳后复核。先核对设备实际公开控制接口，再验证回零、供电、限速、死区、机械限位和指令过期；滑轨还需端点和线缆管理。[ONVIF 能力说明](https://www.onvif.org/blog/2023/11/13/how-to-use-onvif-profiles-to-ensure-interoperability/)

## Mac 与 PC 接续

以 GitHub 的明确提交为共同基线，记录 PC 本地尚未同步的变更。Mac 可参与研究、实现、审查与可运行的测试；Windows / CUDA / C920 的现场验收由 PC 完成，真实身份和进食由用户观察确认。后续代码改动优先通过独立分支和 PR 交接，记录测试和未验证项，并在 [PROJECT_STATUS.md](PROJECT_STATUS.md) 追加时间线。
