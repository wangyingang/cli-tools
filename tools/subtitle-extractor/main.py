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
    def __init__(self, video_path, crop_ratio=0.2, frame_skip=15):
        self.video_path = video_path
        self.crop_ratio = crop_ratio
        self.frame_skip = frame_skip

    def _preprocess_frame(self, frame):
        """统一的图像预处理"""
        if frame is None: return None
        h, w = frame.shape[:2]
        crop_h = int(h * self.crop_ratio)
        cropped = frame[h - crop_h:h, 0:w]
        
        target_width = 960
        scale = target_width / w
        new_h = int(crop_h * scale)
        cropped = cv2.resize(cropped, (target_width, new_h))
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        # 适度模糊以减少噪点对差分的影响
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        return gray

    def _is_image_similar(self, img1, img2):
        """判断两帧图像是否相似（用于快速跳过OCR）"""
        if img1 is None or img2 is None: return False
        if img1.shape != img2.shape: return False
        
        diff_img = cv2.absdiff(img1, img2)
        _, diff_thresh = cv2.threshold(diff_img, 30, 255, cv2.THRESH_BINARY)
        non_zero_count = cv2.countNonZero(diff_thresh)
        total_pixels = img1.shape[0] * img1.shape[1]
        change_ratio = non_zero_count / total_pixels
        
        return change_ratio < 0.01

    def _is_text_similar(self, str1, str2):
        if not str1: str1 = ""
        if not str2: str2 = ""
        str1 = str1.replace(" ", "")
        str2 = str2.replace(" ", "")
        if str1 == str2: return True
        return SequenceMatcher(None, str1, str2).ratio() > 0.85

    def process_segment(self, start_frame, end_frame, queue):
        ocr_engine = RapidOCR()
        cap = cv2.VideoCapture(str(self.video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        subtitles = []
        current_sub = None
        
        last_img = None
        last_text = ""
        
        # 记录"上一次"处理的时间，用于反向补偿
        # 初始值设为当前位置，避免第一句字幕时间倒流太远
        current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        last_processed_time = current_time 
        
        current_frame_idx = start_frame
        
        while current_frame_idx < end_frame:
            # --- 1. 物理跳帧 (保持最高性能) ---
            frames_skipped = 0
            if last_img is not None:
                for _ in range(self.frame_skip - 1):
                    if current_frame_idx >= end_frame - 1: break
                    cap.grab() # 仅抓取不解码，极快
                    current_frame_idx += 1
                    frames_skipped += 1
            
            # --- 2. 读取当前帧 ---
            ret, frame = cap.read()
            if not ret: break
            
            # 获取当前帧的准确时间
            current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            
            # 进度汇报
            if queue: queue.put(frames_skipped + 1)

            gray = self._preprocess_frame(frame)
            
            # --- 3. 变化检测与时间轴补偿逻辑 ---
            
            # 计算这一跳的时间间隔 (例如 0.5s)
            time_gap = current_time - last_processed_time
            
            # A. 视觉查重：如果画面没变，直接认为字幕没变，跳过OCR
            is_visually_similar = False
            if last_img is not None:
                is_visually_similar = self._is_image_similar(last_img, gray)

            curr_text = ""
            if is_visually_similar:
                curr_text = last_text
            else:
                # 画面变了，做 OCR
                result, _ = ocr_engine(gray)
                if result:
                    texts = [line[1] for line in result if line[2] > 0.6]
                    curr_text = " ".join(texts).strip()

            # B. 文本比对与时间补偿
            if self._is_text_similar(last_text, curr_text):
                # === 情况1：字幕没变 ===
                # 无论是画面没变还是OCR结果没变
                if current_sub:
                    # 将结束时间更新到当前瞬间
                    # (随着循环继续，它会一直延伸，直到发现变了为止)
                    current_sub["end"] = current_time
            else:
                # === 情况2：字幕变了 (出现、消失、或切换) ===
                # 此时，真实的变化点发生在 [last_processed_time, current_time] 之间
                
                if current_sub:
                    # 2.1 旧字幕 -> 新字幕 (切换) 或 旧字幕 -> 空 (消失)
                    if curr_text:
                        # [切换]: 取中间点，让两句话首尾相接
                        split_point = last_processed_time + (time_gap / 2)
                        
                        current_sub["end"] = split_point
                        subtitles.append(current_sub)
                        
                        # 新字幕从中间点开始
                        current_sub = {"text": curr_text, "start": split_point, "end": current_time}
                    else:
                        # [消失]: 延长旧字幕到当前时间 (晚消失)
                        # 保证覆盖整个跳帧区间
                        current_sub["end"] = current_time
                        subtitles.append(current_sub)
                        current_sub = None
                else:
                    # 2.2 空 -> 新字幕 (出现)
                    if curr_text:
                        # [出现]: 从上一次检查的时间开始 (早出现)
                        # 这样可以覆盖前面的盲区，确保不漏字
                        # 注意：第一句不要变成负数
                        start_t = max(0.0, last_processed_time)
                        current_sub = {"text": curr_text, "start": start_t, "end": current_time}

            # 更新状态
            last_text = curr_text
            last_img = gray
            last_processed_time = current_time
            current_frame_idx += 1
        
        # 循环结束，保存最后一句
        if current_sub:
            subtitles.append(current_sub)
            
        cap.release()
        return subtitles

# ================= 辅助与包装函数 =================
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

def listener_thread(queue, pbar):
    while True:
        try:
            n = queue.get(timeout=1)
            if n == "DONE": break
            pbar.update(n)
        except:
            if not pbar.disable: continue
            break

# ================= 主程序 =================
def main():
    parser = argparse.ArgumentParser(description="多进程视频硬字幕提取", prog="subx")
    parser.add_argument("video_path")
    parser.add_argument("--processes", type=int, default=8)
    parser.add_argument("--skip", type=int, default=15)
    parser.add_argument("--crop", type=float, default=0.2)
    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print("❌ 文件不存在")
        return

    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    print(f"🎬 视频: {video_path.name}")
    print(f"📊 帧数: {total_frames} | FPS: {fps:.2f}")
    print(f"🚀 模式: {args.processes}进程 | 跳帧: {args.skip}")

    manager = multiprocessing.Manager()
    queue = manager.Queue()

    segment_length = total_frames // args.processes
    tasks = []
    for i in range(args.processes):
        start = i * segment_length
        end = total_frames if i == args.processes - 1 else (i + 1) * segment_length
        tasks.append((str(video_path), start, end, i+1, args.crop, args.skip, queue))

    pbar = tqdm(total=total_frames, unit="frame", mininterval=0.5)
    monitor = threading.Thread(target=listener_thread, args=(queue, pbar))
    monitor.start()

    results = []
    ctx = multiprocessing.get_context('spawn')
    
    with ctx.Pool(processes=args.processes) as pool:
        for res in pool.imap(run_worker, tasks):
            results.append(res)
    
    queue.put("DONE")
    monitor.join()
    pbar.close()

    print("\n📦 正在合并与去重...")
    
    final_subs = []
    all_subs_flat = []
    for chunk_subs in results:
        all_subs_flat.extend(chunk_subs)
        
    if all_subs_flat:
        final_subs.append(all_subs_flat[0])
        for sub in all_subs_flat[1:]:
            last = final_subs[-1]
            # 简单的文本去重
            if SequenceMatcher(None, last['text'], sub['text']).ratio() > 0.85:
                # 如果两句话内容一样，且时间接近（允许因为补偿逻辑产生的轻微重叠），则合并
                # 这里的阈值设大一点，因为我们现在主动延长了时间
                if sub['start'] - last['end'] < 1.0: 
                    last['end'] = max(last['end'], sub['end'])
            else:
                final_subs.append(sub)

    output_path = video_path.with_suffix(".srt")
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(final_subs):
            f.write(f"{i+1}\n")
            f.write(f"{format_time(sub['start'])} --> {format_time(sub['end'])}\n")
            f.write(f"{sub['text']}\n\n")
            
    print(f"✅ 完成！字幕文件: {output_path}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()