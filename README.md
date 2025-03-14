# NekkoTavern

本地调用 ollama 和 gpt-sovits 进行智能对话、语音合成的极简AI角色扮演聊天软件。
(这是另一个项目的升级版，如果你只是想简单了解核心流程和接口调用，可以参考[链接](https://github.com/chi-ha-ya/AI-Waifu-All-In-One))。

## 功能特性
- **完全离线**：无需网络，单卡运行。
- **自由定制**：支持导入导出角色卡，自定义角色性格和音色。
- **实时对话**：[gpt-sovits](https://github.com/RVC-Boss/GPT-SoVITS/tree/20240821v2)语音合成,[faster-whisper](https://huggingface.co/guillaumekln/faster-whisper-small/tree/main)语音识别,支持实时文字/语音聊天。
- **多语言**：自带中日英等多语言支持（依赖底模和gpt-sovits）。
- **长期记忆**：已实现小型RAG系统，支持保存长期记忆。
- **[视频演示]**：待施工。
## 环境要求
- **Ollama**：至少一个对话模型。
- **GPT-SovitsV2**：启动api 服务，支持零样本推理。
## 安装部署

#### Ollama：
1. 安装运行 Ollama（[官网](https://ollama.com/)）。
2. 安装对话模型 (推荐:[qwen2.5:7b](https://ollama.com/library/qwen2.5:7b))：
    ```bash
    ollama pull qwen2.5:7b
    ```
3. 安装embeding模型 [bge-m3](https://ollama.com/library/bge-m3)：
    ```bash
    ollama pull bge-m3
    ```

#### GPT-SOVITS：
1. 下载解压 [整合包](https://github.com/RVC-Boss/GPT-SoVITS/releases/tag/20240821v2)。
2. 根目录创建一个名为`go-api.bat`的批处理脚本，内容如下：
    ```bash
    runtime\python.exe api_v2.py
    pause
    ```
3. 双击运行`go-api.bat`，启用推理服务。
#### 启动
1. Python 依赖
    ```bash
    pip install -r requirements.txt
    ```
2. 下载faster-faster-whisper语音识别模型到`model/faster-whisper-small/`目录，[下载链接](https://huggingface.co/guillaumekln/faster-whisper-small/tree/main)。

整合包下载解压后，直接双击`launch.bat`启动,可以略过以上安装步骤，[下载链接](https://pan.baidu.com/s/1pRjYZf7vSd2ccW_u1oq_pQ?pwd=6666)。
## 使用教程
聊天界面：
![img](/src/chat.png)
角色界面(参考音频支持实时切换，其他参数build后生效),模型参数请参考[文档](https://www.llamafactory.cn/ollama-docs/modelfile.html#%E6%9C%89%E6%95%88%E7%9A%84%E5%8F%82%E6%95%B0%E5%92%8C%E5%80%BC)：
![img](/src/chara.png)
角色知识库界面：
![img](/src/mem.png)
## 文件结构
```
NekkoTavern
├── model
├   └──faster-whisper-small     # faster-whisper 模型
└── character                   # 角色目录
    └── Nekko
        ├── *.png               # 角色卡
        ├── *.wav               # 参考音频，文件名为语音内容
        ...
├── launch.bat                  # 双击启动
```
## 其它
- 添加系统环境变量"OLLAMA_MODELS"，可以指定模型安装路径到其他盘。
- 参考语音是5~10s干净的人声，文件名为语音内容，当前为了开箱即用仅支持未训练推理
