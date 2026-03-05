import os
import logging
import httpx
from dotenv import load_dotenv
from urllib.parse import quote

logger = logging.getLogger(__name__)
load_dotenv()


async def wolfram_query(query: str) -> str:
    """
    Query Wolfram Alpha using the LLM API for AI-optimized responses.

    Args:
        query: Query string for Wolfram Alpha

    Returns:
        Formatted response from Wolfram Alpha LLM API
    """
    try:
        # Get API key from environment
        app_id = os.getenv("WOLFRAM_APP_ID")
        if not app_id:
            error_msg = "Error: WOLFRAM_APP_ID environment variable not set"
            logger.error(error_msg)
            return error_msg

        logger.info(f"Wolfram Alpha LLM API query starting for: {query}")

        # LLM API endpoint
        url = "https://www.wolframalpha.com/api/v1/llm-api"
        
        # Parameters for the API call
        params = {
            "appid": app_id,
            "input": query,
            "maxchars": 8000  # Increase from default 6800 for more complete responses
        }
        
        # Make the API request
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, params=params, timeout=30.0)
            
            # Check for errors
            if response.status_code == 403:
                return "Error: Invalid Wolfram Alpha API key or access denied"
            elif response.status_code == 400:
                return "Error: Invalid query format"
            elif response.status_code == 501:
                # 501 means Wolfram Alpha didn't understand the query
                # The response text contains suggestions
                logger.info(f"Wolfram Alpha couldn't understand the query")
                return f"Wolfram Alpha couldn't understand the query: '{query}'. {response.text.strip()}"
            elif response.status_code != 200:
                logger.error(f"API returned status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return f"Error: Wolfram Alpha API returned status code {response.status_code}"
            
            # The LLM API returns plain text, not XML
            result_text = response.text.strip()
            
            if not result_text:
                return "No results found for your query"
            
            # Check for common error messages in the response
            if "Wolfram|Alpha did not understand your input" in result_text:
                return f"Wolfram Alpha could not understand the query: {query}"
            
            if "No short answer available" in result_text and len(result_text) < 100:
                return "No detailed answer available for this query"
            
            logger.info(f"Successfully received response from Wolfram Alpha LLM API")
            
            # The LLM API already returns well-formatted text, so we can return it directly
            # Just add a header for clarity
            return f"Wolfram Alpha result for '{query}':\n\n{result_text}"

    except httpx.TimeoutException:
        return "Error: Wolfram Alpha query timed out"
    except Exception as e:
        error_msg = f"Wolfram Alpha error: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg