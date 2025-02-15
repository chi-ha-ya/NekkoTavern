import os
import json
import re
from tkinter import filedialog, messagebox
from PIL import Image, PngImagePlugin
import base64


def extract_dialogue_from_text(text):
    pattern = r'''(?:“[^”]*”|‘[^’]*’|"[^"]*"|'[^']*'|「[^」]*」|『[^』]*』|［[^］]*］|\([^)]*\)|（[^）]*）)'''
    matches = re.findall(pattern, text)
    dialogues = [match[1:-1] if match else match for match in matches]
    return dialogues


def get_absolute_path(path: str, base_dir: str):
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    path = os.path.normpath(path)  # Normalize the path
    # Replace backslashes with forward slashes
    return path.replace(os.sep, "/")


def get_relative_path(path: str, base_dir: str = None):
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(path)  # Normalize the path
    base_dir = os.path.normpath(base_dir)
    if os.path.isabs(path) and path.startswith(base_dir):
        path = os.path.relpath(path, base_dir)
    # Replace backslashes with forward slashes
    return path.replace(os.sep, "/")


def save_config(config, config_path="config.json"):
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error writing to {config_path}: {e}")
        return False


def select_file(self, title, filetypes, initialdir=None):
    if initialdir is None:
        initialdir = os.getcwd()
    file_path = filedialog.askopenfilename(
        title=title,
        filetypes=filetypes,
        initialdir=initialdir
    )
    return file_path


def load_config(config_path="config.json"):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"Configuration loaded successfully from {config_path}")
        return config
    except FileNotFoundError:
        print(f"The configuration file {config_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"The configuration file {config_path} could not be decoded.")
        return None
    except Exception as e:
        print(f"An error occurred while loading the configuration file: {e}")
        return None


def load_settings_from_png(file_path: str):
    try:
        with Image.open(file_path) as img:
            metadata = img.info
            if "chara" in metadata:
                chara_data_base64 = metadata["chara"]
                chara_data = base64.b64decode(
                    chara_data_base64).decode('utf-8')
                chara_data = json.loads(chara_data)
                return chara_data
            else:
                print(f"The 'chara' metadata was not found in the image.")
                return None
    except FileNotFoundError:
        print(f"The configuration file {file_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"The configuration file {file_path} could not be decoded.")
        return None
    except Exception as e:
        print(f"An error occurred while loading the configuration file: {e}")
        return None


def load_settings_from_json(file_path: str) -> dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"The configuration file {file_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"The configuration file {file_path} could not be decoded.")
        return None
    except Exception as e:
        print(f"An error occurred while loading the configuration file: {e}")
        return None


def load_settings_from_file(file_path: str):
    try:
        if file_path.lower().endswith('.png'):
            data = load_settings_from_png(file_path)
        elif file_path.lower().endswith('json'):
            data = load_settings_from_json(file_path)
        else:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            data = content

        return data
    except Exception as e:
        print(f"Error loading character data: {e}")
        return None


def save_settings_to_json(character: dict, file_path: str):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(character, f, indent=4, ensure_ascii=False)
        print(f"Settings saved successfully to {file_path}")
        return True
    except Exception as e:
        print(f"Error saving settings to JSON file: {e}")
        return False


def save_settings_to_png(character: dict, file_path: str):
    try:
        chara_data = json.dumps(character, ensure_ascii=False, indent=4)
        chara_data_base64 = base64.b64encode(
            chara_data.encode('utf-8')).decode('utf-8')
        with Image.open(file_path) as img:
            img_copy = img.copy()
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("chara", chara_data_base64)
            img_copy.save(file_path, format="PNG", pnginfo=png_info)
        print(f"Settings saved successfully to {file_path}")
        return True
    except FileNotFoundError:
        print(f"The image file {file_path} was not found.")
        return False
    except Exception as e:
        print(f"Error saving settings to PNG file: {e}")
        return False


def save_character_settings(character_settings, file_path: str):
    audio_path = character_settings["ref_audio"]
    dir_path = os.path.dirname(file_path)
    if dir_path in audio_path:
        character_settings["ref_audio"] = audio_path.replace(
            f"{dir_path}/", '')  # Convert absolute path to relative path
    if file_path.lower().endswith('.png'):
        return save_settings_to_png(character_settings, file_path)
    elif file_path.lower().endswith('.json'):
        return save_settings_to_json(character_settings, file_path)
    else:
        print(
            f"The file format {os.path.splitext(file_path)[1]} is not supported. Please use .png or .json formats."
        )
        return False


def main():
    while True:
        # 提示用户输入PNG文件或文件夹路径
        input_path = input("请输入角色卡PNG文件的路径或文件夹路径: ").strip()

        # 检查路径是否存在
        if not os.path.exists(input_path):
            print("指定的路径无效。")
            continue

        # 检查路径是文件还是文件夹
        if os.path.isfile(input_path):
            # 如果是文件，处理单个文件
            if input_path.lower().endswith('.png'):
                character_data = load_settings_from_file(input_path)
                if character_data:
                    json_file_path = os.path.splitext(input_path)[0] + '.json'
                    save_settings_to_json(character_data, json_file_path)
                else:
                    print("无法从PNG文件中读取角色信息。")
            else:
                print("指定的文件不是PNG格式。")
        elif os.path.isdir(input_path):
            # 如果是文件夹，批量处理文件夹中的所有PNG文件
            for file_name in os.listdir(input_path):
                if file_name.lower().endswith('.png'):
                    png_file_path = os.path.join(input_path, file_name)
                    character_data = load_settings_from_file(png_file_path)
                    if character_data:
                        json_file_path = os.path.splitext(
                            png_file_path)[0] + '.json'
                        save_settings_to_json(character_data, json_file_path)
                    else:
                        print(f"无法从文件 {file_name} 中读取角色信息。")
            print("批量处理完成。")
        else:
            print("指定的路径无效。")

        # 询问用户是否继续
        continue_input = input("是否继续处理其他文件或文件夹？(y/n): ").strip().lower()
        if continue_input != 'y':
            break


if __name__ == "__main__":
    main()
