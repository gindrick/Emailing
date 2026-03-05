import os
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


async def read_file(path: str) -> str:
    """
    Read contents of a file.
    
    Args:
        path: Path to the file to read
        
    Returns:
        File contents as a string
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            return f"Error: File '{path}' does not exist"
        
        if not file_path.is_file():
            return f"Error: '{path}' is not a file"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"Read file: {path} ({len(content)} bytes)")
        return content
        
    except Exception as e:
        error_msg = f"File read error: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def write_file(path: str, content: str) -> str:
    """
    Write or overwrite contents to a file.
    
    Args:
        path: Path to the file to write
        content: Content to write to the file
        
    Returns:
        Success message or error
    """
    try:
        file_path = Path(path)
        
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Wrote file: {path} ({len(content)} bytes)")
        return f"Successfully wrote {len(content)} bytes to '{path}'"
        
    except Exception as e:
        error_msg = f"File write error: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def list_files(directory: str = ".") -> str:
    """
    List files in a directory.
    
    Args:
        directory: Directory path to list files from
        
    Returns:
        List of files and directories as a formatted string
    """
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return f"Error: Directory '{directory}' does not exist"
        
        if not dir_path.is_dir():
            return f"Error: '{directory}' is not a directory"
        
        items = []
        for item in sorted(dir_path.iterdir()):
            if item.is_dir():
                items.append(f"[DIR]  {item.name}/")
            else:
                size = item.stat().st_size
                items.append(f"[FILE] {item.name} ({size} bytes)")
        
        if not items:
            return f"Directory '{directory}' is empty"
        
        header = f"Contents of '{directory}':\n"
        return header + "\n".join(items)
        
    except Exception as e:
        error_msg = f"Directory listing error: {str(e)}"
        logger.error(error_msg)
        return error_msg