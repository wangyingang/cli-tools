import cv2
import argparse
import datetime
import multiprocessing
import threading
import time
import numpy as np
from pathlib import Path
from difflib import SequenceMatcher
from tqdm import tqdm
from rapidocr_onnxruntime import RapidOCR

# ================= 核心工作类 =================
class SegmentWorker:
    def __init__(self, video_path, crop_ratio=0.2, frame_skip=10):
        self.video_path = video_path
        self.crop_ratio = crop_ratio
        self.frame_skip = frame_skip

    def _is_image_similar(self, img1, img2):
        if img1 is None or img2 is None: return False
        if img1.shape != img2.shape: return False
        
        # === 核心优化：二值化处理 ===
        # 1. 计算两张图的绝对差值
        diff_img = cv2.absdiff(img1, img2)
        
        # 2. 只有变化剧烈的像素才会被关注
        # 字幕出现/消失通常会产生极大的像素亮度变化 (0 -> 255)
        # 背景微动通常变化较小 (例如 50 -> 60)
        # 我们设定阈值 30，忽略掉所有微小的背景变化和噪点
        _, diff_thresh = cv2.threshold(diff_img, 30, 255, cv2.THRESH_BINARY)
        
        # 3. 计算有多少个像素发生了剧烈变化
        # countNonZero 极快
        non_zero_count = cv2.countNonZero(diff_thresh)
        
        # 4. 判断比例
        # 如果剧烈变化的像素占比低于 1% (0.01)，则认为画面(字幕)没变
        total_pixels = img1.shape[0] * img1.shape[1]
        change_ratio = non_zero_count / total_pixels
        
        return change_ratio < 0.01

    def _is_text_similar(self, str1, str2):
        if not str1 or not str2: return False
        return SequenceMatcher(None, str1, str2).ratio() > 0.85

    # 新增 queue 参数用于汇报进度
    def process_segment(self, start_frame, end_frame, queue):
        ocr_engine = RapidOCR()
        cap = cv2.VideoCapture(str(self.video_path))
        
        # 跳转到分段起始点
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        subtitles = []
        current_sub = None
        last_img = None
        
        current_frame_idx = start_frame
        
        while current_frame_idx < end_frame:
            # 物理跳帧：grab
            frames_skipped = 0
            for _ in range(self.frame_skip - 1):
                if current_frame_idx >= end_frame: break
                cap.grab()
                current_frame_idx += 1
                frames_skipped += 1
            
            if current_frame_idx >= end_frame: 
                # 汇报跳过的帧数
                if queue: queue.put(frames_skipped)
                break

            ret, frame = cap.read()
            current_frame_idx += 1
            
            # 汇报进度 (跳过的 + 刚才 read 的这1帧)
            if queue: queue.put(frames_skipped + 1)

            if not ret: break

            current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

            # --- 图像处理 ---
            h, w = frame.shape[:2]
            crop_h = int(h * self.crop_ratio)
            cropped = frame[h - crop_h:h, 0:w]
            
            target_width = 960
            scale = target_width / w
            new_h = int(crop_h * scale)
            cropped = cv2.resize(cropped, (target_width, new_h))
            gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            # --- 视觉查重 & OCR ---
            if last_img is not None and self._is_image_similar(last_img, gray):
                if current_sub:
                    current_sub["end"] = current_time
            else:
                last_img = gray
                result, _ = ocr_engine(gray)
                
                txt = ""
                if result:
                    texts = [line[1] for line in result if line[2] > 0.6]
                    txt = " ".join(texts).strip()
                
                if not current_sub:
                    if txt:
                        current_sub = {"text": txt, "start": current_time, "end": current_time}
                else:
                    if txt:
                        if self._is_text_similar(current_sub["text"], txt):
                            current_sub["end"] = current_time
                        else:
                            if current_sub["end"] - current_sub["start"] > 0.2:
                                subtitles.append(current_sub)
                            current_sub = {"text": txt, "start": current_time, "end": current_time}
                    else:
                        if current_sub["end"] - current_sub["start"] > 0.2:
                            subtitles.append(current_sub)
                        current_sub = None
        
        if current_sub:
            subtitles.append(current_sub)
            
        cap.release()
        return subtitles

# ================= 包装函数 =================
def run_worker(args):
    video_path, start_frame, end_frame, idx, crop, skip, queue = args
    worker = SegmentWorker(video_path, crop, skip)
    return worker.process_segment(start_frame, end_frame, queue)

def format_time(seconds):
    td = datetime.timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

# ================= 监听线程 =================
def listener_thread(queue, pbar):
    while True:
        try:
            # 从队列获取增量，超时1秒防止死锁
            n = queue.get(timeout=1)
            if n == "DONE":
                break
            pbar.update(n)
        except:
            if not pbar.disable: # 如果进度条还没关，继续
                continue
            break

# ================= 主程序 =================
def main():
    parser = argparse.ArgumentParser(description="多进程视频硬字幕提取 (带实时进度)")
    parser.add_argument("video_path")
    parser.add_argument("--processes", type=int, default=8)
    parser.add_argument("--skip", type=int, default=15)
    parser.add_argument("--crop", type=float, default=0.2)
    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print("文件不存在")
        return

    # 1. 获取视频信息
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    print(f"🎬 视频: {video_path.name}")
    print(f"📊 总帧数: {total_frames} | 并发进程: {args.processes}")

    # 2. 准备多进程通讯
    # 使用 Manager 来管理跨进程 Queue
    manager = multiprocessing.Manager()
    queue = manager.Queue()

    # 3. 切分任务
    segment_length = total_frames // args.processes
    tasks = []
    for i in range(args.processes):
        start = i * segment_length
        end = total_frames if i == args.processes - 1 else (i + 1) * segment_length
        # 把 queue 传进去
        tasks.append((str(video_path), start, end, i+1, args.crop, args.skip, queue))

    # 4. 启动进度条监听线程
    # 使用 total_frames 作为总长度，这样精度就是“帧”
    pbar = tqdm(total=total_frames, unit="frame", mininterval=0.5)
    monitor = threading.Thread(target=listener_thread, args=(queue, pbar))
    monitor.start()

    # 5. 并行执行
    results = []
    ctx = multiprocessing.get_context('spawn')
    
    with ctx.Pool(processes=args.processes) as pool:
        # 这里不再包裹 tqdm，进度由 listener 线程负责
        # imap 依然用于收集结果
        for res in pool.imap(run_worker, tasks):
            results.append(res)
    
    # 任务全部完成，通知监听线程退出
    queue.put("DONE")
    monitor.join()
    pbar.close()

    print("\n📦 正在合并字幕片段...")
    
    # 6. 合并结果
    final_subs = []
    all_subs_flat = []
    for chunk_subs in results:
        all_subs_flat.extend(chunk_subs)
        
    if all_subs_flat:
        final_subs.append(all_subs_flat[0])
        for sub in all_subs_flat[1:]:
            last = final_subs[-1]
            time_gap = sub['start'] - last['end']
            if time_gap < 0.5 and SequenceMatcher(None, last['text'], sub['text']).ratio() > 0.85:
                last['end'] = sub['end'] 
            else:
                final_subs.append(sub)

    # 7. 保存
    output_path = video_path.with_suffix(".srt")
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(final_subs):
            f.write(f"{i+1}\n")
            f.write(f"{format_time(sub['start'])} --> {format_time(sub['end'])}\n")
            f.write(f"{sub['text']}\n\n")
            
    print(f"✅ 完成！文件已保存: {output_path}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
