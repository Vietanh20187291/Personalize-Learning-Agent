# backend/rag/embedder.py
from typing import Optional

from langchain_community.embeddings import HuggingFaceEmbeddings

_embeddings: Optional[HuggingFaceEmbeddings] = None


def get_embeddings() -> Optional[HuggingFaceEmbeddings]:
	"""Khởi tạo embedding theo kiểu lazy để tránh treo backend lúc startup."""
	global _embeddings
	if _embeddings is not None:
		return _embeddings

	try:
		_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
	except Exception as exc:
		# Không chặn startup/login khi model embedding chưa tải được.
		print(f"⚠️ Không khởi tạo được embedding model: {exc}")
		_embeddings = None

	return _embeddings


# Backward-compatible alias (có thể là None trước lần gọi đầu tiên).
embeddings = None