import os
import json
import logging
from typing import Optional
from tavily import TavilyClient
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


async def web_search(
    query: str, max_results: int = 5, include_raw_content: bool = False
) -> str:
    """
    Search the web using Tavily API.

    Args:
        query: Search query string
        max_results: Maximum number of results to return
        include_raw_content: Whether to include raw HTML content

    Returns:
        Formatted search results as a string
    """
    try:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "Error: TAVILY_API_KEY environment variable not set"

        client = TavilyClient(api_key=api_key)

        # Perform search
        response = client.search(
            query=query,
            max_results=max_results,
            include_raw_content=include_raw_content,
        )

        # Format results
        results = []
        for idx, result in enumerate(response.get("results", []), 1):
            formatted_result = f"\n{idx}. **{result.get('title', 'No title')}**"
            formatted_result += f"\n   URL: {result.get('url', 'No URL')}"
            formatted_result += f"\n   {result.get('content', 'No content')}"
            if result.get("score"):
                formatted_result += f"\n   Relevance: {result['score']:.2f}"
            results.append(formatted_result)

        if not results:
            return f"No results found for query: {query}"

        return f"Search Results for '{query}':\n" + "\n".join(results)

    except Exception as e:
        error_msg = f"Web search error: {str(e)}"
        logger.error(error_msg)
        return error_msg
