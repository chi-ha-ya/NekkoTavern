import requests

ollama_base_url = "http://localhost:11434/api"
gpt_sovits_tts_url = "http://127.0.0.1:9880/tts"

# True:仅将“”内台词生成语音，False:全部生成，（有bug =.=
extract_dialogue_for_tts = False


def generate_completion(prompt, model, stream=True):
    url = f"{ollama_base_url}/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": stream
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=data, stream=stream)
    return response
