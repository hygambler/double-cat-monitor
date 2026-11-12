"""Local live view and SQLite event review."""
from contextlib import closing
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from catwatch.alignment import alignment_enabled, set_alignment_enabled
from catwatch.core import FEEDING_EVENT, ROOT, load_config
from catwatch.focus import FOCUS_MAX, FOCUS_MIN, read_focus, request_focus
from catwatch.live import read_preview

c = load_config(os.environ.get("CATWATCH_CONFIG"))
title = "与".join(c["cats"])
st.set_page_config(page_title=f"{title} · 吃猫粮记录", page_icon="🐈", layout="wide")

TZ = ZoneInfo("Asia/Shanghai")

st.title(title)
st.caption("吃猫粮监控")
is_demo = st.sidebar.checkbox("查看演示数据（模拟）", value=False)
days = st.sidebar.selectbox("查看最近天数", [1, 7, 30], index=1)
path = ROOT / "data/demo.sqlite3" if is_demo else Path(c["db"])


@st.fragment(run_every=0.5)
def show_live():
    st.header("实时监控")
    camera, results = st.columns([2, 1], gap="large")
    preview = read_preview(c["status"])
    try:
        status = json.loads(Path(c["status"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    alignment = status.get("alignment") or {}
    with camera:
        st.subheader("C920 摄像头")
        if status.get("state") == "alignment_stop":
            st.error("机位检查已停止监控。请重新框选粮碗，再手动启动。")
        elif alignment.get("state") == "disabled":
            st.caption("机位检查已关闭 · 按现有蓝框记录")
        elif alignment.get("state") == "retrying":
            st.warning("暂时无法确认粮碗位置，已暂停记录，正在重试。")
        elif alignment.get("checked_at"):
            checked = datetime.fromtimestamp(alignment["checked_at"], TZ).strftime("%H:%M:%S")
            label = "已重新定位粮碗" if alignment["state"] == "adjusted" else "机位正常"
            st.caption(f"上次机位检查 {checked} · {label}")
        if preview:
            st.image(io.BytesIO(preview["jpeg"]))
            captured = datetime.fromtimestamp(preview["captured_at"], TZ).strftime("%H:%M:%S")
            st.caption(f"最近一帧 {captured} · 蓝框为吃猫粮区 · 绿框为检测到的猫")
        else:
            if status.get("state") == "no_signal" and time.time() - status.get("updated", 0) < 8:
                st.warning("C920 暂无信号，采集程序正在尝试重连。")
            else:
                st.info("等待摄像头画面。请确认采集程序正在运行且 C920 已连接。")
    with results:
        st.subheader("YOLO 判断")
        if preview and time.time() - status.get("updated", 0) < 8:
            if status.get("identity_mode") == "night":
                st.caption("身份识别 · 夜间模式")
            if status.get("identity_low_light"):
                st.warning("画面过暗，检测到的猫按身份未知记录。")
        if not preview:
            st.write("暂无实时结果")
            return
        detections = preview["detections"]
        st.metric("当前画面中的猫", len(detections))
        for cat in detections:
            name = "身份未知" if cat["cat"] == "unknown" else cat["cat"]
            if alignment.get("state") == "retrying":
                zone = "机位复核中"
            else:
                zone = "在吃猫粮区" if cat["in_zone"] else "在吃猫粮区外"
            st.write(f"**#{cat['index']} {name}** · {zone}")
        st.caption(f"本帧检测与身份匹配 {preview['inference_ms']:.1f} ms")
        st.caption("YOLO 检测猫，毛色样本用于匹配名字。")


@st.fragment(run_every=2)
def show_alignment_switch():
    with st.expander("机位检查"):
        enabled = alignment_enabled(c)
        if enabled:
            st.caption("已开启 · 每小时检查一次。")
        else:
            st.caption("已关闭 · 采集继续按现有蓝框记录。")
        label = "关闭机位检查" if enabled else "开启机位检查"
        if st.button(label, key="alignment_switch"):
            try:
                set_alignment_enabled(c, not enabled)
            except (OSError, RuntimeError):
                st.warning("暂时无法保存设置，请重试。")
            else:
                st.rerun()


@st.fragment(run_every=1)
def show_focus():
    with st.expander("摄像头对焦"):
        result = read_focus(c["status"], "result")
        request = read_focus(c["status"], "request")
        actual = result.get("value")
        try:
            heartbeat = json.loads(Path(c["status"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            heartbeat = {}
        connected = (result.get("state") in ("ready", "rejected")
                     and heartbeat.get("state") == "running"
                     and time.time() - heartbeat.get("updated", 0) < 8)
        if connected:
            mode = {"manual": "手动", "auto": "自动"}.get(result.get("mode"), "未确认")
            value = f"{actual:g}" if actual is not None else "未读到"
            st.caption(f"摄像头回读 · {mode}对焦 · 焦点 {value}")
        else:
            st.info("等待 USB 摄像头连接。")
        if connected and request.get("id") != result.get("id"):
            st.caption("正在应用对焦设置…")
        elif connected and result.get("state") == "rejected":
            st.warning("摄像头拒绝了这次设置，请查看回读值。")
        elif request.get("mode") == "manual" and actual != request.get("value") and connected:
            st.warning("摄像头回读值与设定值不同。")
        with st.form("camera_focus"):
            target = st.slider("手动焦点数值", FOCUS_MIN, FOCUS_MAX, int(actual) if actual is not None else 15,
                               key="focus_value",
                               step=1, help="点击滑块轨道或拖动滑块，按方向键可微调。数值是摄像头的焦点档位。")
            manual = st.form_submit_button("应用手动焦点", disabled=not connected)
            auto = st.form_submit_button("切回自动对焦", disabled=not connected)
            if manual or auto:
                try:
                    request_focus(c["status"], "manual" if manual else "auto", target)
                    st.caption("已发送设置，等待摄像头回读。")
                except (OSError, RuntimeError):
                    st.warning("暂时无法发送设置，请重试。")


@st.fragment(run_every=4)
def show_records():
    st.header("吃猫粮次数与时长")
    st.caption("系统把猫在粮碗区域持续停留记为候选进食。结合现场观察可复核是否进食，时长按有效观测累计。")
    if is_demo:
        st.warning("正在查看模拟事件。")
    if not path.exists():
        st.info("数据库尚未生成。运行采集程序，或执行 python -m catwatch demo 后选择演示数据。")
        return

    start_day = datetime.now(TZ).date() - timedelta(days=days - 1)
    start_ts = datetime.combine(start_day, datetime.min.time(), TZ).timestamp()
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
            df = pd.read_sql_query("SELECT * FROM events WHERE kind = ? AND start_ts >= ? ORDER BY start_ts DESC",
                                   conn, params=[FEEDING_EVENT, start_ts])
    except (sqlite3.Error, pd.errors.DatabaseError):
        st.warning("暂时无法读取 SQLite，页面会自动重试。")
        return
    df["归属"] = df["reviewed_cat"].fillna(df["cat"]).replace("unknown", "身份未知")
    df["observed_seconds"] = df["observed_seconds"].astype(float)
    candidates = df[df["review"] != "rejected"]
    confirmed = df[df["review"] == "confirmed_eating"]
    cats = [*c["cats"], "身份未知"]
    summary = pd.DataFrame({
        "候选进食次数": candidates.groupby("归属").size().reindex(cats, fill_value=0),
        "候选进食秒数": candidates.groupby("归属")["observed_seconds"].sum().reindex(cats, fill_value=0).round(1),
        "确认进食次数": confirmed.groupby("归属").size().reindex(cats, fill_value=0),
        "确认进食秒数": confirmed.groupby("归属")["observed_seconds"].sum().reindex(cats, fill_value=0).round(1),
    }).rename_axis("猫咪").reset_index()
    st.dataframe(summary, hide_index=True)
    if df.empty:
        st.info("所选时段没有进食候选记录。")
        return
    df["开始"] = pd.to_datetime(df.start_ts, unit="s", utc=True).dt.tz_convert(TZ)
    df["日期"] = df["开始"].dt.strftime("%Y-%m-%d")
    df["区域停留秒"] = (df.end_ts - df.start_ts).round(1)
    cols = st.columns(3)
    cols[0].metric("候选进食", len(candidates))
    cols[1].metric("人工确认进食", len(confirmed))
    cols[2].metric("身份未知（复核后）", int((candidates["归属"] == "身份未知").sum()))
    st.caption("按开始日期归档。区域停留秒包含短暂漏检，有效观测秒按检测到猫的时间累计。")
    counts = df.groupby(["日期", "归属"]).size().unstack(fill_value=0)
    st.bar_chart(counts)
    st.dataframe(df[["id", "开始", "cat", "归属", "区域停留秒", "observed_seconds", "ambiguous", "review", "end_reason"]],
                 column_config={"cat": "模型身份", "observed_seconds": "有效观测秒", "review": "复核状态"},
                 hide_index=True)
    st.download_button("导出当前事件 CSV", df.to_csv(index=False).encode("utf-8-sig"), "feeding-events.csv", "text/csv")
    with st.expander("人工复核 / 修正身份"):
        st.caption("请结合现场观察或独立拍摄的测试视频复核。")
        with st.form("review"):
            event_id = st.selectbox("事件编号", df.id.tolist(), key="review_event")
            review_labels = {"pending": "待复核", "confirmed_eating": "确认进食",
                             "rejected": "未进食", "uncertain": "无法判断"}
            review = st.selectbox("复核结果", list(review_labels), key="review_result",
                                  format_func=review_labels.__getitem__)
            corrected = st.selectbox("身份归属", ["保留模型结果", *c["cats"], "unknown"], key="review_cat")
            if st.form_submit_button("保存复核"):
                with closing(sqlite3.connect(path, timeout=10)) as conn, conn:
                    conn.execute("UPDATE events SET review=?, reviewed_cat=? WHERE id=? AND kind=?",
                                 (review, None if corrected == "保留模型结果" else corrected, int(event_id), FEEDING_EVENT))
                st.rerun()


show_live()
show_alignment_switch()
show_focus()
show_records()
