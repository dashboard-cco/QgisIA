# -*- coding: utf-8 -*-
"""
Protocolo entre a ponte MCP (fora do QGIS) e o servidor socket (dentro do QGIS).

Sem dependências do QGIS, para poder ser usado pelos dois lados e testado sozinho.

Formato: uma linha JSON (UTF-8) por mensagem.
  pedido:   {"id": 1, "token": "...", "tool": "list_layers", "params": {}}
  resposta: {"id": 1, "ok": true, "result": ...}
            {"id": 1, "ok": false, "error": "..."}
"""
import hmac
import json
import os
import traceback

# Ferramentas que gravam arquivos, alteram dados ou removem coisas.
# O "modo somente leitura" do painel bloqueia todas elas.
MUTATING = frozenset({
    # gravam arquivo, alteram dados ou removem coisas do projeto
    "remove_layer", "export_layer", "calculate_field", "run_algorithm",
    "export_layout_pdf", "export_layout_image", "save_project",
    "add_features", "update_features", "delete_features",
    "add_field", "delete_field", "rename_field", "delete_selected_features",
    "commit_edits", "rollback_edits", "undo_edit", "redo_edit",
    "export_layout", "export_map_image", "remove_layout", "save_layer_as",
    "save_layer_to_project", "create_layer", "load_files", "create_group", "move_layer_to_group",
    "set_layer_crs", "copy_style",
})

# Execução de Python arbitrário: tem uma chave própria no painel, separada do
# modo somente leitura, e começa desligada.
CODE_TOOLS = frozenset({"execute_code"})

CONFIG_DIRNAME = ".qgis_ia"
CONFIG_FILENAME = "server.json"


def config_path():
    return os.path.join(os.path.expanduser("~"), CONFIG_DIRNAME, CONFIG_FILENAME)


def write_config(host, port, token):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"host": host, "port": port, "token": token}, f)
    return path


def remove_config():
    try:
        os.remove(config_path())
    except OSError:
        pass


def read_config():
    """Lê host/port/token. Variáveis de ambiente têm prioridade."""
    cfg = {}
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    host = os.environ.get("QGIS_IA_HOST") or cfg.get("host")
    port = os.environ.get("QGIS_IA_PORT") or cfg.get("port")
    token = os.environ.get("QGIS_IA_TOKEN") or cfg.get("token")
    if not (host and port and token):
        raise RuntimeError(
            "Servidor não iniciado no QGIS. Abra o painel QGIS_IA "
            "e clique em 'Iniciar servidor'."
        )
    return host, int(port), token


def handle_request(line, funcs, token, read_only=False, allow_code=False):
    """Processa uma linha de pedido e devolve o dict de resposta."""
    try:
        req = json.loads(line)
        if not isinstance(req, dict):
            raise ValueError("pedido não é um objeto JSON")
    except ValueError as e:
        return {"id": None, "ok": False, "error": f"JSON inválido: {e}"}

    rid = req.get("id")
    tool = req.get("tool")

    if not hmac.compare_digest(str(req.get("token", "")), str(token)):
        return {"id": rid, "tool": tool, "ok": False, "error": "Token inválido."}

    if tool not in funcs:
        return {"id": rid, "tool": tool, "ok": False,
                "error": f"Ferramenta desconhecida: {tool}"}

    if tool in CODE_TOOLS and not allow_code:
        return {"id": rid, "tool": tool, "ok": False,
                "error": f"'{tool}' desligada. Para habilitar, marque "
                         "'Permitir execução de código Python' no painel QGIS_IA."}

    if read_only and (tool in MUTATING or tool in CODE_TOOLS):
        return {"id": rid, "tool": tool, "ok": False,
                "error": f"'{tool}' bloqueada: o servidor está em modo somente leitura."}

    params = req.get("params") or {}
    if not isinstance(params, dict):
        return {"id": rid, "tool": tool, "ok": False,
                "error": "'params' deve ser um objeto."}

    try:
        result = funcs[tool](**params)
        return {"id": rid, "tool": tool, "ok": True, "result": result}
    except Exception as e:
        return {"id": rid, "tool": tool, "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()}


def encode(resp):
    return (json.dumps(resp, ensure_ascii=False, default=str) + "\n").encode("utf-8")
