# -*- coding: utf-8 -*-
"""
Actions: code - Execução de PyQGIS arbitrário.

Equivale ao console Python do QGIS e à ferramenta de código do QGIS MCP.
Fica DESLIGADA por padrão: o painel QGIS_IA tem uma caixa para habilitar.
Com ela ligada, quem estiver conectado pode fazer qualquer coisa que o QGIS
faz, inclusive ler e apagar arquivos. Ligue só quando precisar.
"""
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr

MAX_OUTPUT = 100_000


def execute_code(code, return_variable=None):
    """
    Executa código PyQGIS no QGIS e devolve o que foi impresso.

    O código roda com 'iface', 'QgsProject', 'processing' e os módulos usuais
    já disponíveis. Use print() para devolver informação, ou informe
    'return_variable' com o nome de uma variável definida pelo código.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Informe 'code' com o código Python a executar.")

    from qgis import core, gui, utils
    import processing as processing_module

    namespace = {
        "__name__": "__qgis_ia__",
        "iface": utils.iface,
        "qgis": __import__("qgis"),
        "core": core,
        "gui": gui,
        "processing": processing_module,
    }
    for name in dir(core):
        if name.startswith("Qgs"):
            namespace[name] = getattr(core, name)

    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(compile(code, "<qgis_ia>", "exec"), namespace)
    except Exception:
        out = stdout.getvalue()
        raise RuntimeError(
            "Erro ao executar o código:\n" + traceback.format_exc()
            + ("\n--- saída antes do erro ---\n" + out if out else "")
        )

    result = {
        "success": True,
        "stdout": stdout.getvalue()[:MAX_OUTPUT],
        "stderr": stderr.getvalue()[:MAX_OUTPUT],
    }
    if return_variable:
        if return_variable not in namespace:
            raise ValueError(
                f"A variável '{return_variable}' não foi definida pelo código.")
        value = namespace[return_variable]
        result["value"] = value if isinstance(
            value, (str, int, float, bool, type(None), list, dict)) else str(value)
    return result


TOOLS = {"execute_code": execute_code}
