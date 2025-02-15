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


def generate_summary_prompt(content):
    prompt = f"""
    As who you are, please write a memo summarizing the given text. Focus on listing the key points and highlighting the main truths. If there are dialogues, retain the roles and their lines for easy reference. Ensure no information is omitted and record the details as thoroughly as possible.

    Given text:
    {content}

    Summary:
    """
    return prompt


def generate_contextual_prompt(user_input, relevant_documents, conversation_history):

    prompt = f"""
    As who you are, Please generate a response to the user's input. Ensure the response maintains coherence with the conversation history. Meanwhile, there are some relevant documents that may be useful for the response,use them to enhance the content of response. If there is any irrelevant or inaccurate information in the relevant documents, please disregard it. Prioritize information that directly relates to the user's input and the ongoing conversation.

    Relevant Documents:
    {relevant_documents}

    Conversation History:
    {conversation_history}

    User's Input:
    {user_input}

    Response:
    """
    return prompt
