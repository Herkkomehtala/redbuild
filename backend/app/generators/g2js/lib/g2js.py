import subprocess
import os
import logging

logger = logging.getLogger(__name__)

class G2JSRunner:
    """
    Wrapper for executing the GadgetToJScript binary via Wine.
    """
    
    def __init__(self, executable_path: str, loader_source: str):
        """
        Initialize the runner.

        Args:
            executable_path: Path to GadgetToJScript.exe.
            loader_source: Path to the input C# loader source code.
        """
        self.exe = executable_path
        self.loader_source = loader_source

    def _to_wine_path(self, linux_path: str) -> str:
        """
        Converts a Linux path to a Wine-compatible Windows path (Z: drive).

        Why:
        GadgetToJScript compiles code at runtime using CSharpCodeProvider.
        Inside the Wine environment, it expects Windows-style paths (backslashes, drive letters)
        to locate files. Standard Linux paths will fail to resolve.
        """
        # Assumes standard Wine configuration where the root (/) is mapped to Z:
        return "Z:" + linux_path.replace("/", "\\")

    def run(self, output_type: str, output_path_base: str) -> str:
        """
        Executes GadgetToJScript to generate the gadget.

        Args:
            output_type: The target format (e.g., 'js', 'vbs', 'hta').
            output_path_base: The base path (without extension) for the output file.

        Returns:
            The content of the generated script file.

        Raises:
            RuntimeError: If the external process fails.
            FileNotFoundError: If the expected output file is not created.
        """
        # Convert paths to Wine format because CSharpCodeProvider/StreamWriter inside Wine need Windows paths
        wine_loader_source = self._to_wine_path(self.loader_source)
        wine_output_base = self._to_wine_path(output_path_base)

        cmd = [
            "wine", self.exe, 
            "-w", output_type, 
            "-b", 
            "-c", wine_loader_source, 
            "-d", "System.dll,System.Core.dll", 
            "-o", wine_output_base
        ]
        
        logger.info(f"Running external command: {'. '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.stdout:
            logger.info(f"G2JS STDOUT:\n{result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"G2JS STDERR:\n{result.stderr.strip()}")

        if result.returncode != 0:
            raise RuntimeError(f"G2JS execution failed with code {result.returncode}")
        
        expected_file = f"{output_path_base}.{output_type}"
        if not os.path.exists(expected_file):
             raise FileNotFoundError(f"G2JS did not produce expected file: {expected_file}")
             
        with open(expected_file, "r") as f:
            return f.read()