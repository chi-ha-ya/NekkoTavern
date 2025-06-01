import pyaudio
import numpy as np
from faster_whisper import WhisperModel
import queue
import threading
import os
import webrtcvad
import time
from pydub import AudioSegment
import pyperclip  # 用于复制文本到剪贴板
import keyboard

# 麦克风参数
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 16000  # Whisper 模型支持的采样率
CHUNK = int(SAMPLE_RATE * 1)  # 1秒的音频数据
CHUNK_ACTIVATION_RATE = 0.4  # 激活率阈值,低于此视为静音
SPEECH_START = "<start>"  # 说话开始的特殊字符
SPEECH_END = "<end>"  # 说话结束的特殊字符
SILENCE_THRESHOLD_MS = 1000  # 说话结束的静音阈值（毫秒）

# 全局变量
text_queue = queue.Queue()
is_recording = False


class Faster_Whisper_STT:
    def __init__(self, text_queue, model_path="./model/faster-whisper-small"):
        self.audio_queue = queue.Queue()
        self.text_queue = text_queue  # 用于将识别结果传递到主线程
        self.stop_event = threading.Event()
        self.is_recording = False
        self.audio_stream = None
        # 初始化 VAD
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(0)  # 设置 VAD 的灵敏度,范围 0-3,0 最不灵敏

        # 指定模型路径
        self.model_path = model_path

        # 检查模型文件是否存在
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件未找到: {model_path}")

        # 加载本地模型
        self.model = WhisperModel(model_path, device="cuda",
                                  compute_type="float16", local_files_only=True)

    def start(self):
        global is_recording
        if self.is_recording:
            return
        self.is_recording = True
        is_recording = True
        self.stop_event.clear()
        self.recording_thread = threading.Thread(
            target=self.record_audio, daemon=True)
        self.recognizing_thread = threading.Thread(
            target=self.recognize_audio, daemon=True)
        self.recording_thread.start()
        self.recognizing_thread.start()
        print("语音输入已启动。")

    def stop(self):
        global is_recording
        if not self.is_recording:
            return
        self.is_recording = False
        is_recording = False
        self.stop_event.set()
        self.recording_thread.join()
        self.recognizing_thread.join()
        self.recording_thread = None
        self.recognizing_thread = None
        print("语音输入已停止。")

    def is_speech(self, data):
        frame_size = int(SAMPLE_RATE * 0.02 * 3)  # 10ms* 3的帧大小
        num_frames = len(data) // frame_size
        count = 0
        for i in range(num_frames):
            frame = data[i * frame_size:(i + 1) * frame_size]
            if self.vad.is_speech(frame, SAMPLE_RATE):
                count += 1
            if count > CHUNK_ACTIVATION_RATE * num_frames:
                return True
        return False

    def record_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS,
                        rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK)
        speech_buffer = bytearray()
        speech_detected = False
        silence_count = 0
        silence_threshold_chunks = int(
            SILENCE_THRESHOLD_MS * (SAMPLE_RATE / CHUNK) / 1000)
        while not self.stop_event.is_set():
            data = stream.read(CHUNK)
            if self.is_speech(data):
                if not speech_detected:
                    self.audio_queue.put(SPEECH_START)  # 检测到说话开始
                    speech_detected = True
                speech_buffer.extend(data)
                silence_count = 0
            else:
                if speech_detected:
                    silence_count += 1
                    if silence_count >= silence_threshold_chunks:  # 静音超过阈值
                        self.audio_queue.put(bytes(speech_buffer))  # 将语音数据放入队列
                        speech_buffer.clear()
                        speech_detected = False
                        silence_count = 0
        stream.stop_stream()
        stream.close()
        p.terminate()

    def recognize_audio(self):
        while not self.stop_event.is_set():
            if not self.audio_queue.empty():
                item = self.audio_queue.get()
                if item == SPEECH_START:
                    self.text_queue.put(SPEECH_START)  # 将说话开始标志放入 text_queue
                else:
                    audio_data = np.frombuffer(item, dtype=np.int16)
                    segments, info = self.model.transcribe(audio_data.astype(
                        np.float16) / np.iinfo(np.int16).max, beam_size=5)
                    recognized_text = " ".join(segment.text.strip()
                                               for segment in segments)
                    print(f"[{info.language}] {recognized_text}")
                    self.text_queue.put(recognized_text)  # 将识别结果放入 text_queue
                    self.text_queue.put(SPEECH_END)  # 将说话结束标志放入 text_queue
            time.sleep(0.1)


def output_text_to_input_field():
    while True:
        if not text_queue.empty():
            text = text_queue.get()
            if text == SPEECH_START:
                continue
            elif text == SPEECH_END:
                continue
            else:
                # 将识别的文本复制到剪贴板
                pyperclip.copy(text)
                print(text)
                # 模拟 Ctrl+V 粘贴
                keyboard.press_and_release('ctrl+v')
        time.sleep(0.1)


def main():
    # 初始化语音识别器
    stt = Faster_Whisper_STT(text_queue)

    # 启动语音识别
    stt.start()

    # 启动文本输出线程
    output_thread = threading.Thread(
        target=output_text_to_input_field, daemon=True)
    output_thread.start()

    print("语音输入已启动，正在监听语音输入。")
    print("按 Ctrl+C 停止程序。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("正在停止语音输入...")
        stt.stop()
        print("语音输入已停止。")


if __name__ == "__main__":
    main()
