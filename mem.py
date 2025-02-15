import os
from chromadb.config import Settings
from chromadb.api.types import Embedding
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.docstore.document import Document
from langchain_chroma import Chroma
import requests
from typing import List
import uuid
import ollama as ollama
import json
from typing import (
    List,
    Tuple,
)

vector_store_path = "memory"
collection_name = "memory_collection"


CHUNK_SIZE = 1024    # 每个块的大小
CHUNK_OVERLAP = 64   # 块之间的重叠大小
QUERY_K = 4
DEFAULT_EMBEDDING_MODEL = "bge-m3"  # or "nomic-embed-text"
DEFAULT_EMBEDDING_URL = "http://localhost:11434/api/embeddings"

# 初始化文本分割器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "！", "？", ".",
                "!", "?", "；", ";", "，", ","]  # 中文、日文、英文标点符号
)


class OllamaEmbeddingFunction:
    def __init__(self, model_name=DEFAULT_EMBEDDING_MODEL, base_url=DEFAULT_EMBEDDING_URL):
        self.model_name = model_name
        self.base_url = base_url

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            embedding = self.embed_query(text)
            embeddings.append(embedding)
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        try:
            response = requests.post(
                self.base_url,
                json={"model": self.model_name,
                      "prompt": query},  # 发送单个 prompt
                timeout=10
            )
            # response = ollama.embed(model=self.model_name, input=query)
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            # 检查 embedding 存在且格式正确
            if embedding and isinstance(embedding, list) and all(isinstance(x, (int, float)) for x in embedding):
                return embedding
            else:
                print("Ollama 没有返回 embedding 或返回的格式不正确。")
                print("Ollama 返回的 JSON:", data)  # 打印完整的 JSON 响应，方便调试
                return []
        except requests.exceptions.RequestException as e:
            print(f"连接 Ollama 出错: {e}")
            return []
        except (KeyError, TypeError) as e:
            print(f"处理 Ollama 响应出错: {e}, 响应内容: {response.text}")  # 打印响应内容
            return []


def get_store_path(folder_name: str) -> str:
    return os.path.join(folder_name, vector_store_path)


# 初始化向量存储
def init_vector_store(store_path: str) -> Chroma:
    ollama_ef = OllamaEmbeddingFunction()
    settings = Settings(anonymized_telemetry=False)
    if not os.path.exists(store_path):
        os.makedirs(store_path)
    store = Chroma(persist_directory=store_path,
                   embedding_function=ollama_ef, client_settings=settings,
                   collection_metadata={"hnsw:space": "cosine"},
                   collection_name=collection_name)  # 使用新的初始化方式
    print(f"向量存储初始化完成，路径: {store_path}")

    return store


# 检查向量存储是否存在
def check_vector_store_exists(store_path: str) -> bool:
    return os.path.exists(store_path) and len(os.listdir(store_path)) > 0


# 加载向量存储
def load_vector_store(store_path: str) -> Chroma:
    ollama_ef = OllamaEmbeddingFunction()
    settings = Settings(anonymized_telemetry=False)
    return Chroma(persist_directory=store_path,
                  embedding_function=ollama_ef, client_settings=settings,
                  collection_metadata={"hnsw:space": "cosine"},
                  collection_name=collection_name)  # 使用新的初始化方式


def split_text(text: str) -> list[str]:
 # 使用 RecursiveCharacterTextSplitter 分割文本
    paragraphs = text_splitter.split_text(text)

    # 检查最后一段是否过短，并将其合并到前一段
    if len(paragraphs) > 1:
        last_paragraph = paragraphs[-1]

        if len(last_paragraph) < CHUNK_SIZE / 3:  # 如果最后一段长度小于平均段落长度的3分之一，则合并到前一段
            paragraphs[-2] += " " + last_paragraph  # 合并最后一段到前一段
            paragraphs.pop()  # 删除原来的最后一段

    return paragraphs


# 插入文本到向量存储
def insert_text_to_vector_store(store_path: str, text: str, chroma: Chroma = None) -> None:
    if not chroma:
        chroma = get_or_create_vector_store(store_path)

    # 使用 RecursiveCharacterTextSplitter 分割文本
    print(f"插入文本到向量存储,文本长度: {len(text)}")  # 打印文本长度
    paragraphs = split_text(text)
    # 打印分割后的段落数和每段的长度
    segment_lengths = [len(p) for p in paragraphs]
    print(f"分割后的段落数: {len(paragraphs)} 每段长度：{segment_lengths}")
    documents = [
        # Generate a unique ID for each document
        Document(page_content=paragraph, metadata={}, id=uuid.uuid4().hex)
        for paragraph in paragraphs
    ]
    chroma.add_documents(documents)


# 删除文档从向量存储
def delete_document_from_vector_store(store_path: str, document_ids: List[str], chroma: Chroma = None) -> None:
    if not chroma:
        chroma = load_vector_store(store_path)

    # 确认文档存在后再删除
    try:
        result = chroma.get(ids=document_ids)
        if len(result["documents"]) > 0:
            # print(f"正在删除文档ID为 {document_ids} 内容为 {result} 的文档...\n")
            chroma.delete(document_ids)
            print(f"ID为 {document_ids} 的文档已删除")
        else:
            print(f"ID为 {document_ids} 的文档不存在，无法删除。")
    except Exception as e:
        print(f"删除文档时出错: {e}")
# 获取相关上下文从向量存储


def get_relevant_context_from_vector_store(store_path: str, query: str, k: int = QUERY_K,
                                           chroma: Chroma = None) -> List[Tuple[Document, float]]:

    if not chroma:
        chroma = load_vector_store(store_path)

    results_with_scores = chroma.similarity_search_with_score(
        query, k=k)  # 获取文档和相似度

    return results_with_scores


# 获取或创建向量存储
def get_or_create_vector_store(store_path: str) -> Chroma:
    if check_vector_store_exists(store_path):
        return load_vector_store(store_path)
    else:
        return init_vector_store(store_path)


if __name__ == "__main__":
    store_path = get_store_path("character/Nekko")
    query = "your search query"
    k = 5  # 返回的文档数量
    threshold = 0.7  # 相似度阈值
    store = get_or_create_vector_store(store_path)
