import sys
import io
import logging
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)


async def execute_python(code: str) -> str:
    """
    Execute Python code in a subprocess for better isolation and reliability.
    
    Args:
        code: Python code to execute
        
    Returns:
        Output from code execution or error message
    """
    try:
        # Create a temporary file to store the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Execute the code in a subprocess
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            # Combine stdout and stderr
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n"
                output += f"STDERR:\n{result.stderr}"
            
            if not output and result.returncode == 0:
                output = "Code executed successfully (no output)"
            elif not output:
                output = f"Process exited with code {result.returncode}"
            
            logger.info(f"Executed Python code ({len(code)} chars)")
            return output
            
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return "Python execution timeout (30 seconds)"
    except Exception as e:
        error_msg = f"Python execution error: {type(e).__name__}: {str(e)}"
        logger.error(error_msg)
        return error_msg