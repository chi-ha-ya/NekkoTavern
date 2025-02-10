import pyaudio
import threading
import time
import sys
import queue
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO

CHUNK_SIZE = 1024
RATE = 32000


class AudioPlayer():
    def __init__(self, audio_queue: queue.Queue):
        self.audio_queue = audio_queue
        self.stop_event = threading.Event()  # Event to stop the thread
        self.lock = threading.Lock()  # Lock to synchronize audio playback

        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            output=True,
            start=False  # Do not start the stream immediately
        )

        # Start the audio playback thread
        self.play_audio_thread = threading.Thread(
            target=self.play_audio_process, daemon=True)
        self.play_audio_thread.start()

    def start(self):
        if not self.stream.is_active():
            self.stream.start_stream()  # Start the stream

        self.stop_event.clear()  # Clear the stop event

    def stop(self):
        self.stop_event.set()  # Set the stop event to stop playback
        self.stream.stop_stream()  # Stop the stream immediately
        self.audio_queue.queue.clear()  # Clear the audio queue

    def stream_audio(self, audio_segment):
        with self.lock:  # Ensure thread-safe audio playback
            try:
                # Convert AudioSegment to raw audio data
                raw_data = audio_segment.raw_data
                # Write raw audio data to the stream
                if not self.stop_event.is_set() and self.stream.is_active() and raw_data != b'':
                    self.stream.write(raw_data)
            except Exception as e:  # Catch potential exceptions during streaming
                print(f"Error during audio streaming: {e}", file=sys.stderr)

    def play_audio_process(self):
        last_segment = None
        cross_fade_duration = 50  # 50ms cross-fade duration
        last_segment_tail_length = 50  # 保留上一段音频结尾的50ms数据
        while True:
            if self.stop_event.is_set():
                # If stop_event is set, do not process the queue
                time.sleep(0.1)  # Sleep to reduce CPU usage
                continue

            if not self.audio_queue.empty():
                audio_clip = self.audio_queue.get()
                if audio_clip:
                    # 确保 audio_clip 是一个类文件对象
                    if isinstance(audio_clip, BytesIO):
                        audio_clip.seek(0)  # 确保从头开始读取
                    # Convert BytesIO to AudioSegment
                    audio_segment = AudioSegment.from_file(
                        audio_clip, format="wav")

                    # 如果存在上一个片段，则进行交叉淡入淡出
                    if last_segment:
                        # 只保留上一段音频结尾的50ms数据
                        last_segment_tail = last_segment[-last_segment_tail_length:]
                        combined_segment = last_segment_tail.append(
                            audio_segment, crossfade=cross_fade_duration)
                    else:
                        combined_segment = audio_segment

                    # 播放合并后的片段
                    self.stream_audio(combined_segment)

                    # 更新 last_segment 为当前片段
                    last_segment = audio_segment

                    # 清空已处理的音频片段，避免重复处理
                    audio_clip.close()
                # elif audio_clip is None:
                #     break  # 处理结束标志，退出循环

            # 在空闲时减少CPU占用
            time.sleep(0.1)  # 适当调整延时时间
        print("Audio playback has stopped.")

        # Reset last_segment to None when stopping playback
        self.last_segment = None

    def __del__(self):
        # Ensure the stream and PyAudio instance are properly closed when the object is destroyed
        if self.stream and self.stream.is_active():
            self.stream.stop_stream()
        if self.stream:
            self.stream.close()
        self.p.terminate()
