import time
import logging

logger = logging.getLogger(__name__)

def web_search(query: str) -> str:
    """Search DuckDuckGo for information"""
    try:
        from ddgs import DDGS
        print(f"🔍 Searching web: {query}")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No results found."
            output = f"Web search results for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n{r['body']}\nSource: {r['href']}\n\n"
            return output
    except ImportError:
        return "Web search unavailable. Install: pip install duckduckgo-search"
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Search failed: {str(e)}"

def deep_research(topic: str, num_queries: int = 3) -> str:
    """Perform multi-step research"""
    print(f"🔬 Deep research: {topic}")
    results = []
    queries = [topic, f"{topic} latest developments", f"{topic} expert analysis"]
    for q in queries[:num_queries]:
        result = web_search(q)
        results.append(result)
        time.sleep(1)
    return "\n\n--- NEXT SEARCH ---\n\n".join(results)
