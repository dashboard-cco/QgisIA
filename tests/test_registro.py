# -*- coding: utf-8 -*-
"""Toda ferramenta descrita em tool_specs existe no plugin, e vice-versa.

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests\\test_registro.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from qgis.core import QgsApplication  # noqa: E402

app = QgsApplication([], False)
app.initQgis()
sys.path.append(os.path.join(QgsApplication.prefixPath(), "python", "plugins"))

from qgis_ia import tool_specs, protocol  # noqa: E402
from qgis_ia.mcp_socket import build_funcs  # noqa: E402
from qgis_ia.executor import ACTIONS, DESTRUTIVAS  # noqa: E402

funcs = build_funcs()
falhas = []
sem_func = sorted(set(tool_specs.TOOLS) - set(funcs))
sem_spec = sorted(set(funcs) - set(tool_specs.TOOLS))
if sem_func:
    falhas.append(f"descritas sem implementação: {sem_func}")
if sem_spec:
    falhas.append(f"implementadas sem descrição para o MCP: {sem_spec}")
if not DESTRUTIVAS <= set(ACTIONS):
    falhas.append(f"DESTRUTIVAS fora do executor: {sorted(DESTRUTIVAS - set(ACTIONS))}")
if not (DESTRUTIVAS - {"rollback_edits"}) <= protocol.MUTATING | {"remove_layer"}:
    falhas.append("ação destrutiva fora do modo somente leitura")
for f in falhas:
    print("FALHOU:", f)
print("OK" if not falhas else f"{len(falhas)} FALHA(S)", f"({len(funcs)} ferramentas)")
app.exitQgis()
sys.exit(1 if falhas else 0)
