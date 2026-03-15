import json
import os
import numpy as np
from datetime import datetime
from config import MEMORY_FILE, MAX_MEMORY_ENTRIES, MAX_CONTEXT_ENTRIES
from core.utils import get_time, get_relative_time, get_time_context

# Initialize embedding model for semantic search
try:
    from sentence_transformers import SentenceTransformer
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception:
    embedding_model = None

def get_embedding(text):
    """Generates a vector embedding for a given text string."""
    try:
        return embedding_model.encode(text) if embedding_model else None
    except Exception:
        return None

def cosine_sim(v1, v2):
    """Calculates cosine similarity between two vectors."""
    try:
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    except Exception:
        return 0.0

def load_memory():
    """Loads memory history from JSON with error handling."""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [e for e in data if isinstance(e, dict)][-MAX_MEMORY_ENTRIES:]
    except Exception:
        pass
    return []

def save_memory(hist):
    """Saves memory to a temporary file first to prevent corruption."""
    try:
        tmp = f"{MEMORY_FILE}.tmp"
        # Ensure we only save the limit
        to_save = hist[-MAX_MEMORY_ENTRIES:]
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
        
        # Atomic swap
        if os.path.exists(MEMORY_FILE):
            os.replace(tmp, MEMORY_FILE)
        else:
            os.rename(tmp, MEMORY_FILE)
    except Exception as e:
        print(f"❌ Memory save error: {e}")

def add_memory(hist, usr, aura, typ="conversation", meta=None):
    """Adds a new interaction to history and generates embeddings."""
    if not usr.strip() or not aura.strip():
        return

    entry = {
        "user": usr,
        "aura": aura,
        "timestamp": datetime.now().isoformat(),
        "type": typ,
        "time_context": get_time_context()
    }
    
    if meta:
        # Filter metadata to avoid saving large objects (like raw search results)
        entry["metadata"] = {k: v for k, v in meta.items() if v and k != "web_result"}

    # Generate embedding for future semantic search
    if embedding_model:
        emb = get_embedding(usr)
        if emb is not None:
            entry['embedding'] = emb.tolist()
    
    hist.append(entry)
    
    # Prune list if it exceeds the limit
    if len(hist) > MAX_MEMORY_ENTRIES:
        hist[:] = hist[-MAX_MEMORY_ENTRIES:]

def get_context(hist, usr_input, max_ent=MAX_CONTEXT_ENTRIES):
    """
    Retrieves a mix of semantically relevant past memories 
    and the most recent conversational turns.
    """
    if not hist:
        return ""

    relevant_entries = []
    
    # 1. SEMANTIC SEARCH (Long-term Recall)
    if embedding_model and len(hist) > 5:
        qe = get_embedding(usr_input)
        if qe is not None:
            # We look at the last 100 entries for semantic relevance
            search_pool = hist[-100:]
            scored = []
            for e in search_pool:
                if 'embedding' in e:
                    sim = cosine_sim(qe, np.array(e['embedding']))
                    # Threshold for relevance
                    if sim > 0.45:
                        ec = e.copy()
                        ec['_score'] = sim
                        scored.append(ec)
            
            # Sort by highest similarity
            scored.sort(key=lambda x: x.get('_score', 0), reverse=True)
            relevant_entries.extend(scored[:5]) # Take top 5 semantic matches

    # 2. RECENCY (Short-term context)
    # Always include the last few messages to maintain flow
    recent_turns = hist[-4:]
    relevant_entries.extend(recent_turns)

    # 3. DE-DUPLICATE AND SORT
    # Create a unique list based on timestamp
    unique_map = {e['timestamp']: e for e in relevant_entries}
    final_selection = sorted(unique_map.values(), key=lambda x: x['timestamp'])

    # 4. FORMATTING
    ctx = "\n--- RELEVANT MEMORY & CONTEXT ---\n"
    for e in final_selection[-max_ent:]:
        dt = datetime.fromisoformat(e['timestamp'])
        rel_time = get_relative_time(dt)
        
        ctx += f"[{rel_time}] User: {e.get('user', '')}\n"
        ctx += f"[{rel_time}] AURA: {e.get('aura', '')}\n"
    
    ctx += "--------------------------------\n"
    return ctx