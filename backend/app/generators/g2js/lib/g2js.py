import subprocess
import os
import logging

logger = logging.getLogger(__name__)

class G2JSRunner:
    def __init__(self, executable_path, loader_source):
        self.exe = executable_path
        self.loader_source = loader_source

    def _to_wine_path(self, linux_path):
        # Assumes standard Wine configuration where / is mapped to Z:
        return "Z:" + linux_path.replace("/", "\\")

    def run(self, output_type, output_path_base):
        # We assume running in container/linux -> usage of wine
        # Convert paths to Wine format (Z:\...) because CSharpCodeProvider/StreamWriter inside Wine need Windows paths
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
        
        logger.info(f"Running external command: {' '.join(cmd)}")
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
