# -*- coding: utf-8 -*-
"""Instala o QgisIA em desenvolvimento como um plugin separado: "QGIS_IA dev".

    python instalar_dev.py

Copia src/qgis_ia para <perfil QGIS>/python/plugins/qgis_ia_dev e ajusta, SÓ NA
CÓPIA, tudo o que colidiria com o plugin QGIS_IA já instalado (App_Qgis):
nome no menu/painel, pasta de configuração do servidor MCP, porta, variáveis de
ambiente e nome do servidor no Claude Code. Os dois funcionam ao mesmo tempo.
Rode de novo depois de cada mudança e reinicie o QGIS (ou recarregue o plugin).
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(AQUI, "src", "qgis_ia")
PERFIL = os.environ.get("QGIS_PERFIL", "default")
DESTINO = os.path.join(os.environ["APPDATA"], "QGIS", "QGIS3", "profiles", PERFIL,
                       "python", "plugins", "qgis_ia_dev")

TROCAS = {
    "metadata.txt": [
        ("name=QGIS_IA", "name=QGIS_IA dev"),
        ("description=", "description=[DESENVOLVIMENTO] "),
    ],
    "__init__.py": [
        ('"&QGIS_IA"', '"&QGIS_IA dev"'),
        ('"QGIS_IA"', '"QGIS_IA dev"'),
    ],
    "dockwidget.py": [
        ('"QGIS_IA — confirmar"', '"QGIS_IA dev — confirmar"'),
        ("<b>QGIS_IA</b>", "<b>QGIS_IA dev</b>"),
        ('"QGIS_IA"', '"QGIS_IA dev"'),
        ("qgis-ia", "qgis-ia-dev"),
    ],
    "protocol.py": [
        ('CONFIG_DIRNAME = ".qgis_ia"', 'CONFIG_DIRNAME = ".qgis_ia_dev"'),
        ('"QGIS_IA_HOST"', '"QGIS_IA_DEV_HOST"'),
        ('"QGIS_IA_PORT"', '"QGIS_IA_DEV_PORT"'),
        ('"QGIS_IA_TOKEN"', '"QGIS_IA_DEV_TOKEN"'),
    ],
    "mcp_socket.py": [
        ("DEFAULT_PORT = 9876", "DEFAULT_PORT = 9886"),
    ],
}


def versao():
    try:
        h = subprocess.run(["git", "-C", AQUI, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        h = ""
    return f"-dev.{h}" if h else "-dev"


def main():
    if not os.path.isdir(ORIGEM):
        sys.exit(f"Não achei o código em {ORIGEM}")
    if os.path.isdir(DESTINO):
        shutil.rmtree(DESTINO)
    shutil.copytree(ORIGEM, DESTINO, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for arquivo, trocas in TROCAS.items():
        caminho = os.path.join(DESTINO, arquivo)
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
        for antes, depois in trocas:
            if antes not in texto:
                sys.exit(f"ERRO: '{antes}' não está em {arquivo}; ajuste instalar_dev.py.")
            texto = texto.replace(antes, depois)
        if arquivo == "metadata.txt":
            linhas = [l + versao() if l.startswith("version=") else l for l in texto.splitlines()]
            texto = "\n".join(linhas) + "\n"
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto)
    print(f"Instalado em {DESTINO}")
    print("No QGIS: Complementos > Gerenciar e instalar > Instalados > marque 'QGIS_IA dev'.")
    print("Se não aparecer, feche e abra o QGIS.")


if __name__ == "__main__":
    main()
