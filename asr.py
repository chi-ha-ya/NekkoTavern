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
from stt import Faster_Whisper_STT

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
