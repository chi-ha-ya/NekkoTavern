import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from stt import Faster_Whisper_STT
from stt import SPEECH_START
from stt import SPEECH_END
from tts import GPT_Sovits_TTS
from vox import AudioPlayer
import chat as chat
from PIL import Image
import queue
import json
import re
import time
import sys
import utils
import ollama as ollama
import mem as mem


Font_YaHei_11 = ("Microsoft YaHei", 11)
Font_YaHei_12 = ("Microsoft YaHei", 12)
Font_YaHei_14 = ("Microsoft YaHei", 14)
Font_YaHei_18 = ("Microsoft YaHei", 18)
Font_YaHei_20 = ("Microsoft YaHei", 20)


def ui_mainloop():
    root = ctk.CTk()
    config = utils.load_config()
    app = MainGUI(root, config)
    root.iconbitmap('logo.ico')
    root.mainloop()


class MainGUI:
    def __init__(self, root, config=None):
        self.root = root
        self.config = config
        self.character = {}
        self.extract_dialogue_for_tts = False
        self.auto_send_message = False
        self.query_memory_before_send_message = False

        # Configure window size
        self.root.geometry("800x480+1000+500")
        self.root.resizable(True, True)

        # ========== Main container uses TabView ==========
        self.tab_view = ctk.CTkTabview(self.root, width=800, height=480)
        self.tab_view.pack(fill="both", expand=True)

        # Create each Tab
        self.main_tab = self.tab_view.add("chat")
        self.character_tab = self.tab_view.add("chara")
        self.memory_tab = self.tab_view.add("mem")

        # Build the layout for each Tab
        self.build_main_tab()
        self.build_character_tab()
        self.build_memory_tab()

        # Load character file
        default_character_path = utils.get_absolute_path(
            self.config['character'], os.getcwd())
        self.load_character_card(default_character_path)

        # Set the initial directory to the "characters" folder under the current working directory
        self.initialdir_load = os.path.join(os.getcwd(), "characters")
        self.initialdir_save = os.path.join(os.getcwd(), "characters")

        # Initialize STT and audio player
        self.asr = Faster_Whisper_STT(
            self.input_text_queue, self.config["stt_model_path"])
        self.audio_player = AudioPlayer(self.audio_queue)

        # Initialize TTS (delayed until after character file is loaded)
        self.tts = GPT_Sovits_TTS(self.character, self.audio_queue)

        # Start the audio player
        self.audio_player.start()  # Start the audio player
        self.tts.start()  # Start TTS

        # Start a thread to listen for STT output
        self.stt_listener_thread = threading.Thread(
            target=self.listen_stt_output, daemon=True)
        self.stt_listener_thread.start()

    def log(self, info: str, title=""):
        """ Log information """
        self.log_text.configure(state="normal")  # Set to editable state
        self.log_text.insert(
            ctk.END, f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]    {title}:\n{info}\n")
        self.log_text.configure(state="disabled")  # Restore to read-only state
        # Automatically scroll to the bottom of the text box
        self.log_text.see(ctk.END)

    def build_main_tab(self):
        """ Build the main interface """
        # Use grid layout
        # Row for the history message text box
        self.main_tab.grid_rowconfigure(0, weight=1)
        # Row for the input message text box
        self.main_tab.grid_rowconfigure(1, weight=0)
        self.main_tab.grid_rowconfigure(2, weight=0)  # Row for the buttons
        self.main_tab.grid_columnconfigure(0, weight=1)  # Only column

        # History message text box
        self.history_text = ctk.CTkTextbox(
            self.main_tab, width=640, height=400)
        self.history_text.grid(row=0, column=0, padx=10,
                               pady=10, sticky="nsew")
        self.history_text.configure(font=Font_YaHei_18)

        # Input message text box
        self.input_text = ctk.CTkEntry(self.main_tab, width=640, height=100)
        self.input_text.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.input_text.configure(font=Font_YaHei_20)

        # Button container
        self.button_frame = ctk.CTkFrame(self.main_tab)
        self.button_frame.grid(row=2, column=0, padx=10, pady=10, sticky="se")

       # Memory switch
        self.memory_switch = ctk.CTkSwitch(
            self.button_frame, text="MEM",
            command=self.toggle_memory_query,
            width=36,
        )
        self.memory_switch.grid(row=0, column=0, padx=10, pady=10)
        self.memory_switch.deselect()  # Default is not recording

        # Add avatar display
        self.character_image_label = ctk.CTkLabel(
            self.button_frame, text="", image=None)
        self.character_image_label.grid(
            row=0, column=1, padx=0, pady=0)

        # Load configuration file button
        self.load_config_button = ctk.CTkButton(
            self.button_frame,
            text="Load Character Card",
            command=self.load_character_card,
            width=100,  # Set button width
            height=36,  # Set button height
            corner_radius=16,  # Set button corner radius
            fg_color="#4CAF50",  # Set button background color
            hover_color="#45a049",  # Set button hover color
            text_color="white",  # Set button text color
            font=Font_YaHei_12  # Set button font
        )
        self.load_config_button.grid(row=0, column=2, padx=10, pady=10)

        # Recording switch
        self.record_switch = ctk.CTkSwitch(
            self.button_frame, text="REC",
            command=self.toggle_recording,
            width=36,
        )
        self.record_switch.grid(row=0, column=3, padx=10, pady=10)
        self.record_switch.deselect()  # Default is not recording

        # Dialing switch
        self.dialing_switch = ctk.CTkSwitch(
            self.button_frame, text="Dial",
            command=self.toggle_dialing,
            width=36,
        )
        self.dialing_switch.grid(row=0, column=4, padx=10, pady=10)
        self.dialing_switch.deselect()  # Default is not recording

        # Send button
        self.send_button = ctk.CTkButton(
            self.button_frame, text="Send",
            command=self.send_message,
            width=120, height=40,)
        self.send_button.grid(row=0, column=5, padx=10, pady=10)
        # Bind shortcut keys
        # Enter key to send message
        self.input_text.bind("<Return>", self.send_message)
        self.root.bind(
            self.config["key_recording"], self.toggle_recording)  # Ctrl+R shortcut for recording
        self.root.bind(
            self.config["key_tts"], self.toggle_audio_playback)  # Ctrl+P shortcut for stopping audio playback

        self.input_text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

    def build_character_tab(self):
        self.character_tab.rowconfigure(0, weight=1)
        self.character_tab.columnconfigure(0, weight=1)
        self.character_tab.columnconfigure(1, weight=0)

        # Left Frame
        self.character_left_frame = ctk.CTkFrame(self.character_tab)
        self.character_left_frame.grid(
            row=0, column=0, sticky="nsew", padx=2, pady=2)

        # Right Frame
        self.character_right_frame = ctk.CTkFrame(self.character_tab)
        self.character_right_frame.grid(
            row=0, column=1, sticky="nsew", padx=2, pady=2)

        # Left layout
        self.build_character_left_layout()
        # Right layout
        self.build_character_right_layout()

    def build_character_left_layout(self):
        self.character_left_frame.grid_rowconfigure(0, weight=0)
        self.character_left_frame.grid_rowconfigure(1, weight=2)
        self.character_left_frame.grid_rowconfigure(2, weight=0)
        self.character_left_frame.grid_rowconfigure(3, weight=0)
        self.character_left_frame.grid_columnconfigure(0, weight=1)

        chapter_label = ctk.CTkLabel(
            self.character_left_frame,
            text="character description:",
            font=Font_YaHei_11
        )
        chapter_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

        # model file text box
        self.model_profile_text = ctk.CTkTextbox(
            self.character_left_frame, width=640, height=400)
        self.model_profile_text.grid(row=1, column=0, padx=10,
                                     pady=10, sticky="nsew")
        self.model_profile_text.configure(font=Font_YaHei_18)

        # ========== Output log label ==========
        log_label = ctk.CTkLabel(
            self.character_left_frame,
            text="log: ",
            font=Font_YaHei_11
        )
        log_label.grid(row=2, column=0, padx=5, pady=(5, 0), sticky="w")

        # ========== Log: Read-only ==========
        self.log_text = ctk.CTkTextbox(
            self.character_left_frame,
            wrap="word",
            font=Font_YaHei_12
        )
        self.log_text.grid(row=3, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.log_text.configure(state="disabled")

    def build_character_right_layout(self):
        """
            # 参考：https://www.llamafactory.cn/ollama-docs/modelfile.html#%E6%9C%89%E6%95%88%E7%9A%84%E5%8F%82%E6%95%B0%E5%92%8C%E5%80%BC
            mirostat	   启用 mirostat 采样控制 perplexity。(default: 0, 0 = disabled, 1 = Mirostat, 2 = Mirostat 2.0)
            mirostat_eta   影响算法对生成文本的反馈响应速度。较低的学习率将导致反应更慢，而较高的学习率响应更快。(Default: 0.1)
            mirostat_tau   控制输出的连贯性和多样性之间的平衡。较低的值将导致更集中和连贯的文本。(Default: 5.0)
            num_ctx        设置生成下一个token时使用的上下文窗口大小。(Default: 2048)
            repeat_last_n  设置模型回溯多少个token以防止重复。(Default: 64, 0 = 禁用, -1 = num_ctx)
            repeat_penalty 设置对重复的惩罚程度。较高的值(例如,1.5)将更强烈地惩罚重复,而较低的值(例如,0.9)则会更加宽容。(Default: 1.1)
            temperature    模型的温度。增加温度会使模型的回答更具创造性。(Default: 0.7)
            seed           设置用于生成的随机数种子。设置为特定数字如42,将使模型在相同的提示下生成相同的文本。(Default: 0)
            stop           设置要使用的停止序列。当遇到此模式时,LLM 将停止生成文本并返回。可以在模型文件中通过指定多个单独的 stop 参数来设置多个停止序列。(Default:"AI assistant:")
            tfs_z          尾部自由采样减少小概率标记对输出的影响。较高的值(例如,2.0)影响减少更多,而值为 1.0 则禁用此设置。(Default: 1)
            num_predict    预测生成文本时的最大标记数。(Default: 128, -1 = 无限生成, -2 = 填充上下文)
            top_k          减少生成无意义内容的概率。较高的值(例如. 100)将提供更多样化的答案,而较低的值(例如. 10)则会更加保守。(Default: 40)
            top_p          与 top-k 结合使用。较高的值(例如, 0.95)将导致更多样化的文本,而较低的值(例如, 0.5)将生成更集中和保守的文本。(Default: 0.9)
            min_p          作为 top_p 的替代品,旨在确保质量和多样性的平衡。参数 p 表示token入选的最小概率,且与token本身概率有关,例如,p=0.05 和最可能标记的概率为 0.9 时,值小于 0.045 的token将被过滤掉。(Default: 0.0)
        """
        # Initialize variables
        self.character_name_var = ctk.StringVar(value="")
        self.ref_audio_var = ctk.StringVar(value="")
        self.ref_prompt_text_var = ctk.StringVar(value="")
        self.ref_audio_lang_var = ctk.StringVar(value="ja")
        self.speed_factor_var = ctk.StringVar(value="1.0")

        self.model_from_var = ctk.StringVar(value="qwen2.5:7b")
        self.model_template_var = ctk.StringVar(value="")
        self.model_message_var = ctk.StringVar(value="")
        self.additional_PARAMETER_var = ctk.StringVar(value="")

        self.parameters_mirostat_var = ctk.StringVar(value="0.0")
        self.parameters_mirostat_eta_var = ctk.StringVar(value="0.1")
        self.parameters_mirostat_tau_var = ctk.StringVar(value="5.0")
        self.parameters_num_ctx_var = ctk.StringVar(value="2048")
        self.parameters_repeat_last_n_var = ctk.StringVar(value="128")
        self.parameters_repeat_penalty_var = ctk.StringVar(value="1.5")
        self.parameters_temperature_var = ctk.DoubleVar(value=0.95)
        self.parameters_seed_var = ctk.StringVar(value="0")
        self.parameters_stop_var = ctk.StringVar(value="AI assistant:")
        self.parameters_tfs_z_var = ctk.StringVar(value="2.0")
        self.parameters_num_predict_var = ctk.StringVar(value="256")
        self.parameters_top_k_var = ctk.StringVar(value="40")
        self.parameters_top_p_var = ctk.StringVar(value="0.95")
        self.parameters_min_p_var = ctk.StringVar(value="0.05")

        self.character_name_var.trace_add("write", self.character_name_update)
        self.ref_audio_lang_var.trace_add("write", self.select_audio_lang)
        self.speed_factor_var.trace_add("write", self.speed_factor_update)

        # Set layout weights
        self.character_right_frame.rowconfigure(0, weight=1)
        self.character_right_frame.rowconfigure(1, weight=0)
        self.character_right_frame.columnconfigure(0, weight=1)
        self.character_info_frame = ctk.CTkFrame(self.character_right_frame)
        self.character_info_frame.grid(
            row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.character_info_frame.grid_rowconfigure(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21), weight=0)
        self.character_info_frame.grid_columnconfigure(0, weight=0)
        self.character_info_frame.grid_columnconfigure(1, weight=1)
        self.character_info_frame.grid_columnconfigure(2, weight=0)

        # Name
        name_label = ctk.CTkLabel(
            self.character_info_frame,
            text="Name:",
            font=Font_YaHei_12
        )
        name_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        character_name_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.character_name_var,
            font=Font_YaHei_12
        )
        character_name_entry.grid(
            row=0, column=1, padx=5, pady=5, sticky="nsew")

        # Reference Audio
        ref_audio_label = ctk.CTkLabel(
            self.character_info_frame,
            text="Reference Audio Path:",
            font=Font_YaHei_12
        )
        ref_audio_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ref_audio_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.ref_audio_var,
            font=Font_YaHei_12
        )
        ref_audio_entry.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        # Button to select audio file
        select_audio_button = ctk.CTkButton(
            self.character_info_frame,
            text="choose",
            command=self.select_audio_file,
            width=40,
            font=Font_YaHei_12
        )
        select_audio_button.grid(row=1, column=2, padx=5, pady=5, sticky="ew")

        # Reference Audio Language
        ref_audio_lang_label = ctk.CTkLabel(
            self.character_info_frame,
            text="Reference Audio Language:",
            font=Font_YaHei_12
        )
        ref_audio_lang_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")
        ref_audio_lang_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.ref_audio_lang_var,
            font=Font_YaHei_12
        )
        ref_audio_lang_entry.grid(
            row=2, column=1, padx=5, pady=5, sticky="nsew")

        # Speed Factor
        speed_factor_label = ctk.CTkLabel(
            self.character_info_frame,
            text="speaking speed:",
            font=Font_YaHei_12
        )
        speed_factor_label.grid(row=3, column=0, padx=5, pady=5, sticky="e")
        speed_factor_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.speed_factor_var,
            font=Font_YaHei_12
        )
        speed_factor_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

        # From
        from_label = ctk.CTkLabel(
            self.character_info_frame,
            text="From Model:",
            font=Font_YaHei_12
        )
        from_label.grid(row=4, column=0, padx=5, pady=5, sticky="e")
        from_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.model_from_var,
            font=Font_YaHei_12
        )
        from_entry.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")
        # Button to list ollama models
        list_models_button = ctk.CTkButton(
            self.character_info_frame,
            text="list",
            command=self.list_installed_models,
            width=40,
            font=Font_YaHei_12
        )
        list_models_button.grid(row=4, column=2, padx=5, pady=5, sticky="ew")

        # Temperature
        temperature_label = ctk.CTkLabel(
            self.character_info_frame,
            text="temperature:",
            font=Font_YaHei_12
        )
        temperature_label.grid(row=5, column=0, padx=5, pady=5, sticky="e")
        temperature_slider = ctk.CTkSlider(
            self.character_info_frame,
            from_=0.0, to=2.0,
            number_of_steps=200,
            variable=self.parameters_temperature_var,
            command=self.update_temperature_label
        )
        temperature_slider.grid(row=5, column=1, padx=5, pady=5, sticky="we")

        # Temperature value label
        self.temperature_value_label = ctk.CTkLabel(
            self.character_info_frame,
            text=f"{self.parameters_temperature_var.get():.2f}",
            font=Font_YaHei_12
        )
        self.temperature_value_label.grid(
            row=5, column=2, padx=1, pady=1, sticky="w")

        # Num Predict
        # num_predict_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="num_predict:",
        #     font=Font_YaHei_12
        # )
        # num_predict_label.grid(row=6, column=0, padx=5, pady=5, sticky="e")
        # num_predict_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_num_predict_var,
        #     font=Font_YaHei_12
        # )
        # num_predict_entry.grid(row=6, column=1, padx=5, pady=5, sticky="nsew")

        # Repeat Penalty
        repeat_penalty_label = ctk.CTkLabel(
            self.character_info_frame,
            text="repeat_penalty:",
            font=Font_YaHei_12
        )
        repeat_penalty_label.grid(row=7, column=0, padx=5, pady=5, sticky="e")
        repeat_penalty_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.parameters_repeat_penalty_var,
            font=Font_YaHei_12
        )
        repeat_penalty_entry.grid(
            row=7, column=1, padx=5, pady=5, sticky="nsew")

        # Top K
        top_k_label = ctk.CTkLabel(
            self.character_info_frame,
            text="top_k:",
            font=Font_YaHei_12
        )
        top_k_label.grid(row=8, column=0, padx=5, pady=5, sticky="e")
        top_k_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.parameters_top_k_var,
            font=Font_YaHei_12
        )
        top_k_entry.grid(row=8, column=1, padx=5, pady=5, sticky="nsew")

        # Top P
        # top_p_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="top_p:",
        #     font=Font_YaHei_12
        # )
        # top_p_label.grid(row=9, column=0, padx=5, pady=5, sticky="e")
        # top_p_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_top_p_var,
        #     font=Font_YaHei_12
        # )
        # top_p_entry.grid(row=9, column=1, padx=5, pady=5, sticky="nsew")

        # Mirostat
        # mirostat_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="mirostat:",
        #     font=Font_YaHei_12
        # )
        # mirostat_label.grid(row=10, column=0, padx=5, pady=5, sticky="e")
        # mirostat_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_mirostat_var,
        #     font=Font_YaHei_12
        # )
        # mirostat_entry.grid(row=10, column=1, padx=5, pady=5, sticky="nsew")

        # Mirostat Eta
        # mirostat_eta_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="mirostat_eta:",
        #     font=Font_YaHei_12
        # )
        # mirostat_eta_label.grid(row=11, column=0, padx=5, pady=5, sticky="e")
        # mirostat_eta_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_mirostat_eta_var,
        #     font=Font_YaHei_12
        # )
        # mirostat_eta_entry.grid(
        #     row=11, column=1, padx=5, pady=5, sticky="nsew")

        # Mirostat Tau
        # mirostat_tau_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="mirostat_tau:",
        #     font=Font_YaHei_12
        # )
        # mirostat_tau_label.grid(row=12, column=0, padx=5, pady=5, sticky="e")
        # mirostat_tau_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_mirostat_tau_var,
        #     font=Font_YaHei_12
        # )
        # mirostat_tau_entry.grid(
        #     row=12, column=1, padx=5, pady=5, sticky="nsew")

        # Num Context
        num_ctx_label = ctk.CTkLabel(
            self.character_info_frame,
            text="num_ctx:",
            font=Font_YaHei_12
        )
        num_ctx_label.grid(row=13, column=0, padx=5, pady=5, sticky="e")
        num_ctx_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.parameters_num_ctx_var,
            font=Font_YaHei_12
        )
        num_ctx_entry.grid(row=13, column=1, padx=5, pady=5, sticky="nsew")

        # Repeat Last N
        # repeat_last_n_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="repeat_last_n:",
        #     font=Font_YaHei_12
        # )
        # repeat_last_n_label.grid(row=14, column=0, padx=5, pady=5, sticky="e")
        # repeat_last_n_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_repeat_last_n_var,
        #     font=Font_YaHei_12
        # )
        # repeat_last_n_entry.grid(
        #     row=14, column=1, padx=5, pady=5, sticky="nsew")

        # Seed
        # seed_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="seed:",
        #     font=Font_YaHei_12
        # )
        # seed_label.grid(row=15, column=0, padx=5, pady=5, sticky="e")
        # seed_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_seed_var,
        #     font=Font_YaHei_12
        # )
        # seed_entry.grid(row=15, column=1, padx=5, pady=5, sticky="nsew")

        # Stop
        # stop_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="stop:",
        #     font=Font_YaHei_12
        # )
        # stop_label.grid(row=16, column=0, padx=5, pady=5, sticky="e")
        # stop_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_stop_var,
        #     font=Font_YaHei_12
        # )
        # stop_entry.grid(row=16, column=1, padx=5, pady=5, sticky="nsew")

        # TFS Z
        # tfs_z_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="tfs_z:",
        #     font=Font_YaHei_12
        # )
        # tfs_z_label.grid(row=17, column=0, padx=5, pady=5, sticky="e")
        # tfs_z_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_tfs_z_var,
        #     font=Font_YaHei_12
        # )
        # tfs_z_entry.grid(row=17, column=1, padx=5, pady=5, sticky="nsew")

        # Min P
        # min_p_label = ctk.CTkLabel(
        #     self.character_info_frame,
        #     text="min_p:",
        #     font=Font_YaHei_12
        # )
        # min_p_label.grid(row=18, column=0, padx=5, pady=5, sticky="e")
        # min_p_entry = ctk.CTkEntry(
        #     self.character_info_frame,
        #     textvariable=self.parameters_min_p_var,
        #     font=Font_YaHei_12
        # )
        # min_p_entry.grid(row=18, column=1, padx=5, pady=5, sticky="nsew")

        # Additional Parameters
        additional_PARAMETER_label = ctk.CTkLabel(
            self.character_info_frame,
            text="Additional PARAMETER (optional):",
            font=Font_YaHei_12
        )
        additional_PARAMETER_label.grid(
            row=19, column=0, padx=5, pady=5, sticky="e")
        additional_PARAMETER_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.additional_PARAMETER_var,
            font=Font_YaHei_12
        )
        additional_PARAMETER_entry.grid(
            row=19, column=1, padx=5, pady=5, sticky="nsew")

        # Template
        template_label = ctk.CTkLabel(
            self.character_info_frame,
            text="template (optional):",
            font=Font_YaHei_12
        )
        template_label.grid(row=20, column=0, padx=5, pady=5, sticky="e")
        template_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.model_template_var,
            font=Font_YaHei_12
        )
        template_entry.grid(row=20, column=1, padx=5, pady=5, sticky="nsew")

        # MESSAGE
        MESSAGE_label = ctk.CTkLabel(
            self.character_info_frame,
            text="MESSAGE (optional):",
            font=Font_YaHei_12
        )
        MESSAGE_label.grid(row=21, column=0, padx=5, pady=5, sticky="e")
        MESSAGE_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.model_message_var,
            font=Font_YaHei_12
        )
        MESSAGE_entry.grid(row=21, column=1, padx=5, pady=5, sticky="nsew")

        """
        Buttons
        """
        self.character_buttons_frame = ctk.CTkFrame(self.character_right_frame)
        self.character_buttons_frame.grid(
            row=1, column=0, sticky="se", padx=5, pady=5)
        self.character_buttons_frame.columnconfigure((0, 1, 2), weight=1)

        self.btn_generate_setting = ctk.CTkButton(
            self.character_buttons_frame,
            text="load",
            command=self.load_character_file,
            font=Font_YaHei_12
        )
        self.btn_generate_setting.grid(
            row=0, column=0, padx=5, pady=2, sticky="ew")

        self.btn_generate_directory = ctk.CTkButton(
            self.character_buttons_frame,
            text="save",
            command=self.save_character_file,
            font=Font_YaHei_12
        )
        self.btn_generate_directory.grid(
            row=0, column=1, padx=5, pady=2, sticky="ew")

        self.btn_generate_chapter = ctk.CTkButton(
            self.character_buttons_frame,
            text="build",
            command=self.build_model,
            font=Font_YaHei_12
        )
        self.btn_generate_chapter.grid(
            row=0, column=2, padx=5, pady=2, sticky="ew")

    def build_memory_tab(self):
        # Top frame
        self.top_frame = ctk.CTkFrame(self.memory_tab)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.top_frame.columnconfigure(
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), weight=1)

        # Load button in top_frame
        self.load_history_button = ctk.CTkButton(
            self.top_frame, text="Import Chat History", command=self.load_history_text, font=Font_YaHei_12
        )
        self.load_history_button.grid(
            row=0, column=0, padx=5, pady=5, sticky="ew")

        # Load button in top_frame
        self.load_button = ctk.CTkButton(
            self.top_frame, text="Load Text File", command=self.load_text_file, font=Font_YaHei_12
        )
        self.load_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Summary button in top_frame

        self.summary_button = ctk.CTkButton(
            self.top_frame, text="Summary", command=self.summary_memo, font=Font_YaHei_12
        )
        self.summary_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Save button in top_frame
        self.import_vector_store_button = ctk.CTkButton(
            self.top_frame, text="Save To Memory", command=self.save_to_vector_store, font=Font_YaHei_12
        )
        self.import_vector_store_button.grid(
            row=0, column=9, padx=5, pady=5, sticky="ew")

        # Middle frame
        self.middle_frame = ctk.CTkFrame(self.memory_tab)
        self.middle_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.memory_tab.grid_rowconfigure(1, weight=1)
        self.memory_tab.grid_columnconfigure(0, weight=1)
        self.middle_frame.grid_rowconfigure(0, weight=1)
        self.middle_frame.grid_columnconfigure(0, weight=1)

        # Textbox in middle_frame
        self.memo_text = ctk.CTkTextbox(
            self.middle_frame, wrap="word", font=Font_YaHei_14)
        self.memo_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Bottom frame
        self.bottom_frame = ctk.CTkFrame(self.memory_tab)
        self.bottom_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.bottom_frame.columnconfigure(0, weight=1)  # 所有列都自动扩展
        self.bottom_frame.columnconfigure(1, weight=0)  # 按钮所在的列不扩展

        # Query input box and Query button in bottom_frame
        self.query_message_box = ctk.CTkEntry(
            self.bottom_frame, placeholder_text="Select or enter your query here", font=Font_YaHei_12
        )
        self.query_message_box.grid(
            row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.query_message_box.bind(
            "<Return>", self.perform_query)  # 绑定 Enter 键到查询功能

        self.query_memo_button = ctk.CTkButton(
            self.bottom_frame, text="Query", command=self.perform_query, font=Font_YaHei_12
        )
        self.query_memo_button.grid(
            row=0, column=1, padx=5, pady=5, sticky="e")

        # Delete input box and Delete button in bottom_frame
        self.delete_message_box = ctk.CTkEntry(
            self.bottom_frame, placeholder_text="Select or enter document ID to delete. Leave empty to delete all displayed documents", font=Font_YaHei_12
        )
        self.delete_message_box.grid(
            row=1, column=0, padx=5, pady=5, sticky="nsew")
        self.delete_message_box.bind(
            "<Return>", self.perform_delete)  # 绑定 Enter 键到删除功能

        self.delete_memo_button = ctk.CTkButton(
            self.bottom_frame, text="Delete", command=self.perform_delete, font=Font_YaHei_12,
        )
        self.delete_memo_button.grid(
            row=1, column=1, padx=5, pady=5, sticky="e")

    def load_history_text(self):
        history = self.history_text.get("1.0", ctk.END).strip()
        if history:
            self.memo_text.delete("1.0", ctk.END)
            self.memo_text.insert(ctk.END, history)

    # Methods for load, save, and query

    def load_text_file(self):
        file_path = filedialog.askopenfilename(
            title="Load Text File",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt;*.json;*.md")
            ],
            initialdir=self.initialdir_load
        )
        if file_path:
            try:
                data = utils.load_settings_from_file(file_path)
                content = data
                self.memo_text.delete("1.0", ctk.END)
                self.memo_text.insert(ctk.END, content)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")

    def summary_memo(self):
        # 检查是否有选中的文本
        try:
            start_pos = self.memo_text.index("sel.first")  # 获取选中文本的起始位置
            end_pos = self.memo_text.index("sel.last")     # 获取选中文本的结束位置
            content = self.memo_text.get(
                start_pos, end_pos).strip()  # 获取选中的内容
        except Exception as e:
            # 如果没有选中的文本，则获取整个文本框的内容
            start_pos = "1.0"  # 设置起始位置为文本框的开头
            end_pos = ctk.END  # 设置结束位置为文本框的结尾
            content = self.memo_text.get(
                start_pos, end_pos).strip()  # 获取整个文本框的内容

        if not content:
            return

        # Generate summary using the model specified in character settings
        prompt = chat.generate_summary_prompt(content)
        response = chat.generate_completion(
            prompt, model=self.character['name'], stream=False)
        if response.status_code == 200:
            summary = f"\n{response.json()['response']}"

            # 插入新文本到原来选中内容的位置
            self.memo_text.delete(start_pos, end_pos)
            self.memo_text.insert(start_pos, summary)
            # 设置插入的内容为选中状态
            end_pos = self.memo_text.index(
                f"{start_pos} + {len(summary)} chars")
            self.memo_text.tag_add("sel", start_pos, end_pos)
            self.memo_text.see(start_pos)  # 确保选中内容在可视范围内
        else:
            print("Error generating summary:", response.status_code)

    def save_to_vector_store(self):
        text = self.memo_text.get("1.0", ctk.END).strip()
        if not text:
            return
        if self.memo_path:
            mem.insert_text_to_vector_store(
                self.memo_path, text, self.mem_vector_store)
            print(f"Document saved to vector store: {self.memo_path}", "Save")
        else:
            messagebox.showwarning(
                "Warning", "No document selected for saving.")

    def perform_delete(self, event=None):
        # 检查是否有选中的文本
        delete_id = ""
        try:
            start_pos = self.memo_text.index("sel.first")  # 获取选中文本的起始位置
            end_pos = self.memo_text.index("sel.last")     # 获取选中文本的结束位置
            delete_id = self.memo_text.get(
                start_pos, end_pos).strip()  # 获取选中的内容
        except Exception as e:
            # 如果没有选中的文本，则获取delete_message_box框的内容
            delete_id = self.delete_message_box.get().strip()

        delete_ids = []
        if delete_id == "":
            if self.query_result:
                delete_ids = [f"{doc.id}" for doc, _ in self.query_result]
            else:
                return
        else:
            delete_ids = [delete_id]

        answer = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete the document with ID: '{delete_ids}'?"
        )

        if answer:
            mem.delete_document_from_vector_store(
                self.memo_path, delete_ids, self.mem_vector_store)
            # 取消选中的文本状态
            self.memo_text.tag_remove("sel", "1.0", ctk.END)
            messagebox.showinfo("Deletion Successful",
                                "Document deleted successfully.")
        else:
            messagebox.showinfo("Deletion Cancelled",
                                "Deletion cancelled by user.")

    def perform_query(self, event=None, query=None):
      # 检查是否有选中的文本
        if query == None:
            try:
                start_pos = self.memo_text.index("sel.first")  # 获取选中文本的起始位置
                end_pos = self.memo_text.index("sel.last")     # 获取选中文本的结束位置
                query = self.memo_text.get(
                    start_pos, end_pos).strip()  # 获取选中的内容
            except Exception as e:
                # 如果没有选中的文本，则获取query_message_box框的内容
                query = self.query_message_box.get().strip()

        if query:
            # 如果选中的文本不为空，则将其插入到query_message_box框中
            self.query_message_box.delete(0, ctk.END)
            self.query_message_box.insert(0, query)
            self.query_result = mem.get_relevant_context_from_vector_store(
                store_path=self.memo_path, query=query, chroma=self.mem_vector_store)

            # 清空 memo_text
            self.memo_text.delete("1.0", ctk.END)

            # 格式化查询结果并插入到 memo_text
            if self.query_result:
                result_text = "\n".join(
                    [f"\nID: {doc.id} similarity: {similarity:.4f}\n{doc.page_content}\n" for doc, similarity in self.query_result])
                self.memo_text.insert(ctk.END, result_text)
            else:
                self.memo_text.insert(ctk.END, "No relevant documents found.")
        else:
            pass

    def select_audio_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio files", "*.wav;*.mp3;*.flac")],
            initialdir=self.initialdir_load
        )
        if file_path and os.path.exists(file_path):
            self.ref_audio_var.set(file_path)
            self.character["ref_audio_path"] = file_path
            self.character["prompt_text"] = os.path.basename(
                file_path).split('.')[0]  # Use the filename as prompt_text

    def select_audio_lang(self, *args):
        selected_language = self.ref_audio_lang_var.get()
        self.character["prompt_lang"] = selected_language

    def speed_factor_update(self, *args):
        selected_speed_factor = self.speed_factor_var.get()
        self.character["speed_factor"] = f"{float(selected_speed_factor):.2f}"

    def character_name_update(self, *args):
        selected_name = self.character_name_var.get()
        self.character["name"] = selected_name

    def select_image_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image files", "*.png")],
            initialdir=self.initialdir_load
        )
        if file_path:
            self.ref_image_var.set(file_path)

    def update_temperature_label(self, value):
        self.temperature_value_label.configure(text=f"{float(value):.2f}")

    def load_character_card(self, file_path=None):
        if not file_path:
            # Open file selector to choose model file
            file_path = filedialog.askopenfilename(
                title="Select Character Card",
                filetypes=[("character Card", "*.png;*.json")],
                initialdir=self.initialdir_load
            )
        if os.path.exists(file_path):
            try:
                data = utils.load_settings_from_file(file_path)
                self.update_ui_with_data(data, file_path)
                character_exists = self.check_model_exists(data["name"])
                base_model_exists = self.check_model_exists(data["from_model"])
                build_success = False

                if not character_exists:
                    if not base_model_exists:
                        messagebox.showerror(
                            "Error", f"{data['from_model']} Not Found, Import Failed!\nSee logs for more details.")
                        self.log(
                            f"Create character {data['name']} from {file_path} Failed,\nBase model {data['from_model']} not found,You may need to  install it by following instructions:\n ollama run {data['from_model']}")
                        return
                    else:
                        build_success = self.build_model()
                if build_success or (character_exists and base_model_exists):
                    character_path = utils.get_relative_path(file_path)
                    if self.config["character"] != character_path:
                        self.config["character"] = character_path
                        utils.save_config(self.config)
                    self.log(
                        f"Character {data['name']} loaded from {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Not a valid character card!")
                print(f"Error loading character card from {file_path}: {e}")

    def load_character_file(self, file_path=None):
        if not file_path:
            # Open file selector to choose model file
            file_path = filedialog.askopenfilename(
                title="Select Character",
                filetypes=[("character file", "*.json;*.png")],
                initialdir=self.initialdir_load
            )
        if os.path.exists(file_path):
            try:
                data = utils.load_settings_from_file(file_path)
                if data:
                    self.update_ui_with_data(data, file_path)
                    self.log(f"Character profile loaded from {file_path}")
                    return True
            except Exception as e:
                self.log(f"Error loading character profile: {e}")
                print(f"Error loading data: {data}")
                return False
        else:
            return False

    def save_character_file(self):
        # Open file save dialog to let user choose save path and filename
        file_path = filedialog.asksaveasfilename(
            title="Save Character",
            filetypes=[
                ("All files", "*.*"),
                ("JSON files", "*.json"),
            ],
            initialdir=self.initialdir_save,
            # Default filename
            initialfile=f"{self.character_name_var.get()}.json"
        )
        if not file_path:
            print("Save cancelled.")
            return

        # Retrieve current interface parameters
        try:
            parameters = self.get_model_parameters()
        except Exception as e:
            self.log(f"Error getting additional parameters: {e}")
            return

        character_data = {
            "name": self.character_name_var.get(),
            "ref_audio": self.ref_audio_var.get(),
            "ref_audio_lang": self.ref_audio_lang_var.get(),
            "speed_factor": self.speed_factor_var.get(),
            "from_model": self.model_from_var.get(),
            "parameters": parameters,
            "template": self.model_template_var.get(),
            "message": self.model_message_var.get(),
            "description": self.model_profile_text.get("1.0", ctk.END)
        }
        try:
            utils.save_character_settings(character_data, file_path)
            character_path = utils.get_relative_path(file_path)
            if self.config["character"] != character_path:
                self.config["character"] = character_path
                utils.save_config(self.config)
                self.root.title(f"{file_path}")
            self.log(
                f"Character profile was successfully saved to {file_path}")
        except Exception as e:
            messagebox.showerror(
                "Save failed", f"Saving character configuration encountered an error: {e}")

    def get_model_parameters(self):
        parameters = {
            # "mirostat": float(self.parameters_mirostat_var.get()),
            # "mirostat_eta": float(self.parameters_mirostat_eta_var.get()),
            # "mirostat_tau": float(self.parameters_mirostat_tau_var.get()),
            "num_ctx": int(self.parameters_num_ctx_var.get()),
            # "repeat_last_n": int(self.parameters_repeat_last_n_var.get()),
            "repeat_penalty": float(self.parameters_repeat_penalty_var.get()),
            "temperature": float(self.parameters_temperature_var.get()),
            # "seed": int(self.parameters_seed_var.get()),
            # "stop": self.parameters_stop_var.get(),
            # "tfs_z": float(self.parameters_tfs_z_var.get()),
            # "num_predict": int(self.parameters_num_predict_var.get()),
            "top_k": int(self.parameters_top_k_var.get()),
            # "top_p": float(self.parameters_top_p_var.get()),
            # "min_p": float(self.parameters_min_p_var.get())
        }
        self.combine_additional_parameters(parameters)
        return parameters

    def set_ui_parameters(self, parameters):
        self.parameters_mirostat_var.set(str(parameters.get("mirostat", 0.0)))
        self.parameters_mirostat_eta_var.set(
            str(parameters.get("mirostat_eta", 0.1)))
        self.parameters_mirostat_tau_var.set(
            str(parameters.get("mirostat_tau", 5.0)))
        self.parameters_num_ctx_var.set(str(parameters.get("num_ctx", 2048)))
        self.parameters_repeat_last_n_var.set(
            str(parameters.get("repeat_last_n", 128)))
        self.parameters_repeat_penalty_var.set(
            str(parameters.get("repeat_penalty", 1.1)))
        self.parameters_temperature_var.set(
            float(parameters.get("temperature", 0.7)))
        self.parameters_seed_var.set(str(parameters.get("seed", 0)))
        # self.parameters_stop_var.set(parameters.get("stop", ""))
        self.parameters_tfs_z_var.set(str(parameters.get("tfs_z", 1.0)))
        self.parameters_num_predict_var.set(
            str(parameters.get("num_predict", 128)))
        self.parameters_top_k_var.set(str(parameters.get("top_k", 40)))
        self.parameters_top_p_var.set(str(parameters.get("top_p", 0.95)))
        self.parameters_min_p_var.set(str(parameters.get("min_p", 0.00)))

        # 提取剩余的参数
        remaining_parameters = {k: v for k, v in parameters.items() if k not in [
            "mirostat", "mirostat_eta", "mirostat_tau", "num_ctx", "repeat_last_n", "repeat_penalty", "temperature", "seed", "stop", "tfs_z", "num_predict", "top_k", "top_p", "min_p"
        ]}

        # 将剩余参数存储到 additional_PARAMETER_var 中
        self.additional_PARAMETER_var.set(json.dumps(
            remaining_parameters, ensure_ascii=False, indent=0))

        # Update display value
        self.temperature_value_label.configure(
            text=f"{self.parameters_temperature_var.get():.2f}")

    def combine_additional_parameters(self, parameters):
        # Get additional parameters
        add_parameters = self.additional_PARAMETER_var.get()
        if add_parameters.strip():  # Check if there are additional parameters
            additional_params = json.loads(add_parameters)
            # Ensure returned value is a dictionary
            if isinstance(additional_params, dict):
                parameters.update(additional_params)
            else:
                raise ValueError(
                    "Additional parameters must be a dictionary")

    def check_model_exists(self, model_name):
        try:
            # Check if same named model exists
            models_response = ollama.list()  # Get installed model list
            models = models_response.models  # Get model list

            return any(
                model.model == model_name or
                model.model == f"{model_name}:latest"
                for model in models)
        except Exception as e:
            messagebox.showerror(
                "Error", f"Error checking model existence: {e}"
            )
            return False

    def build_model(self):
        # Model building logic
        try:
            parameters = self.get_model_parameters()
        except ValueError as e:
            messagebox.showerror("Build failed", str(e))
            return False

        try:
            from_model = self.model_from_var.get().strip()
            if from_model:  # Check if there is a source model
                from_model_exists = self.check_model_exists(from_model)
                if not from_model_exists:
                    messagebox.showerror(
                        "Build failed", f"Base model '{from_model}' not found. Please check installation:\n ollama run {from_model}")
                    return False

                # Check for existing same named model
            model_name = self.character_name_var.get()
            existing_model = self.check_model_exists(model_name)

            if existing_model:
                # Show dialog to ask whether to overwrite
                response = messagebox.askyesno(
                    "Model already exists", f"Model '{model_name}' already exists. Do you want to replace it?")
                if not response:
                    self.log(
                        f"User cancelled building of model '{model_name}", "Build cancelled")
                    return False

            self.log(
                f"Creating ollama model '{model_name}' ... ", "Starting build...")

            # Build the model
            progress_response = ollama.create(
                model=model_name,
                from_=self.model_from_var.get(),
                parameters=parameters,
                template=self.model_template_var.get(),
                # messages=self.model_message_var.get(), #格式有误，先屏蔽掉
                system=self.model_profile_text.get("1.0", ctk.END),
            )
            self.log(f"Model '{model_name}' created successfully", "done")
            return True

        except Exception as e:
            messagebox.showerror(
                "Build failed", f"An error occurred while building the model: {e}")
            return False,

    def list_installed_models(self):
        try:
            models_response = ollama.list()  # Get installed model list
            models = models_response.models  # Get model list

            # Format model information as string
            models_str = "\n".join(
                [
                    f"Model: {model.model}:\n "
                    f"Modified: {model.modified_at.isoformat() if model.modified_at else 'N/A'}, "
                    f"Digest: {model.digest if model.digest else 'N/A'}, "
                    f"Size: {model.size if model.size else 'N/A'}, "
                    f"Details: {model.details if model.details else 'N/A'}"
                    for model in models
                ]
            )
            models_str_log = "\n".join(
                [
                    f"{model.model}  "
                    f"{model.details.parameter_size if model.details else 'N/A'}  "
                    f"{model.details.family if model.details else 'N/A'}"
                    for model in reversed(models)
                ])  # Simplified model name list

            print(f"Installed models list:\n{models_str}")  # Print to console
            # Output formatted string to log
            self.log(models_str_log, "Installed models list")
        except Exception as e:
            messagebox.showerror("List models failed",
                                 f"Failed to list installed models: {e}")

    def update_ui_with_data(self, data, path: str):
        if not data:
            return
        profile = data["description"]
        if profile:
            self.model_profile_text.delete('1.0', ctk.END)
            self.model_profile_text.insert(ctk.END, profile)
        self.ref_audio_var.set(utils.get_absolute_path(
            data["ref_audio"], os.path.dirname(path)))
        self.root.title(f"{path}")
        self.load_config_button.configure(text=f"{data['name']}")

        if path.lower().endswith(".png"):
            # Update character image display
            img_file = Image.open(path)
            if img_file:
                character_image = ctk.CTkImage(
                    light_image=img_file,
                    dark_image=img_file,
                    size=(36, 36)  # Set image size
                )
                self.character_image_label.configure(
                    image=character_image)
            else:
                self.character_image_label.configure(image=None)
        else:
            self.character_image_label.configure(image=None)

        self.character_name_var.set(data["name"])
        self.ref_prompt_text_var.set(
            os.path.basename(data["ref_audio"]).split('.')[0])
        self.ref_audio_lang_var.set(data["ref_audio_lang"])
        self.speed_factor_var.set(str(data["speed_factor"]))
        self.model_from_var.set(data["from_model"])
        self.set_ui_parameters(data["parameters"])
        self.model_template_var.set(data["template"])
        self.model_message_var.set(data["message"])

        self.character["ref_audio_path"] = self.ref_audio_var.get()
        self.character["prompt_lang"] = self.ref_audio_lang_var.get()
        self.character["prompt_text"] = self.ref_prompt_text_var.get()
        self.character["speed_factor"] = self.speed_factor_var.get()

        self.memo_path = mem.get_store_path(os.path.dirname(path))
        if mem.check_vector_store_exists(self.memo_path):
            self.mem_vector_store = mem.load_vector_store(self.memo_path)
        else:
            self.mem_vector_store = None

    def toggle_memory_query(self, event=None):
        if self.query_memory_before_send_message:
            self.memory_switch.deselect()
            self.query_memory_before_send_message = False
        else:
            self.memory_switch.select()
            self.query_memory_before_send_message = True

    def toggle_recording(self, event=None):
        if self.asr.is_recording:
            print("stop recording...")
            self.asr.stop()
            self.record_switch.deselect()  # Deselect when stopping
            self.dialing_switch.deselect()  # Deselect when stopping
            self.auto_send_message = False

        else:
            print("start recording...")
            self.asr.start()
            self.record_switch.select()  # Select when starting

    def toggle_dialing(self, event=None):
        if self.auto_send_message:
            print("stop dialing...")
            self.asr.stop()
            self.dialing_switch.deselect()  # Deselect when stopping
            self.record_switch.deselect()  # Deselect when stopping
            self.auto_send_message = False

        else:
            print("start dialing...")
            self.asr.start()
            self.dialing_switch.select()  # Select when starting
            self.record_switch.select()
            self.auto_send_message = True

    def toggle_audio_playback(self, event=None):
        if self.audio_player.stop_event.is_set():
            self.tts.start()
            self.audio_player.start()
            print("started audio playback...")
        else:
            self.tts.stop()
            self.audio_player.stop()
            print("stopped audio playback...")

    def send_message(self, event=None):
        user_input = self.input_text.get()
        if not user_input.strip():
            # if the input is empty or contains only whitespace, do nothing
            return
        self.input_text.delete(0, ctk.END)
        self.history_text.insert(ctk.END, "\n")
        self.history_text.insert(ctk.END, f"You:\n")
        self.history_text.insert(ctk.END, f" {user_input}\n")
        self.history_text.see(ctk.END)
        threading.Thread(target=self.send_message_to_model,
                         args=(user_input,), daemon=True).start()

    def extract_think_tags(text):
        # 使用正则表达式匹配 <think> 和 </think> 标签及其内容
        pattern = r'<think>(.*?)</think>'
        matches = re.findall(pattern, text, re.DOTALL)

        if not matches:
            return text, []

        extracted_parts = [f"<think>{match}</think>" for match in matches]
        remaining_text = re.sub(pattern, "", text)

        return remaining_text, extracted_parts

    def send_message_to_model(self, user_input):
        prompt = user_input.strip()
        try:
            conversation_history = self.history_text.get(
                "1.0", ctk.END).strip()
            conversation_history_str = ""
            if conversation_history:
                # Get last chunk of conversation history
                conversation_history_str = mem.split_text(
                    conversation_history)[-1:]

            # Retrieve relevant context from the vector store
            if self.query_memory_before_send_message and conversation_history_str:
                self.perform_query(query=str(user_input))
                relevant_documents_str = self.memo_text.get(
                    "1.0", ctk.END).strip()

                prompt = chat.generate_contextual_prompt(
                    user_input=user_input, conversation_history=conversation_history_str, relevant_documents=relevant_documents_str)

            response = chat.generate_completion(
                prompt, self.character['name'])
            if response.status_code == 200:
                self.history_text.insert(
                    ctk.END, f"{self.character['name']}: \n")
                sentence_buffer = ""
                is_thinking = True
                for chunk in response.iter_lines():
                    if chunk:
                        try:
                            json_data = json.loads(chunk.decode('utf-8'))
                            if "response" in json_data:
                                text_part = json_data["response"]
                                sentence_buffer += text_part
                                if is_thinking and sentence_buffer.startswith("<think>"):
                                    think_end_index = sentence_buffer.find(
                                        "</think>")
                                    if think_end_index != -1:
                                        len_end_tag = len("</think>")
                                        sentence_buffer = sentence_buffer[think_end_index+len_end_tag:]
                                        is_thinking = False
                                        if len(text_part) < len_end_tag:
                                            print(text_part, flush=True)
                                        else:
                                            print(text_part[:text_part.find(
                                                "</think>")+len_end_tag], flush=True)
                                    else:
                                        print(text_part, flush=True, end='')
                                else:
                                    self.history_text.insert(
                                        ctk.END, f"{text_part}")

                                    if re.search(r"[”）)。？！」.~]$", sentence_buffer):
                                        if self.extract_dialogue_for_tts:
                                            dialogues = utils.extract_dialogue_from_text(
                                                sentence_buffer)
                                            if len(dialogues) > 0:
                                                for dialogue in dialogues:
                                                    self.tts.add_text_to_queue(
                                                        dialogue)
                                                sentence_buffer = ""
                                        else:
                                            self.tts.add_text_to_queue(
                                                sentence_buffer)
                                            sentence_buffer = ""
                                        self.history_text.see(ctk.END)
                                    elif json_data.get("done", False):
                                        dialogues = utils.extract_dialogue_from_text(
                                            sentence_buffer)
                                        for dialogue in dialogues:
                                            self.tts.add_text_to_queue(
                                                dialogue)
                                        sentence_buffer = ""
                                        break
                        except json.JSONDecodeError:
                            print(
                                f"JSON decoding error: {chunk}", file=sys.stderr)
                            continue
            else:
                print(f"message send failed! Response: {response}")

        except Exception as e:
            messagebox.showerror("message send failed!", str(e))
            print("message send failed!", str(e))

    def listen_stt_output(self):
        while True:
            if not self.input_text_queue.empty():
                recognized_text = self.input_text_queue.get()
                if recognized_text == SPEECH_START:
                    if self.auto_send_message:
                        self.tts.clear_text_queue()
                        self.audio_queue.queue.clear()
                    # print("Speech started")
                    continue
                elif recognized_text == SPEECH_END:
                    # print("Speech ended")
                    if self.auto_send_message:
                        self.send_message()
                else:
                    # 检查是否有选中的文本
                    try:
                        start_pos = self.input_text.index(
                            "sel.first")  # 获取选中文本的起始位置
                        end_pos = self.input_text.index(
                            "sel.last")    # 获取选中文本的结束位置
                        # 删除选中的文本
                        self.input_text.delete(start_pos, end_pos)
                    except Exception as e:
                        # 如果没有选中的文本，捕获异常并忽略
                        pass

                    # 插入新文本到光标位置
                    self.input_text.insert(ctk.INSERT, recognized_text)

            time.sleep(0.2)
    if __name__ == "__main__":
        ui_mainloop()
