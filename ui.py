import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from stt import Faster_Whisper_STT
from stt import SPEECH_START
from stt import SPEECH_END
from tts import GPT_Sovits_TTS
from vox import AudioPlayer
from chat import generate_completion
from PIL import Image
import queue
import json
import re
import time
import sys
import utils
import ollama as ollama

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

        # Configure window size
        self.root.geometry("800x480+1000+500")
        self.root.resizable(True, True)

        # ========== Main container uses TabView ==========
        self.tab_view = ctk.CTkTabview(self.root, width=800, height=480)
        self.tab_view.pack(fill="both", expand=True)

        # Create each Tab
        self.main_tab = self.tab_view.add("chat")
        self.character_tab = self.tab_view.add("chara")

        # Build the layout for each Tab
        self.build_main_tab()
        self.build_character_tab()

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

        # Add avatar display
        self.character_image_label = ctk.CTkLabel(
            self.button_frame, text="", image=None)
        self.character_image_label.grid(
            row=0, column=0, padx=0, pady=0)

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
        self.load_config_button.grid(row=0, column=1, padx=10, pady=10)

        # Recording switch
        self.record_switch = ctk.CTkSwitch(
            self.button_frame, text="REC",
            command=self.toggle_recording,
            width=36,
        )
        self.record_switch.grid(row=0, column=2, padx=10, pady=10)
        self.record_switch.deselect()  # Default is not recording

        # Dialing switch
        self.dialing_switch = ctk.CTkSwitch(
            self.button_frame, text="Dial",
            command=self.toggle_dialing,
            width=36,
        )
        self.dialing_switch.grid(row=0, column=3, padx=10, pady=10)
        self.dialing_switch.deselect()  # Default is not recording

        # Send button
        self.send_button = ctk.CTkButton(
            self.button_frame, text="Send", 
            command=self.send_message,
            width=120,height=40,)
        self.send_button.grid(row=0, column=4, padx=10, pady=10)
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
        # Initialize variables
        self.character_name_var = ctk.StringVar(value="")
        self.ref_audio_var = ctk.StringVar(value="")
        self.ref_prompt_text_var = ctk.StringVar(value="")
        self.ref_audio_lang_var = ctk.StringVar(value="ja")
        self.speed_factor_var = ctk.StringVar(value="1.0")
        self.from_var = ctk.StringVar(value="qwen2.5:7b")
        self.num_ctx_var = ctk.StringVar(value="8192")
        self.temperature_var = ctk.DoubleVar(value=1.0)
        self.template_var = ctk.StringVar(value="")
        self.additional_PARAMETER_var = ctk.StringVar(value="")
        self.ref_image_var = ctk.StringVar(value="")
        self.model_message_var = ctk.StringVar(value="")

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
            (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), weight=0)
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
            textvariable=self.from_var,
            font=Font_YaHei_12
        )
        from_entry.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")
        # Button to list ollama models
        select_audio_button = ctk.CTkButton(
            self.character_info_frame,
            text="list",
            command=self.list_installed_models,
            width=40,
            font=Font_YaHei_12
        )
        select_audio_button.grid(row=4, column=2, padx=5, pady=5, sticky="ew")

        # Num Context
        num_ctx_label = ctk.CTkLabel(
            self.character_info_frame,
            text="num_ctx:",
            font=Font_YaHei_12
        )
        num_ctx_label.grid(row=5, column=0, padx=5, pady=5, sticky="e")
        num_ctx_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.num_ctx_var,
            font=Font_YaHei_12
        )
        num_ctx_entry.grid(row=5, column=1, padx=5, pady=5, sticky="nsew")

        # Temperature
        temperature_label = ctk.CTkLabel(
            self.character_info_frame,
            text="temperature:",
            font=Font_YaHei_12
        )
        temperature_label.grid(row=6, column=0, padx=5, pady=5, sticky="e")
        temperature_slider = ctk.CTkSlider(
            self.character_info_frame,
            from_=0.0, to=1.0,
            number_of_steps=200,
            variable=self.temperature_var,
            command=self.update_temperature_label
        )
        temperature_slider.grid(row=6, column=1, padx=5, pady=5, sticky="we")

        # Temperature value label
        self.temperature_value_label = ctk.CTkLabel(
            self.character_info_frame,
            text=f"{self.temperature_var.get():.2f}",
            font=Font_YaHei_12
        )
        self.temperature_value_label.grid(
            row=6, column=2, padx=1, pady=1, sticky="w")

        # Template
        template_label = ctk.CTkLabel(
            self.character_info_frame,
            text="template(optional):",
            font=Font_YaHei_12
        )
        template_label.grid(row=7, column=0, padx=5, pady=5, sticky="e")
        template_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.template_var,
            font=Font_YaHei_12
        )
        template_entry.grid(row=7, column=1, padx=5, pady=5, sticky="nsew")

        # Additional Parameters
        additional_PARAMETER_label = ctk.CTkLabel(
            self.character_info_frame,
            text="PARAMETER(optional):",
            font=Font_YaHei_12
        )
        additional_PARAMETER_label.grid(
            row=8, column=0, padx=5, pady=5, sticky="e")
        additional_PARAMETER_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.additional_PARAMETER_var,
            font=Font_YaHei_12
        )
        additional_PARAMETER_entry.grid(
            row=8, column=1, padx=5, pady=5, sticky="nsew")

        # Additional Parameters
        MESSAGE_label = ctk.CTkLabel(
            self.character_info_frame,
            text="MESSAGE(optional):",
            font=Font_YaHei_12
        )
        MESSAGE_label.grid(
            row=9, column=0, padx=5, pady=5, sticky="e")
        MESSAGE_entry = ctk.CTkEntry(
            self.character_info_frame,
            textvariable=self.model_message_var,
            font=Font_YaHei_12
        )
        MESSAGE_entry.grid(
            row=9, column=1, padx=5, pady=5, sticky="nsew")
        """
           Buttons
        """
        self.character_buttons_frame = ctk.CTkFrame(self.character_right_frame)
        self.character_buttons_frame.grid(
            row=1, column=0, sticky="se", padx=5, pady=5)
        # Set three buttons to evenly divide horizontal space
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

    def load_character_card(self,file_path=None):
        if not file_path:
        # Open file selector to choose model file
            file_path = filedialog.askopenfilename(
                title="Select Character Card",
                filetypes=[("character Card", "*.png;*.json")],
                initialdir=self.initialdir_load
            )
        if os.path.exists(file_path):
            try:
                data = utils.load_character(file_path)
                self.update_ui_with_data(data, file_path)
                character_exists = self.check_model_exists(data["name"])
                base_model_exists = self.check_model_exists(data["from_model"])
                build_success = False

                if not character_exists :
                    if not base_model_exists:
                        messagebox.showerror("Error", f"{data['from_model']} Not Found, Import Failed!\nSee logs for more details.")
                        self.log(f"Create character {data['name']} from {file_path} Failed,\nBase model {data['from_model']} not found,You may need to  install it by following instructions:\n ollama run {data['from_model']}")
                        return
                    else:
                        build_success = self.build_model()
                if build_success or(character_exists and base_model_exists):
                    character_path = utils.get_relative_path(file_path)
                    if self.config["character"]!= character_path:
                        self.config["character"] = character_path
                        utils.save_config(self.config)  
                    self.log(f"Character {data['name']} loaded from {file_path}")
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
                data = utils.load_character(file_path)
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
        parameters = {
            "num_ctx": int(self.num_ctx_var.get()),
            "temperature": f"{float(self.temperature_var.get()):.2f}"
        }
        character_data = {
            "name": self.character_name_var.get(),
            "ref_audio": self.ref_audio_var.get(),
            "ref_audio_lang": self.ref_audio_lang_var.get(),
            "speed_factor": self.speed_factor_var.get(),
            "from_model": self.from_var.get(),
            "parameters": parameters,
            "template": self.template_var.get(),
            "message": self.model_message_var.get(),
            "description": self.model_profile_text.get("1.0", ctk.END)
        }
        try:
            utils.save_character_settings(character_data, file_path)
            self.log(
                f"Character profile was successfully saved to {file_path}")
        except Exception as e:
            messagebox.showerror(
                "Save failed", f"Saving character configuration encountered an error: {e}")

    def check_model_exists(self, model_name):
        # Check if same named model exists
        models_response = ollama.list()  # Get installed model list
        models = models_response.models  # Get model list

        return any(
            model.model == model_name or
            model.model == f"{model_name}:latest"
            for model in models)

    def build_model(self):
        # Model building logic
        parameters = {
            "num_ctx": int(self.num_ctx_var.get()),
            "temperature": float(self.temperature_var.get())
        }

        # Get additional parameters
        add_parameters = self.additional_PARAMETER_var.get()
        if add_parameters.strip():  # Check if there are additional parameters
            try:
                additional_params = json.loads(add_parameters)
                # Ensure returned value is a dictionary
                if isinstance(additional_params, dict):
                    parameters.update(additional_params)
                else:
                    raise ValueError(
                        "Additional parameters must be a dictionary")
            except json.JSONDecodeError as e:
                messagebox.showerror(
                    "Build failed", f"Invalid JSON format for additional parameters: {e}")
                return False

            except ValueError as e:
                messagebox.showerror("Build failed", str(e))
                return False

        try:
            from_model = self.from_var.get().strip()
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
                from_=self.from_var.get(),
                parameters=parameters,
                template=self.template_var.get(),
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
        self.from_var.set(data["from_model"])
        self.num_ctx_var.set(str(data["parameters"]["num_ctx"]))
        self.temperature_var.set(
            float(data["parameters"]["temperature"]))  # Update temperature value
        self.temperature_value_label.configure(
            text=f"{self.temperature_var.get():.2f}")  # Update display value
        self.template_var.set(data["template"])
        self.model_message_var.set(data["message"])
        # Remove "num_ctx" and "temperature" then convert the rest to string
        additional_parameters = data["parameters"].copy()
        additional_parameters.pop("num_ctx", None)
        additional_parameters.pop("temperature", None)
        self.additional_PARAMETER_var.set(json.dumps(
            additional_parameters, ensure_ascii=False, indent=0))
        self.character = data
        self.character["ref_audio_path"] = self.ref_audio_var.get()
        self.character["prompt_lang"] = self.ref_audio_lang_var.get()
        self.character["prompt_text"] = self.ref_prompt_text_var.get()
        self.character["speed_factor"] = self.speed_factor_var.get()

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
        threading.Thread(target=self.send_message_to_model,
                         args=(user_input,), daemon=True).start()

    def send_message_to_model(self, user_input):
        try:
            response = generate_completion(
                user_input, self.character['name'])
            if response.status_code == 200:
                self.history_text.insert(
                    ctk.END, f"{self.character['name']}: \n")
                sentence_buffer = ""
                for chunk in response.iter_lines():
                    if chunk:
                        try:
                            json_data = json.loads(chunk.decode('utf-8'))
                            if "response" in json_data:
                                text_part = json_data["response"]
                                self.history_text.insert(ctk.END, f"{text_part}")
                                sentence_buffer += text_part
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
                                        self.tts.add_text_to_queue(sentence_buffer)
                                        sentence_buffer = ""
                                elif json_data.get("done", False):
                                    dialogues = utils.extract_dialogue_from_text(
                                        sentence_buffer)
                                    for dialogue in dialogues:
                                        self.tts.add_text_to_queue(dialogue)
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
