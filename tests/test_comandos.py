# -*- coding: utf-8 -*-
"""Testes do interpretador de comandos simples (sem QGIS, sem IA).

Regras: o comando vale para a camada SELECIONADA (ctx["ativa"]) e nomes de
campo vão entre aspas duplas.

    python tests\\test_comandos.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "qgis_ia"))

import comandos as C  # noqa: E402

CTX = {
    "camadas": ["lotes", "Vias Principais", "pontos_coleta", "Regiões"],
    "campos": {
        "lotes": ["id", "area", "bairro", "nome_rua", "uso"],
        "Vias Principais": ["ID", "nome", "comprimento"],
        "pontos_coleta": ["fid", "tipo", "endereco"],
        "Regiões": ["ra", "nome"],
    },
    "ativa": "lotes",
}

FALHAS = []


def _ctx(ativa):
    return dict(CTX, ativa=ativa)


def caso(frase, action, ativa="lotes", **params):
    try:
        p = C.interpretar(frase, _ctx(ativa))
    except C.ErroComando as e:
        FALHAS.append(f"{frase!r}: ErroComando {e}")
        return
    if p is None:
        FALHAS.append(f"{frase!r}: não reconhecido")
        return
    st = p["steps"][0]
    if st["action"] != action:
        FALHAS.append(f"{frase!r}: ação {st['action']} (esperava {action})")
        return
    for k, v in params.items():
        if st["params"].get(k) != v:
            FALHAS.append(f"{frase!r}: {k}={st['params'].get(k)!r} (esperava {v!r})")


def nada(frase):
    p = C.interpretar(frase, CTX)
    if p is not None:
        FALHAS.append(f"{frase!r}: devia ir para a IA, virou {p['steps']}")


def erro(frase, ativa="lotes", contem=None):
    try:
        p = C.interpretar(frase, _ctx(ativa))
        FALHAS.append(f"{frase!r}: devia dar erro, virou {p and p['steps']}")
    except C.ErroComando as e:
        if contem and contem.lower() not in str(e).lower():
            FALHAS.append(f"{frase!r}: erro sem '{contem}': {e}")


ASPAS = "entre aspas"
SELECIONE = "camada selecionada"

# --- regra 1: só a camada selecionada
caso("copiar camada", "duplicate_layer", layer_name="lotes")
caso("copiar a camada", "duplicate_layer", layer_name="lotes")
caso("copiar camada como lotes_backup", "duplicate_layer", layer_name="lotes", output_name="lotes_backup")
caso("Copie a camada Lotes como lotes_backup", "duplicate_layer", layer_name="lotes", output_name="lotes_backup")
caso("duplicar vias principais", "duplicate_layer", ativa="Vias Principais", layer_name="Vias Principais")
caso("copiar só as selecionadas", "duplicate_layer", layer_name="lotes", only_selected=True)
caso("renomear camada para lotes_2026", "rename_layer", layer_name="lotes", new_name="lotes_2026")
caso("remover camada", "remove_layer", layer_name="lotes")
caso("listar camadas", "list_layers")
caso("quantas camadas tem no projeto?", "list_layers")
erro("copiar camada Vias Principais", contem=SELECIONE)          # outra camada: selecione-a
erro("duplicar regioes", contem=SELECIONE)
erro("pintar Regiões de azul", contem=SELECIONE)
erro("zoom na camada regiões", contem=SELECIONE)
erro("copiar camada", ativa=None, contem="nenhuma camada selecionada")
erro('criar campo "x"', ativa=None, contem="nenhuma camada selecionada")
erro("copiar camada estradas")                                    # não existe

# --- regra 2: campos entre aspas
caso('criar campo "area_ha" tipo decimal', "add_field", layer_name="lotes", field_name="area_ha", field_type="Double")
caso('criar campo "RA"', "add_field", field_name="RA", field_type="String")
caso('adicione uma coluna "populacao" do tipo inteiro', "add_field", ativa="Regiões", layer_name="Regiões",
     field_name="populacao", field_type="Integer")
caso('criar campo "obs" texto com tamanho 100', "add_field", field_name="obs", length=100, field_type="String")
caso('criar campo "valor" com 2 casas decimais', "add_field", field_name="valor", field_type="Double", precision=2)
caso('criar campo "data de nascimento"', "add_field", field_name="data de nascimento")
caso('criar campo "vistoria" data', "add_field", field_name="vistoria", field_type="Date")
caso('criar novo campo "ativo" do tipo sim/não', "add_field", field_name="ativo", field_type="Boolean")
caso('criar campo “tipo_lote” inteiro', "add_field", field_name="tipo_lote", field_type="Integer")  # aspas do Word
erro("criar campo area_ha tipo decimal", contem=ASPAS)
erro("criar campo RA", contem=ASPAS)
caso('apagar campo "bairro"', "delete_field", layer_name="lotes", field_name="bairro")
caso('deletar o campo "nome"', "delete_field", ativa="Vias Principais", field_name="nome")
caso('excluir campos "uso" e "bairro"', "delete_field", field_name=["uso", "bairro"])
caso('apagar coluna "TIPO"', "delete_field", ativa="pontos_coleta", field_name="tipo")
erro("apagar campo bairro", contem=ASPAS)
erro('apagar campo "inexistente"', contem="não achei")
caso('renomear campo "nome_rua" para "logradouro"', "rename_field", field_name="nome_rua", new_name="logradouro")
erro("renomear campo nome_rua para logradouro", contem=ASPAS)
erro('renomear campo "nome_rua" para logradouro', contem=ASPAS)
caso("listar campos", "list_fields", layer_name="lotes")
caso("quais são os campos?", "list_fields", layer_name="lotes")
caso('calcular campo "area" com área em hectares', "calculate_field", field_name="area", expression="$area / 10000")
caso('calcular campo "area_m2" = $area', "calculate_field", field_name="area_m2", expression="$area",
     field_type="Double")
caso('preencher campo "uso" com residencial', "calculate_field", field_name="uso", expression="'residencial'")
caso('preencher campo "uso" com \'misto\' só nas selecionadas', "calculate_field", expression="'misto'",
     only_selected=True)
caso('preencher campo "id" com numeração', "calculate_field", field_name="id", expression="@row_number")
caso('preencher campo "nome_rua" com "bairro"', "calculate_field", expression='"bairro"')
erro("calcular campo area com área em hectares", contem=ASPAS)

# --- condições: campo entre aspas; area/comprimento sem aspas = geometria
caso('selecionar onde "area" maior que 1000', "select_features", layer_name="lotes", expression='"area" > 1000')
caso("selecionar onde area maior que 1000", "select_features", expression="$area > 1000")
caso('selecione as feições com "bairro" igual a Centro', "select_features", expression="\"bairro\" = 'Centro'")
caso('selecionar onde "tipo" vazio', "select_features", ativa="pontos_coleta", expression='"tipo" IS NULL')
caso('selecionar onde "area" entre 100 e 500', "select_features", expression='"area" BETWEEN 100 AND 500')
caso('selecionar onde "nome_rua" contém Avenida e "area" > 300', "select_features",
     expression="\"nome_rua\" ILIKE '%Avenida%' AND \"area\" > 300")
caso('selecionar onde "uso" diferente de comercial', "select_features", expression="\"uso\" <> 'comercial'")
caso('selecionar onde "uso" igual a "bairro"', "select_features", expression='"uso" = "bairro"')
erro("selecionar onde bairro igual a Centro", contem=ASPAS)
erro('selecionar onde "xyz" igual a 1', contem="não achei")
caso("selecionar tudo", "select_features", layer_name="lotes")
caso("limpar seleção", "clear_selection")
caso("inverter seleção", "invert_selection", layer_name="lotes")
caso("apagar feições selecionadas", "delete_selected_features", layer_name="lotes")
caso('apagar feições onde "area" menor que 1', "delete_features", layer_name="lotes", expression='"area" < 1')
caso("contar feições", "count_features", layer_name="lotes")
caso('quantas feições tem onde "uso" igual a residencial', "count_features", expression="\"uso\" = 'residencial'")

# --- edição
caso("editar camada", "start_editing", layer_name="lotes")
caso("iniciar edição", "start_editing", layer_name="lotes")
caso("editar", "start_editing", ativa="Vias Principais", layer_name="Vias Principais")
caso("salvar edição", "commit_edits")
caso("cancelar edição", "rollback_edits")
caso("desfazer", "undo_edit", layer_name="lotes", steps=1)
caso("desfazer 3 vezes", "undo_edit", steps=3)
caso("refazer", "redo_edit")
caso("o que está em edição?", "edit_status")

# --- filtro / navegação
caso('filtrar onde "bairro" igual a Centro', "filter_layer", expression="\"bairro\" = 'Centro'")
caso('mostrar só onde "area" maior ou igual a 500', "filter_layer", expression='"area" >= 500')
caso("limpar filtro", "clear_filter", layer_name="lotes")
caso("zoom na camada", "zoom_to_layer", layer_name="lotes")
caso("zoom na seleção", "zoom_to_selection")

# --- ditado por voz (Windows Win+H): "aspas" falado vira aspas; ponto final é ignorado
caso("Criar campo aspas área aspas tipo decimal.", "add_field", field_name="área", field_type="Double")
caso("apagar campo aspas bairro aspas", "delete_field", field_name="bairro")
caso("renomear campo aspas uso aspas para aspas uso_solo aspas", "rename_field", field_name="uso",
     new_name="uso_solo")
caso("Selecionar onde abre aspas bairro fecha aspas igual a Centro.", "select_features",
     expression="\"bairro\" = 'Centro'")

# --- cortesia
caso('por favor, apagar campo "uso"', "delete_field", field_name="uso")

# --- vai para a IA
nada("crie um buffer de 100 m nas vias")
nada("faça um mapa temático da população por RA")
nada("qual a média da área dos lotes?")
nada("apagar feições de lotes")

ajuda = C.interpretar("ajuda", CTX)
if not ajuda or not ajuda.get("ajuda"):
    FALHAS.append("ajuda sem exemplos")
# todo exemplo da ajuda funciona com a camada 'lotes' selecionada
for ex in C.exemplos():
    try:
        if C.interpretar(ex, CTX) is None:
            FALHAS.append(f"exemplo da ajuda não reconhecido: {ex!r}")
    except C.ErroComando as e:
        if ASPAS in str(e) or SELECIONE in str(e):
            FALHAS.append(f"exemplo da ajuda fora das regras: {ex!r} -> {e}")

# --- expressões avulsas
for txt, esperado in [
    ('"area" maior que 10', '"area" > 10'),
    ("area maior que 10", "$area > 10"),
    ('"area" > 10', '"area" > 10'),
    ("$area > 10", "$area > 10"),
    ('"bairro" é Centro ou "bairro" é Sul', "\"bairro\" = 'Centro' OR \"bairro\" = 'Sul'"),
    ('"uso" preenchido', '"uso" IS NOT NULL'),
    ('"nome_rua" começa com Rua', "\"nome_rua\" ILIKE 'Rua%'"),
    ('"area" <= 2,5', '"area" <= 2.5'),
    ('"bairro" igual a "Asa Sul e Norte"', "\"bairro\" = 'Asa Sul e Norte'"),
]:
    try:
        got = C.expressao(txt, CTX["campos"]["lotes"])
    except C.ErroComando as e:
        got = f"ErroComando: {e}"
    if got != esperado:
        FALHAS.append(f"expressao({txt!r}) = {got!r} (esperava {esperado!r})")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
