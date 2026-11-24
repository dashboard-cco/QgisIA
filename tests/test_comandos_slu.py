# -*- coding: utf-8 -*-
"""Frases dos Planos de Serviço SLU-DF (Anexo G) e de preparo de linhas no
interpretador (sem QGIS, sem IA).

    python tests\\test_comandos_slu.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "qgis_ia"))

import comandos as C  # noqa: E402

GDB = "E:\\planos\\CC01.gdb"
CTX = {
    "camadas": ["Coleta_Linha", "Coleta_Poligono", "Limites dos Lotes", "vias", "lotes"],
    "campos": {"Coleta_Linha": ["lote", "codigo_circuito", "codigo_ra", "deslocamento"],
               "Coleta_Poligono": ["codigo_circuito", "codigo_ra"],
               "Limites dos Lotes": ["Código_RA", "nome"], "vias": ["nome"], "lotes": ["id"]},
    "ativa": "Coleta_Linha",
    "layouts": [],
    "fonte_ativa": GDB + "|layername=Coleta_Linha",
    "pasta_projeto": "E:\\projeto",
}
FALHAS = []


def caso(frase, action, ativa="Coleta_Linha", fonte=None, **params):
    ctx = dict(CTX, ativa=ativa)
    if fonte is not None:
        ctx["fonte_ativa"] = fonte
    try:
        p = C.interpretar(frase, ctx)
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: ErroComando {e}")
        return
    if p is None:
        FALHAS.append(f"{frase!r}: não reconhecido")
        return
    st = p["steps"][0]
    if st["action"] != action:
        FALHAS.append(f"{frase!r}: ação {st['action']} (esperava {action}) {st['params']}")
        return
    for k, v in params.items():
        if st["params"].get(k) != v:
            FALHAS.append(f"{frase!r}: {k}={st['params'].get(k)!r} (esperava {v!r})")


def erro(frase, contem="", ativa="Coleta_Linha", fonte=None):
    ctx = dict(CTX, ativa=ativa)
    if fonte is not None:
        ctx["fonte_ativa"] = fonte
    try:
        p = C.interpretar(frase, ctx)
    except C.ErroComando as e:
        if contem and contem not in str(e):
            FALHAS.append(f"{frase!r}: erro sem '{contem}': {e}")
        return
    FALHAS.append(f"{frase!r}: devia dar erro, deu {p and p['steps'][0]['action']}")


# criar o .gdb modelo
caso("criar gdb da coleta convencional lote 1", "slu_criar_gdb", servico="P1", lote=1, pasta_saida="E:\\projeto")
caso("criar gdb CC02", "slu_criar_gdb", servico="P1", lote=2)
caso("criar o gdb da varrição manual lote III em C:\\planos", "slu_criar_gdb", servico="P5", lote=3,
     pasta_saida="C:\\planos")
caso("gerar gdb P10 lote 2", "slu_criar_gdb", servico="P10", lote=2)
caso("criar gdb da coleta seletiva lote 01", "slu_criar_gdb", servico="P2", lote=1)
caso("criar gdb de transbordo lote 1", "slu_criar_gdb", servico="P12")
erro("criar gdb da catação lote 1", contem="não tem .gdb")
erro("criar gdb da coleta convencional", contem="lote")
erro("criar gdb lote 1", contem="serviço")

# plano completo
caso("gerar plano da coleta convencional lote 1", "slu_gerar_plano", servico="P1", lote=1)
caso("gerar plano", "slu_gerar_plano", servico="P1", lote=1, gdb_existente=GDB, pasta_saida="E:\\planos")
caso("gerar plano P10 lote 2 do 2º trimestre de 2026", "slu_gerar_plano", servico="P10", trimestre=2, ano=2026)
caso("gerar plano de serviço da varrição manual lote 3 empresa Valor Ambiental", "slu_gerar_plano",
     empresa="Valor Ambiental")
erro("gerar plano", fonte="E:\\x\\lotes.shp", ativa="lotes", contem="serviço")

# conferir / preencher / exportar (o .gdb é o da camada selecionada)
caso("validar plano", "slu_validar_gdb", gdb_path=GDB, carregar_erros=True)
caso("verificar o gdb", "slu_validar_gdb", gdb_path=GDB)
caso("conferir topologia", "slu_validar_gdb")
caso("validar plano com relatório", "slu_validar_gdb", relatorio_xlsx="E:\\planos\\CC01_relatorio.xlsx")
caso("validar plano C:\\outros\\VA02.gdb", "slu_validar_gdb", gdb_path="C:\\outros\\VA02.gdb")
erro("validar plano", ativa="lotes", fonte="E:\\x\\lotes.shp", contem="Selecione no painel")
caso("preencher atributos do plano", "slu_preencher_atributos", gdb_path=GDB, sobrescrever=False)
caso("preencher o plano", "slu_preencher_atributos")
caso("completar os campos do plano sobrescrevendo", "slu_preencher_atributos", sobrescrever=True)
caso("exportar tabela do plano", "slu_exportar_xlsx", saida_xlsx="E:\\planos\\CC01_tabela_atributos.xlsx")
caso("gerar planilha do plano em excel", "slu_exportar_xlsx")
caso("exportar plano em shapefile", "slu_exportar_shapefile", pasta_saida="E:\\planos")
caso("gerar planilha de soltura", "slu_planilha_soltura", dois_turnos=True,
     saida_xlsx="E:\\planos\\CC01_soltura.xlsx")
caso("soltura com um turno", "slu_planilha_soltura", dois_turnos=False)

# programação trimestral / texto
caso("gerar programação trimestral da pintura de meio-fio lote 1 do 2º trimestre de 2026",
     "slu_gerar_programacao_trimestral", servico="P10", lote=1, trimestre=2, ano=2026,
     saida_xlsx="E:\\projeto\\FR01_programacao_2026_T2.xlsx")
caso("programação P3 lote 2 terceiro trimestre 2026", "slu_gerar_programacao_trimestral", servico="P3", trimestre=3)
caso("programação trimestral da catação lote 1 T1 2026", "slu_gerar_programacao_trimestral", servico="P9")
erro("programação trimestral da coleta convencional lote 1 do 1º trimestre", contem="não tem programação")
erro("programação trimestral P10 lote 1", contem="trimestre")
caso("gerar texto do plano", "slu_gerar_docx", servico="P1", lote=1, gdb_path=GDB)
caso("gerar docx da varrição mecanizada lote 2", "slu_gerar_docx", servico="P6", lote=2)

# regras / RA
caso("regras do edital", "slu_info_edital")
caso("regras do edital para P5", "slu_info_edital", servico="P5")
caso("o que o edital pede para a coleta seletiva?", "slu_info_edital", servico="P2")
caso("copiar camada com RA pela camada Limites dos Lotes", "duplicar_camada_com_ra",
     layer_name="Coleta_Linha", ra_layer="Limites dos Lotes")
caso("duplicar com RA", "duplicar_camada_com_ra")

# preparo das linhas e atributos (genéricos)
caso("dividir linhas a cada 100 m", "geoprocess", tool="split_length", distance=100.0)
caso("quebrar as linhas em trechos de 130 metros", "geoprocess", tool="split_length", distance=130.0)
caso("dividir linhas nos cruzamentos", "geoprocess", tool="split_lines")
caso("dividir nas interseções com vias", "geoprocess", tool="split_lines", overlay="vias")
caso("encaixar nas linhas de vias", "geoprocess", tool="snap", overlay="vias")
caso("encaixar na camada vias com tolerância de 2 m", "geoprocess", tool="snap", overlay="vias", distance=2.0)
caso('preencher "codigo_ra" pela camada Limites dos Lotes campo "Código_RA"', "fill_field_by_location",
     field="codigo_ra", overlay="Limites dos Lotes", overlay_field="Código_RA")
caso('preencher campo "codigo_ra" pela camada Limites dos Lotes', "fill_field_by_location", field="codigo_ra")
erro("preencher codigo_ra pela camada Limites dos Lotes", contem="entre aspas")
erro('preencher "xyz" pela camada Limites dos Lotes', contem="xyz")
caso("exportar camada em gdb", "save_layer_as", format="gdb")
caso("salvar camada em C:\\planos\\CC01.gdb", "save_layer_as", output_path="C:\\planos\\CC01.gdb")

# o que já existia continua igual
caso('criar campo "RA"', "add_field")
caso('calcular campo "x" com área', "calculate_field", ativa="Coleta_Poligono")
caso("salvar projeto", "save_project")
caso("criar camada de pontos chamada postes", "create_layer")
caso("recortar pela camada vias", "geoprocess", tool="clip")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
