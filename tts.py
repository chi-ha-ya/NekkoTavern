import requests
import threading
import time
import queue
from io import BytesIO

gpt_sovits_tts_url = "http://127.0.0.1:9880/tts"


class GPT_Sovits_TTS:
    def __init__(self, character, audio_queue: queue.Queue):
        self.character = character
        self.audio_queue = audio_queue
        self.text_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.tts_thread = None

    def start(self):
        self.stop_event.clear()
        if self.tts_thread is not None:
            self.tts_thread.join()
        self.tts_thread = threading.Thread(
            target=self.tts_process, daemon=True)
        self.tts_thread.start()
        # print("TTS线程已启动。")

    def stop(self):
        self.stop_event.set()
        self.tts_thread.join()
        self.clear_text_queue()
        self.tts_thread = None
        # print("TTS进程已停止。")

    def clear_text_queue(self):
        self.text_queue.queue.clear()
        # print("文本队列已清空。")

    def add_text_to_queue(self, text):
        if self.stop_event.is_set():
            # print("TTS服务未启动，无法添加文本。")
            return
        # if not text:
        #     print("文本为空，无法添加。")
        #     return
        # if len(text) > 1024:
        #     print("文本过长，无法添加。")
        #     return
        self.text_queue.put(text)
        # print(f"已将文本添加到队列：{text}")

    def get_audio_from_api(self, text):
        params = {
            "text": text,
            "text_lang": "auto",
            "ref_audio_path": self.character["ref_audio_path"],
            "prompt_lang": self.character["prompt_lang"],
            "prompt_text": self.character["prompt_text"],
            "speed_factor": self.character["speed_factor"],
            "text_split_method": "cut5",
            "media_type": "wav",
            "parallel_infer": True,
            "streaming_mode": False
        }
        try:
            response = requests.get(
                gpt_sovits_tts_url, params=params, stream=False)
            if response.status_code == 200:
                # 将响应内容转换为 BytesIO 对象
                audio_data = BytesIO(response.content)
                self.audio_queue.put(audio_data)
            else:
                print(
                    f"Failed to get audio data. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"生成音频失败，TTS 引擎未启动？错误信息:\n {e}")

    def tts_process(self):
        while not self.stop_event.is_set():
            if not self.text_queue.empty():
                text = self.text_queue.get()
                if text:
                    self.get_audio_from_api(text)
                elif text is None:  # Check for None explicitly
                    break
            time.sleep(0.01)  # Reduce sleep time for responsiveness
        print("TTS 处理线程已停止")
