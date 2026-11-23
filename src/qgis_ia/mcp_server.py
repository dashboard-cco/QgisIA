#!/usr/bin/env python3
"""
Ponte MCP (stdio) do QGIS_IA.

Roda FORA do QGIS, iniciada pelo Claude Desktop / Claude Code:

    python "C:\\caminho\\para\\qgis_ia\\mcp_server.py"

Fala MCP (JSON-RPC 2.0 sobre stdin/stdout) usando SÓ a biblioteca padrão do
Python 3.8+. Não precisa de uv, pip, nem do pacote 'mcp': qualquer Python
instalado serve, inclusive o que vem dentro do QGIS.

Cada ferramenta é repassada ao servidor socket do plugin, dentro do QGIS.
Antes de usar, abra o QGIS e clique em "Iniciar servidor" no painel QGIS_IA.

Regra de ouro deste arquivo: stdout é só do protocolo. Qualquer mensagem
para humano vai em stderr.
"""
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol  # noqa: E402
from tool_specs import TOOLS  # noqa: E402

SERVER_NAME = "qgis-ia"
SERVER_VERSION = "2.0.0"

# Versões do protocolo MCP que sabemos falar (mais nova primeiro).
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

CALL_TIMEOUT = 600  # geoprocessamento pode demorar
_next_id = 0


def log(msg):
    print(f"[qgis-ia] {msg}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------- QGIS
def call_qgis(tool, params):
    """Envia um pedido ao QGIS; devolve 'result' ou levanta RuntimeError."""
    global _next_id
    host, port, token = protocol.read_config()
    _next_id += 1
    payload = {"id": _next_id, "token": token, "tool": tool, "params": params or {}}
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.settimeout(CALL_TIMEOUT)
            sock.sendall(data)
            chunks = []
            while True:
                chunk = sock.recv(1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunk.endswith(b"\n"):
                    break
    except OSError as e:
        raise RuntimeError(
            f"Nao consegui falar com o QGIS ({e}). Verifique se o QGIS esta aberto "
            "e se o servidor foi iniciado no painel QGIS_IA."
        )

    raw = b"".join(chunks).decode("utf-8", "replace").strip()
    if not raw:
        raise RuntimeError("O QGIS fechou a conexao sem responder.")
    resp = json.loads(raw)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "Erro desconhecido no QGIS."))
    return resp.get("result")


def tool_content(name, result):
    """Converte o resultado do QGIS em blocos de conteúdo MCP."""
    if name == "render_map" and isinstance(result, dict) and result.get("data_base64"):
        return [
            {"type": "image", "data": result["data_base64"],
             "mimeType": result.get("mime", "image/png")},
            {"type": "text",
             "text": f"Mapa renderizado: {result.get('width')}x{result.get('height')} px"},
        ]
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return [{"type": "text", "text": text}]


# ------------------------------------------------------------ JSON-RPC
def negotiate_version(requested):
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def handle_initialize(params):
    version = negotiate_version((params or {}).get("protocolVersion"))
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "Ferramentas do QGIS aberto no computador do usuario. "
            "Antes de montar expressoes ou filtros, chame get_layer_info para ver "
            "os campos e o CRS reais. Use list_algorithms + get_algorithm_help para "
            "qualquer operacao sem ferramenta dedicada, e render_map para conferir o "
            "resultado visualmente."
        ),
    }


def handle_tools_list():
    return {"tools": [
        {"name": name, "description": desc, "inputSchema": schema}
        for name, (desc, schema) in TOOLS.items()
    ]}


def handle_tools_call(params):
    params = params or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Ferramenta desconhecida: {name}"}],
                "isError": True}
    try:
        result = call_qgis(name, arguments)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True}
    return {"content": tool_content(name, result), "isError": False}


def dispatch(method, params):
    """Devolve (result, error). error é None em caso de sucesso."""
    if method == "initialize":
        return handle_initialize(params), None
    if method == "tools/list":
        return handle_tools_list(), None
    if method == "tools/call":
        return handle_tools_call(params), None
    if method == "ping":
        return {}, None
    if method in ("resources/list", "prompts/list"):
        # Alguns clientes perguntam mesmo sem a capability anunciada.
        return ({"resources": []} if method.startswith("resources") else {"prompts": []}), None
    return None, {"code": -32601, "message": f"Metodo nao suportado: {method}"}


def serve(stdin, stdout):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "JSON invalido"}}) + "\n")
            stdout.flush()
            continue

        if isinstance(msg, list):  # batch
            responses = []
            for item in msg:
                r = process(item)
                if r is not None:
                    responses.append(r)
            if responses:
                stdout.write(json.dumps(responses, ensure_ascii=False, default=str) + "\n")
                stdout.flush()
            continue

        response = process(msg)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            stdout.flush()


def process(msg):
    """Processa uma mensagem. Devolve o dict de resposta, ou None para notificações."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Pedido invalido"}}

    msg_id = msg.get("id")
    method = msg.get("method")

    # Sem 'method' é uma resposta do cliente (não esperamos nenhuma): ignora.
    if method is None:
        return None

    is_notification = "id" not in msg
    try:
        result, error = dispatch(method, msg.get("params"))
    except Exception as e:  # nunca derruba a ponte
        log(f"erro interno em {method}: {type(e).__name__}: {e}")
        result, error = None, {"code": -32603, "message": f"Erro interno: {e}"}

    if is_notification:
        return None
    if error is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": error}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def main():
    log(f"ponte iniciada ({len(TOOLS)} ferramentas)")
    try:
        serve(sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        pass
    log("ponte encerrada")


if __name__ == "__main__":
    main()
