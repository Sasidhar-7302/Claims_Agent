import chromadb
from chromadb.utils import embedding_functions
import os
import re
import math
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

# Define paths
BASE_DIR = Path(__file__).parent.parent
POLICIES_DIR = BASE_DIR / "data" / "policies"
POLICY_INDEX_FILE = POLICIES_DIR / "index.json"
DB_DIR = BASE_DIR / "data" / "chroma_db"

# Ensure DB directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)

def load_policy_index() -> List[Dict]:
    """Load policy index metadata."""
    if not POLICY_INDEX_FILE.exists():
        return []
    try:
        import json
        with open(POLICY_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("policies", [])
    except Exception as e:
        print(f"[WARN] Failed to load policy index: {e}")
        return []


class SimpleHashEmbeddingFunction:
    """Lightweight, dependency-free embedding function."""
    def __init__(self, dim: int = 256):
        self.dim = dim

    def __call__(self, input: List[str]) -> List[List[float]]:
        vectors = []
        for text in input:
            vec = [0.0] * self.dim
            tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
            for token in tokens:
                idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "simple-hash"

    def get_config(self) -> Dict:
        return {"dim": self.dim}

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> List[str]:
        return ["cosine"]

    def embed_documents(self, input: List[str]) -> List[List[float]]:
        return self.__call__(input)

    def embed_query(self, input: List[str]) -> List[List[float]]:
        return self.__call__(input)

    @classmethod
    def build_from_config(cls, config: Dict):
        dim = config.get("dim", 256) if isinstance(config, dict) else 256
        return cls(dim=dim)


def get_embedding_function():
    """Select an embedding function based on environment or availability."""
    mode = os.getenv("EMBEDDING_MODE", "").strip().lower()
    if mode == "hash":
        return SimpleHashEmbeddingFunction()

    try:
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    except Exception as e:
        print(f"[WARN] SentenceTransformer embeddings unavailable: {e}")
        return SimpleHashEmbeddingFunction()


class WarrantyVectorStore:
    def __init__(self):
        """Initialize ChromaDB client and collection."""
        self.client = chromadb.PersistentClient(path=str(DB_DIR))
        
        self.embedding_fn = get_embedding_function()
        
        self.collection = self.client.get_or_create_collection(
            name="warranty_policies",
            embedding_function=self.embedding_fn
        )

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Simple sliding window chunking."""
        if not text:
            return []
            
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
            
        return chunks

    def index_policies(self, force_reindex: bool = False) -> int:
        """
        Index all policy documents from the policies directory.
        Returns number of chunks indexed.
        """
        if force_reindex:
            self.client.delete_collection("warranty_policies")
            self.collection = self.client.get_or_create_collection(
                name="warranty_policies",
                embedding_function=self.embedding_fn
            )

        # Check if already populated (naive check)
        if self.collection.count() > 0 and not force_reindex:
            return self.collection.count()

        policy_index = load_policy_index()
        policy_map = {p.get("policy_file"): p for p in policy_index}
        files = list(POLICIES_DIR.glob("*.txt"))
        count = 0
        
        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Create chunks
                # We prepend metadata to the chunk text to help retrieval context
                filename = file_path.name
                policy_meta = policy_map.get(filename, {})
                product_model = policy_meta.get(
                    "product_name",
                    filename.replace("policy_", "").replace(".txt", "").replace("_", " ").title()
                )
                
                chunks = self._chunk_text(content)
                
                ids = []
                documents = []
                metadatas = []
                
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{filename}_{i}"
                    ids.append(chunk_id)
                    # Add meaningful context to embedding content
                    documents.append(f"Policy for {product_model}: {chunk}")
                    metadatas.append({
                        "source": filename,
                        "product": product_model,
                        "chunk_index": i,
                        "policy_id": policy_meta.get("policy_id", ""),
                        "product_id": policy_meta.get("product_id", ""),
                        "policy_file": filename,
                        "version": policy_meta.get("version", ""),
                        "effective_date": policy_meta.get("effective_date", "")
                    })
                
                if documents:
                    self.collection.add(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas
                    )
                    count += len(documents)
                    
            except Exception as e:
                print(f"Error indexing {file_path}: {e}")
                continue
                
        return count

    def ensure_indexed(self) -> int:
        """Ensure the policy store is indexed."""
        if self.collection.count() == 0:
            return self.index_policies(force_reindex=False)
        return self.collection.count()

    def query(
        self,
        query_text: str,
        n_results: int = 4,
        product_id: Optional[str] = None,
        policy_file: Optional[str] = None,
        policy_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Query the vector store for relevant policy sections.
        """
        where = None
        if policy_id:
            where = {"policy_id": policy_id}
        elif policy_file:
            where = {"policy_file": policy_file}
        elif product_id:
            where = {"product_id": product_id}

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )
        
        # Flatten results
        output = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i]
                output.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": results["distances"][0][i] if results["distances"] else 0
                })
                
        return output

# Global instance
_store_instance = None

def get_vector_store():
    global _store_instance
    if _store_instance is None:
        _store_instance = WarrantyVectorStore()
    return _store_instance
