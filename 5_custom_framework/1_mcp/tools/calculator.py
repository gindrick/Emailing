import math
import logging

logger = logging.getLogger(__name__)


async def calculate(expression: str) -> str:
    """
    Safely evaluate mathematical expressions.
    
    Args:
        expression: Mathematical expression to evaluate
        
    Returns:
        Result of the calculation as a string
    """
    try:
        # Define safe built-ins for evaluation
        safe_dict = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
            'pow': pow,
            'sqrt': math.sqrt,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'pi': math.pi,
            'e': math.e,
            'log': math.log,
            'log10': math.log10,
            'exp': math.exp,
        }
        
        # Evaluate the expression with restricted built-ins
        result = eval(expression, {"__builtins__": {}}, safe_dict)
        
        logger.info(f"Calculated: {expression} = {result}")
        return f"Result: {result}"
        
    except Exception as e:
        error_msg = f"Calculation error: {str(e)}"
        logger.error(error_msg)
        return error_msg