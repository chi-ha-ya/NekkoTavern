import pyaudio
import numpy as np
from faster_whisper import WhisperModel
import queue
import threading
import os
import webrtcvad
import time
from pydub import AudioSegment

# 麦克风参数
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 16000  # Whisper 模型支持的采样率
CHUNK = int(SAMPLE_RATE * 0.5)  # 0.5秒的音频数据
CHUNK_ACTIVATION_RATE = 0.4  # 激活率阈值,低于此视为静音
SPEECH_START = "<start>"  # 说话开始的特殊字符
SPEECH_END = "<end>"  # 说话结束的特殊字符
SILENCE_THRESHOLD_MS = 1000  # 说话结束的静音阈值（毫秒）


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
        if self.is_recording:
            return
        self.is_recording = True
        self.stop_event.clear()
        self.recording_thread = threading.Thread(
            target=self.record_audio, daemon=True)
        self.recognizing_thread = threading.Thread(
            target=self.recognize_audio, daemon=True)
        self.recording_thread.start()
        self.recognizing_thread.start()
        # print("开始语音识别...")

    def stop(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.stop_event.set()
        # print("停止语音识别...")
        self.recording_thread.join()
        self.recognizing_thread.join()
        # print("语音识别线程已结束。")
        self.recording_thread = None
        self.recognizing_thread = None

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
        # print("开始录音...")
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


def load_audio_file(file_path):
    """
        加载音频文件,
        仅wav工作,可用的命令: 
        ffmpeg -i input_file -acodec pcm_s16le -ar 16000 -ac 1 output_file.wav

        -i input_file: 指定输入文件路径。
        -acodec pcm_s16le: 指定音频编码器为PCM 16位线性编码。
        -ar 16000: 指定采样率为16000 Hz。
        -ac 1: 指定声道数为1(单声道)。
        output_file.wav: 指定输出文件路径。
        注意：ffmpeg需要安装并且在系统路径中可用。例如，在Windows上，可以使用以下命令批量转换MP3到WAV格式：

        Get-ChildItem -Path . -Filter *.mp3 | ForEach-Object {
        $outputFile = $_.DirectoryName + "\" + $_.BaseName + ".wav"
        ffmpeg -i $_.FullName -acodec pcm_s16le -ar 16000 -ac 1 $outputFile}

    """
    try:
        # 使用pydub加载音频文件
        audio = AudioSegment.from_file(file_path)
        # 转换为WAV格式
        wav_data = audio.export(format="wav").read()
        return np.frombuffer(wav_data, dtype=np.int16)
    except Exception as e:
        raise ValueError(f"无法加载音频文件 {file_path}: {e}")


def transcribe_audio_file(file_path, model):
    """转录音频文件并保存结果到同名txt文件"""
    # 加载音频数据
    audio_data = load_audio_file(file_path)

    # 转录音频
    segments, info = model.transcribe(audio_data.astype(
        np.float16) / np.iinfo(np.int16).max, beam_size=5)
    recognized_text = " ".join(segment.text.strip() for segment in segments)

    # 保存转录结果到同名txt文件
    base_name = os.path.splitext(file_path)[0]
    txt_file_path = f"{base_name}.txt"
    with open(txt_file_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(recognized_text)
    print(f"转录完成,结果已保存到 {txt_file_path}")


def transcribe_audio_folder(folder_path, model):
    """批量转录音频文件夹中的所有音频文件"""
    supported_formats = ('.wav', '.mp3', '.ogg', '.flac',
                         '.aac', '.amr', '.m4a', '.wma')
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if os.path.isfile(file_path) and file_path.lower().endswith(supported_formats):
            transcribe_audio_file(file_path, model)


def main():
    while True:
        # 提示用户输入文件或文件夹路径
        input_path = input("请输入音频文件的路径或包含音频文件的文件夹路径: ").strip()

        # 指定模型路径
        model_path = "./model/faster-whisper-small"
        # 加载模型
        model = WhisperModel(model_path, device="cuda",
                             compute_type="float16", local_files_only=True)

        # 检查路径是否存在
        if not os.path.exists(input_path):
            print("指定的路径无效。")
            return

        # 检查路径是文件还是文件夹
        if os.path.isfile(input_path):
            # 如果是文件,处理单个文件
            try:
                transcribe_audio_file(input_path, model)
            except ValueError as e:
                print(e)
        elif os.path.isdir(input_path):
            # 如果是文件夹,批量处理文件夹中的所有音频文件
            transcribe_audio_folder(input_path, model)
        else:
            print("指定的路径无效。")


if __name__ == "__main__":
    main()
