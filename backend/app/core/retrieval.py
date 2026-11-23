# backend/app/core/retrieval.py
import os
import re
import voyageai
from pymongo import MongoClient
from dotenv import load_dotenv
from typing import Tuple, List, Dict, Any
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

load_dotenv()

vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client["academic_chatbot"]
collection = db["policy_chunks"]

async def retrieve_with_context(query: str, feature_area: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Hybrid search: Uses exact keyword matching for course codes (e.g., CS101) 
    and vector similarity for semantic meaning.
    """
    
    # 1. Keyword extraction (find words like CS101 or BUS202)
    keywords = re.findall(r'\b[A-Z]{2,4}\d{3}\b', query.upper()) 
    
    # 2. Build the Mongo filter
    filter_query = {}
    if feature_area and feature_area != "general":
        filter_query["feature_area"] = feature_area
        
    if keywords:
        # If they typed a course code, only search chunks that contain it
        filter_query["text"] = {"$regex": "|".join(keywords), "$options": "i"}
        
    cursor = collection.find(filter_query)
    chunks = list(cursor)

    # Fallback: If keyword search found nothing, search the whole feature area
    if not chunks and keywords:
        filter_query.pop("text", None)
        cursor = collection.find(filter_query)
        chunks = list(cursor)

    if not chunks:
        return "No policy documents found.", []

    # 3. Vector similarity
    query_embed = vo.embed([query], model="voyage-3", input_type="query").embeddings[0]
    chunk_embeddings = [c["embedding"] for c in chunks]
    similarities = cosine_similarity([query_embed], chunk_embeddings)[0]

    # 4. Get top 3
    top_indices = np.argsort(similarities)[-3:][::-1]

    citations = []
    context_parts = []
    
    for idx in top_indices:
        if similarities[idx] < 0.3: continue
        chunk = chunks[idx]
        source_num = len(citations) + 1
        context_parts.append(f"[source {source_num}] {chunk['title']} - {chunk['section']}:\n{chunk['text']}")
        citations.append({
            "id": str(chunk["_id"]),
            "title": chunk["title"],
            "section": chunk["section"],
            "text": chunk["text"]
        })

    return "\n\n".join(context_parts), citations