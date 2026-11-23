# -*- coding: utf-8 -*-
"""Testes do interpretador de comandos simples (sem QGIS, sem IA).

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


def caso(frase, action, **params):
    try:
        p = C.interpretar(frase, CTX)
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


def erro(frase):
    try:
        p = C.interpretar(frase, CTX)
        FALHAS.append(f"{frase!r}: devia dar erro, virou {p and p['steps']}")
    except C.ErroComando:
        pass


# camadas
caso("copiar camada lotes", "duplicate_layer", layer_name="lotes")
caso("Copie a camada Lotes como lotes_backup", "duplicate_layer", layer_name="lotes", output_name="lotes_backup")
caso("duplicar vias principais", "duplicate_layer", layer_name="Vias Principais")
caso("faça uma cópia da camada regioes", "duplicate_layer", layer_name="Regiões")
caso("copiar a camada", "duplicate_layer", layer_name="lotes")
caso("copiar lotes só as selecionadas", "duplicate_layer", layer_name="lotes", only_selected=True)
caso("renomear camada lotes para lotes_2026", "rename_layer", layer_name="lotes", new_name="lotes_2026")
caso("remover a camada pontos_coleta", "remove_layer", layer_name="pontos_coleta")
caso("listar camadas", "list_layers")
caso("quantas camadas tem no projeto?", "list_layers")
# campos
caso("criar campo area_ha tipo decimal na camada lotes", "add_field", layer_name="lotes", field_name="area_ha", field_type="Double")
caso("criar campo RA", "add_field", layer_name="lotes", field_name="RA", field_type="String")
caso("adicione uma coluna populacao do tipo inteiro em Regiões", "add_field", layer_name="Regiões", field_name="populacao", field_type="Integer")
caso("criar campo obs texto com tamanho 100 na camada pontos_coleta", "add_field", layer_name="pontos_coleta", field_name="obs", length=100, field_type="String")
caso("criar campo valor com 2 casas decimais", "add_field", field_name="valor", field_type="Double", precision=2)
caso("criar campo data de nascimento", "add_field", field_name="data_de_nascimento")
caso("criar campo vistoria data", "add_field", field_name="vistoria", field_type="Date")
caso("criar novo campo ativo do tipo sim/não", "add_field", field_name="ativo", field_type="Boolean")
caso("apagar campo bairro", "delete_field", layer_name="lotes", field_name="bairro")
caso("deletar o campo nome da camada Vias Principais", "delete_field", layer_name="Vias Principais", field_name="nome")
caso("excluir campos uso e bairro de lotes", "delete_field", layer_name="lotes", field_name=["uso", "bairro"])
caso("apagar coluna TIPO de pontos_coleta", "delete_field", layer_name="pontos_coleta", field_name="tipo")
caso("renomear campo nome_rua para logradouro", "rename_field", field_name="nome_rua", new_name="logradouro")
caso("renomear o campo nome para nome_ra na camada regiões", "rename_field", layer_name="Regiões", field_name="nome", new_name="nome_ra")
caso("listar campos", "list_fields", layer_name="lotes")
caso("quais são os campos de vias principais?", "list_fields", layer_name="Vias Principais")
caso("calcular campo area com área em hectares", "calculate_field", field_name="area", expression="$area / 10000")
caso("calcular campo area_m2 = $area na camada lotes", "calculate_field", layer_name="lotes", field_name="area_m2", expression="$area", field_type="Double")
caso("preencher campo uso com residencial", "calculate_field", field_name="uso", expression="'residencial'")
caso("preencher campo uso com 'misto' só nas selecionadas", "calculate_field", expression="'misto'", only_selected=True)
caso("calcular campo comprimento com comprimento em km na camada vias principais", "calculate_field",
     layer_name="Vias Principais", field_name="comprimento", expression="$length / 1000")
caso("preencher campo id com numeração", "calculate_field", field_name="id", expression="@row_number")
# seleção
caso("selecionar lotes onde area maior que 1000", "select_features", layer_name="lotes", expression='"area" > 1000')
caso("selecione as feições de lotes com bairro igual a Centro", "select_features", expression="\"bairro\" = 'Centro'")
caso("selecionar pontos_coleta onde tipo vazio", "select_features", layer_name="pontos_coleta", expression='"tipo" IS NULL')
caso("selecionar lotes onde area entre 100 e 500", "select_features", expression='"area" BETWEEN 100 AND 500')
caso("selecionar lotes onde nome_rua contém Avenida e area > 300", "select_features",
     expression="\"nome_rua\" ILIKE '%Avenida%' AND \"area\" > 300")
caso("selecionar tudo em lotes", "select_features", layer_name="lotes")
caso("selecionar todos os lotes onde uso diferente de comercial", "select_features", expression="\"uso\" <> 'comercial'")
caso("limpar seleção", "clear_selection")
caso("limpar a seleção de lotes", "clear_selection", layer_name="lotes")
caso("inverter seleção", "invert_selection", layer_name="lotes")
caso("apagar feições selecionadas", "delete_selected_features", layer_name="lotes")
caso("excluir as feições selecionadas da camada pontos_coleta", "delete_selected_features", layer_name="pontos_coleta")
caso("apagar feições de lotes onde area menor que 1", "delete_features", layer_name="lotes", expression='"area" < 1')
caso("contar feições de lotes", "count_features", layer_name="lotes")
caso("quantas feições tem lotes onde uso igual a residencial", "count_features", expression="\"uso\" = 'residencial'")
# edição
caso("editar camada lotes", "start_editing", layer_name="lotes")
caso("iniciar edição", "start_editing", layer_name="lotes")
caso("ligar a edição de vias principais", "start_editing", layer_name="Vias Principais")
caso("salvar edição", "commit_edits")
caso("salvar as alterações de lotes", "commit_edits", layer_name="lotes")
caso("cancelar edição", "rollback_edits")
caso("desfazer", "undo_edit", layer_name="lotes", steps=1)
caso("desfazer 3 vezes", "undo_edit", steps=3)
caso("refazer", "redo_edit")
caso("o que está em edição?", "edit_status")
# filtro / navegação
caso("filtrar lotes onde bairro igual a Centro", "filter_layer", expression="\"bairro\" = 'Centro'")
caso("mostrar só lotes onde area maior ou igual a 500", "filter_layer", expression='"area" >= 500')
caso("limpar filtro de lotes", "clear_filter", layer_name="lotes")
caso("zoom na camada regiões", "zoom_to_layer", layer_name="Regiões")
caso("aproximar de pontos_coleta", "zoom_to_layer", layer_name="pontos_coleta")
caso("zoom na seleção", "zoom_to_selection")
# cortesia
caso("por favor, apagar campo uso", "delete_field", field_name="uso")
# vai para a IA
nada("crie um buffer de 100 m nas vias")
nada("faça um mapa temático da população por RA")
nada("qual a média da área dos lotes?")
nada("apagar feições de lotes")
# reconhece mas avisa
erro("apagar campo inexistente")
erro("copiar camada estradas")
erro("zoom na camada xyz")

ajuda = C.interpretar("ajuda", CTX)
if not ajuda or not ajuda.get("ajuda"):
    FALHAS.append("ajuda sem exemplos")
# todo exemplo da ajuda precisa ser reconhecido (ErroComando = reconheceu, só falta o nome no CTX)
for ex in C.exemplos():
    try:
        if C.interpretar(ex, CTX) is None:
            FALHAS.append(f"exemplo da ajuda não reconhecido: {ex!r}")
    except C.ErroComando:
        pass

# expressões avulsas
for txt, esperado in [
    ("area maior que 10", '"area" > 10'),
    ('"area" > 10', '"area" > 10'),
    ("$area > 10", "$area > 10"),
    ("bairro é Centro ou bairro é Sul", "\"bairro\" = 'Centro' OR \"bairro\" = 'Sul'"),
    ("uso preenchido", '"uso" IS NOT NULL'),
    ("nome_rua começa com Rua", "\"nome_rua\" ILIKE 'Rua%'"),
    ("area <= 2,5", '"area" <= 2.5'),
]:
    got = C.expressao(txt, CTX["campos"]["lotes"])
    if got != esperado:
        FALHAS.append(f"expressao({txt!r}) = {got!r} (esperava {esperado!r})")

for f in FALHAS:
    print("FALHOU:", f)
print("OK" if not FALHAS else f"{len(FALHAS)} FALHA(S)")
sys.exit(1 if FALHAS else 0)
