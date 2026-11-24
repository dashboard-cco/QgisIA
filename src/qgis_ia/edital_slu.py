# -*- coding: utf-8 -*-
"""
Regras do Anexo G do Edital SLU-DF (Pregão 90005/2026):
"Roteiro de Elaboração dos Planos de Serviço — Padrão de construção dos dados
geográficos vetoriais".

Só dados e funções puras (sem QGIS, sem GDAL), para poder ser testado sozinho.
As ações que gravam arquivos ficam em actions/slu.py.

Nomes de camadas, campos e domínios seguem os File Geodatabases-modelo do SLU
(CC01.gdb, CS01.gdb, VA01.gdb, VE01.gdb). O edital proíbe renomear as camadas.
"""
import calendar
import datetime as _dt
import re
import unicodedata

EPSG = 31983  # SIRGAS 2000 / UTM zona 23S (itens 4.6, 5.6 e 6.4)

# ---------------------------------------------------------------- serviços
# grupo: "coleta" (seção 4), "varricao" (seção 5), "demanda" (seção 6),
#        "sem_gdb" (P9, item 3.2)
SERVICOS = {
    "P1": {"nome": "Coleta Convencional", "sigla": "CC", "grupo": "coleta",
           "tipos_servico": {0: "porta a porta", 5: "ponto a ponto", 8: "mista"}},
    "P2": {"nome": "Coleta Seletiva", "sigla": "CS", "grupo": "coleta",
           "tipos_servico": {1: "porta a porta", 6: "ponto a ponto", 9: "mista"}},
    "P3": {"nome": "Coleta Manual de Entulho", "sigla": "MA", "grupo": "demanda", "codigo": 15},
    "P4": {"nome": "Coleta Mecanizada de Entulho", "sigla": "ME", "grupo": "demanda", "codigo": 16},
    "P5": {"nome": "Varrição Manual", "sigla": "VA", "grupo": "varricao", "codigo": 3},
    "P6": {"nome": "Varrição Mecanizada", "sigla": "VE", "grupo": "varricao", "codigo": 4},
    "P7": {"nome": "Lavagem de Vias e Logradouros Públicos", "sigla": "VL", "grupo": "demanda",
           "codigo": 17},
    "P8": {"nome": "Limpeza de Equipamentos e Bens Públicos", "sigla": "LE", "grupo": "demanda",
           "codigo": 18},
    "P9": {"nome": "Catação e Limpeza de Áreas Verdes", "sigla": None, "grupo": "sem_gdb"},
    "P10": {"nome": "Pintura Mecanizada de Meio-fio e Frisagem", "sigla": "FR", "grupo": "demanda",
            "codigo": 20},
    "P11": {"nome": "Limpeza Pré Eventos e Pós Eventos e Coleta de Resíduo de Caixa de Gordura",
            "sigla": "PE", "grupo": "demanda", "codigo": 21},
    "P12": {"nome": "Operação de Transbordos", "sigla": "TR", "grupo": "demanda", "codigo": 22},
}

SIGLA_PARA_SERVICO = {v["sigla"]: k for k, v in SERVICOS.items() if v["sigla"]}

# Serviços sob demanda: têm programação trimestral em .xlsx (seção 7)
SERVICOS_TRIMESTRAIS = ("P3", "P4", "P7", "P8", "P9", "P10", "P11", "P12")

# ------------------------------------------------------------------ domínios
RA = {
    1: "Plano Piloto", 2: "Gama", 3: "Taguatinga", 4: "Brazlândia", 5: "Sobradinho",
    6: "Planaltina", 7: "Paranoá", 8: "Núcleo Bandeirante", 9: "Ceilândia", 10: "Guará",
    11: "Cruzeiro", 12: "Samambaia", 13: "Santa Maria", 14: "São Sebastião",
    15: "Recanto das Emas", 16: "Lago Sul", 17: "Riacho Fundo", 18: "Lago Norte",
    19: "Candangolândia", 20: "Águas Claras", 21: "Riacho Fundo II",
    22: "Sudoeste e Octogonal", 23: "Varjão", 24: "Park Way", 25: "SCIA",
    26: "Sobradinho II", 27: "Jardim Botânico", 28: "Itapoã", 29: "SIA",
    30: "Vicente Pires", 31: "Fercal", 32: "Sol Nascente/Pôr do Sol", 33: "Arniqueira",
    # 34 e 35: camada oficial regioes_administrativas (ra_cira); ausentes no domínio antigo
    34: "Arapoanga", 35: "Água Quente",
}
RA_MIN, RA_MAX = 1, 35  # Tabela 1: "intervalo entre 1 e 35"

# Grafias usadas no edital (Quadro 01) que diferem do domínio do SLU; ambas aceitas.
RA_APELIDOS = {
    5: ["Sobradinho I"], 17: ["Riacho Fundo I"], 25: ["SCIA/Estrutural", "Estrutural"],
    22: ["Sudoeste/Octogonal"], 32: ["Pôr do Sol/Sol Nascente"],
}

# Edital, Termo de Referência, Quadro 01 (p. 27-28): RAs de cada lote.
# Confere com o campo Lote da camada Shp/regioes_administrativas.shp.
RA_POR_LOTE = {
    1: {1, 5, 6, 7, 11, 18, 22, 23, 26, 28, 31, 34},
    2: {3, 4, 9, 10, 20, 25, 29, 30, 32},
    3: {2, 8, 12, 13, 14, 15, 16, 17, 19, 21, 24, 27, 33, 35},
}

# Anexo R (Tabela de Quantidades de Mão de Obra e Equipamentos): veículos de coleta por
# lote e turno, com o código da Tabela 4 do Anexo G. P1 inclui os compactadores 19 m³
# c/ munk da coleta de semienterrado (P1A no Anexo R), usados nos circuitos mistos.
# P2: compactadores 15 m³ (porta a porta), 15 m³ c/ munk (LEVs) e 6 m³.
FROTA_ANEXO_R = {
    ("P1", 1): {0: {"Diurno": 32, "Noturno": 17}, 1: {"Diurno": 10, "Noturno": 0}},
    ("P1", 2): {0: {"Diurno": 30, "Noturno": 19}, 1: {"Diurno": 6, "Noturno": 0}},
    ("P1", 3): {0: {"Diurno": 37, "Noturno": 16}, 1: {"Diurno": 7, "Noturno": 0}},
    ("P2", 1): {2: {"Diurno": 6, "Noturno": 4}, 3: {"Diurno": 2, "Noturno": 0},
                14: {"Diurno": 1, "Noturno": 0}},
    ("P2", 2): {2: {"Diurno": 11, "Noturno": 6}, 3: {"Diurno": 1, "Noturno": 0},
                14: {"Diurno": 2, "Noturno": 0}},
    ("P2", 3): {2: {"Diurno": 9, "Noturno": 3}, 3: {"Diurno": 1, "Noturno": 0},
                14: {"Diurno": 1, "Noturno": 0}},
}

# Edital, item 7.8: textos em Word, Arial 12 no corpo e 14 nos títulos.
FONTE_DOCX = "Arial"
TAM_CORPO_PT, TAM_TITULO_PT = 12, 14

# Tabela 4 - Descrição de Equipamentos
EQUIPAMENTOS = {
    0: "Caminhão Coletor Compactador de 19 m³",
    1: "Caminhão Coletor Compactador de 19 m³ com expansor de compartimento e braço munk",
    2: "Caminhão Coletor Compactador de 15 m³",
    3: "Caminhão Coletor Compactador de 15 m³ com expansor de compartimento e braço munk",
    4: "Caminhão Coletor Baú de 30 m³",
    5: "Veículo moto triciclo",
    6: "Carrinho de varrição (Lutocar)",
    7: "Varredeira mecânica de baixo porte",
    8: "Varredeira mecânica de grande porte",
    9: "Caminhão Polinguindaste Duplo",
    10: "Caminhão Carroceria Aberta Fixa",
    11: "Caminhão Carroceria c/ Guindauto Hidráulico tipo \"Munk\"",
    12: "Caminhão Carroceria Basculante",
    13: "Caminhão Roll on Roll off",
    14: "Caminhão Coletor Compactador de 6 m³",
    15: "Carreta Cavalo Mecânico com Caçamba Metálica Basculante",
    16: "Veículo Leve",
    17: "Furgão",
    18: "Caminhão Basculante 6m³",
    19: "Caminhão Basculante 12m³",
    20: "Pá Carregadeira",
    21: "Ônibus",
    22: "Caminhão Pipa",
    23: "Furgão com Lavadora",
    24: "Caminhão Carroceria",
    25: "Trator c/ Máq. Pintura",
    26: "Carreta Basculante 55m³",
    27: "Carreta c/ Tanque 30.000/31.000 Litros",
    28: "Micro-ônibus",
    29: "Caminhão Tanque 8.000 Litros",
    30: "Motocicleta",
    31: "Caminhão Sucção a Vácuo e Hidrojato",
}
EQUIPAMENTOS_POR_GRUPO = {
    "coleta": {0, 1, 2, 3, 4, 5, 14},
    "varricao": {6, 7, 8},
}

TIPO_SERVICO_DESC = {
    0: "Coleta Convencional (Porta a Porta)", 1: "Coleta Seletiva (Porta a Porta)",
    3: "Varrição Manual", 4: "Varrição Mecanizada",
    5: "Coleta Convencional (Ponto a Ponto)", 6: "Coleta Seletiva (Ponto a Ponto)",
    8: "Coleta Convencional (Mista)", 9: "Coleta Seletiva (Mista)",
    15: "Coleta Manual de Entulho", 16: "Coleta Mecanizada de Entulho",
    17: "Lavagem de Vias e Logradouros Públicos",
    18: "Limpeza de Equipamentos e Bens Públicos",
    20: "Pintura Mecanizada de Meio-fio e Frisagem",
    21: "Limpeza Pré eventos e Pós eventos e Coletas de Resíduo de Caixa de Gordura",
    22: "Operação de Transbordos",
}

LOCAIS_DESTINACAO = [
    "UTMB Asa Sul", "UTMB P Sul", "Transbordo Gama", "Transbordo Brazlândia",
    "Transbordo Sobradinho", "Aterro Sanitário de Brasília - ASB", "IRR PSul",
    "IRR SCIA Alugado", "IRR SCIA Definitivo", "IRR SAAN", "IRR SIA B", "IRR Ceilândia",
    "Cooperativa CRV", "Cooperativa Catamares", "Cooperativa Cooperambiente", "IRR Paranoá",
    "IRR Sobradinho", "Centro de Comercialização", "Cooperativa ECOLIMPO", "Cooperativa R3",
]
LOCAIS_PESAGEM = [
    "UTMB Asa Sul", "UTMB P Sul", "Núcleo de Limpeza do Gama",
    "Núcleo de Limpeza de Sobradinho", "Transbordo Brazlândia",
    "Aterro Sanitário de Brasília - ASB", "Célula de Carga",
    "Unidade de Recebimento de Entulhos - URE", "Núcleo de Limpeza Norte",
]

CICLO = {0: "Padrão", 1: "Quinzenal", 2: "Mensal"}
SEMANA = {0: "Padrão Semanal", 1: "Semana 1", 2: "Semana 2", 3: "Semana 3", 4: "Semana 4"}
TURNOS = ("Diurno", "Noturno")


def dominios(servico, lote):
    """Domínios (listas de códigos) gravados no .gdb, no padrão dos modelos do SLU."""
    grupo = SERVICOS[servico]["grupo"]
    prefixo = lote_codigo(servico, lote)[:2]
    d = {
        "lote": ("Lista dos lotes", "str", {f"{prefixo}0{n}": f"{prefixo}0{n}" for n in (1, 2, 3)}),
        "cod_ra": ("Lista de Regiões Administrativas", "int", dict(RA)),
        "id_tipo_equipamento": ("Lista Tipos de Equipamentos", "int", dict(EQUIPAMENTOS)),
        "ciclo_": ("Padrão Quinzenal ou Mensal", "int", dict(CICLO)),
        "flag_semana": ("Semana de execução", "int", dict(SEMANA)),
    }
    if grupo == "coleta":
        d["id_tipo_servico"] = ("Lista dos Tipos de Serviços", "int",
                                {k: TIPO_SERVICO_DESC[k] for k in (0, 1, 5, 6, 8, 9)})
        d["Tipo_point"] = ("Ponto de Início ou Fim de um circuito", "int", {0: "Fim", 1: "Início"})
        d["Deslocamento"] = ("Via de Passagem ou Via de Coleta", "int",
                             {0: "Via de Coleta", 1: "Via de passagem"})
        d["local_destinacao"] = ("Local de Tratamento ou Destinação", "str",
                                 {v: v for v in LOCAIS_DESTINACAO})
        d["local_pesagem"] = ("Lista dos locais de pesagem", "str", {v: v for v in LOCAIS_PESAGEM})
    elif grupo == "varricao":
        d["id_tipo_servico"] = ("Lista dos codigos do tipo de serviço", "int",
                                {3: "Varrição Manual", 4: "Varrição Mecanizada"})
        d["tipo_pointo"] = ("Ponto de início ou fim de um circuito", "int", {0: "Fim", 1: "Início"})
        d["deslocamento"] = ("Via de varrição ou Via de Passagem", "int",
                             {0: "Via de varrição", 1: "Via de passagem"})
    else:
        d["id_tipo_servico"] = ("Lista dos codigos do tipo de serviço", "int",
                                {k: TIPO_SERVICO_DESC[k] for k in (15, 16, 17, 18, 20, 21, 22)})
    return d


# ------------------------------------------------------------------ esquema
# campo: (nome, tipo, tamanho, apelido, domínio)
# tipos: "str", "int" (32 bits), "int16", "real", "datetime"
def _f(nome, tipo, tamanho=0, apelido=None, dominio=None):
    return {"nome": nome, "tipo": tipo, "tamanho": tamanho, "apelido": apelido, "dominio": dominio}


_DIAS = [_f("segunda", "int16"), _f("terca", "int16", apelido="Terça"), _f("quarta", "int16"),
         _f("quinta", "int16"), _f("sexta", "int16"), _f("sabado", "int16", apelido="Sábado"),
         _f("domingo", "int16")]
DIAS_CAMPOS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
DIAS_NOMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIAS_SIGLA3 = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
DIAS_INICIAL = ["S", "T", "Q", "Q", "S", "S", "D"]


def esquema(servico, lote):
    """Camadas obrigatórias do .gdb: lista de {nome, geometria, campos}."""
    grupo = SERVICOS[servico]["grupo"]
    if grupo == "sem_gdb":
        return []
    tam_lote = 5 if grupo == "coleta" else 4
    tipo_pt = "Tipo_point" if grupo == "coleta" else "tipo_pointo"
    desl = "Deslocamento" if grupo == "coleta" else "deslocamento"
    base = [
        _f("lote", "str", tam_lote, None, "lote"),
        _f("codigo_circuito", "int", apelido="Código Circuito"),
        _f("codigo_ra", "int16", apelido="Código RA", dominio="cod_ra"),
    ]
    poligono = base + [
        _f("nome_circuito", "str", 255, "Nome Circuito"),
        _f("enderecamento", "str", 5000, "Endereçamento"),
        _f("horario_inicio", "datetime", apelido="Horário Início"),
        _f("horario_termino", "datetime", apelido="Horário Término"),
    ] + _DIAS + [
        _f("frequencia", "str", 70, "Frequência"),
        _f("id_tipo_servico", "int16", apelido="Tipo Serviço", dominio="id_tipo_servico"),
        _f("id_tipo_equipamento", "int16", apelido="Tipo Equipamento",
           dominio="id_tipo_equipamento"),
        _f("local_destinacao", "str", 255, "Local Destinação",
           "local_destinacao" if grupo == "coleta" else None),
        _f("ciclo", "int16", apelido="Ciclo", dominio="ciclo_"),
        _f("flag_semana", "int16", apelido="Semana", dominio="flag_semana"),
        _f("turno", "str", 20, "Turno"),
    ]
    if grupo == "coleta":
        poligono.insert(poligono.index(next(c for c in poligono if c["nome"] == "local_destinacao")),
                        _f("local_pesagem", "str", 255, "Local Pesagem", "local_pesagem"))
    if grupo == "demanda":
        poligono.append(_f("numero_equipes", "int16", apelido="Número de Equipes"))
        return [{"nome": "lm_area_circuito_planejado", "geometria": "MultiPolygon",
                 "campos": poligono}]

    pontos = base + [
        _f("endereco", "str", 255, "Endereço"),
        _f("horario", "datetime", apelido="Horário"),
        _f("turno", "str", 20, "Turno"),
        _f("tipo", "int16", apelido="Tipo", dominio=tipo_pt),
    ]
    linhas = base + [_f("deslocamento", "int16", apelido="Deslocamento", dominio=desl)]
    camadas = [
        {"nome": "st_circuito_inicio_fim", "geometria": "Point", "campos": pontos},
        {"nome": "st_circuito_planejado", "geometria": "MultiLineString", "campos": linhas},
    ]
    if grupo == "coleta":
        camadas.append({"nome": "st_conteiner", "geometria": "Point", "campos": base + [
            _f("codigo_conteiner", "int", apelido="Código Equipamento")]})
    else:
        camadas.append({"nome": "st_quantificacao", "geometria": "MultiLineString",
                        "campos": base + [_f("extensao_sarjeta", "real",
                                             apelido="Extensão da Sarjeta")]})
    camadas.append({"nome": "lm_area_circuito_planejado", "geometria": "MultiPolygon",
                    "campos": poligono})
    return camadas


# ----------------------------------------------------------- códigos/nomes
def normaliza_servico(servico):
    """Aceita 'P1', 'p1', '1', 'CC', 'coleta convencional'... e devolve 'P1'."""
    s = str(servico).strip().upper()
    if s in SERVICOS:
        return s
    if s.isdigit() and f"P{int(s)}" in SERVICOS:
        return f"P{int(s)}"
    if s[:2] in SIGLA_PARA_SERVICO and (len(s) == 2 or s[2:].isdigit()):
        return SIGLA_PARA_SERVICO[s[:2]]
    alvo = _sem_acento(s)
    for k, v in SERVICOS.items():
        if _sem_acento(v["nome"].upper()) == alvo:
            return k
    raise ValueError(f"Serviço desconhecido: {servico!r}. Use P1..P12 ou a sigla (CC, CS, VA...).")


def normaliza_lote(lote):
    n = int(str(lote).strip().upper().replace("LOTE", "").strip() or 0)
    if n not in (1, 2, 3):
        raise ValueError(f"Lote inválido: {lote!r}. Use 1, 2 ou 3.")
    return n


def lote_codigo(servico, lote):
    """Valor do campo 'lote' e nome do arquivo: sigla + lote com 2 dígitos (ex.: CC03)."""
    sigla = SERVICOS[servico]["sigla"]
    if not sigla:
        raise ValueError(f"{servico} não tem arquivo .gdb (item 3.2 do Anexo G).")
    return f"{sigla}{normaliza_lote(lote):02d}"


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def dias_ativos(valores):
    """valores: sequência de 7 itens (seg..dom), 0/1/None. Devolve índices ativos."""
    return [i for i, v in enumerate(valores) if v not in (None, 0, "0", False, "")]


def frequencia_texto(valores):
    """'Segunda e Quarta'; 'Terça, Quinta e Sábado' (Tabela 1, campo Frequência)."""
    nomes = [DIAS_NOMES[i] for i in dias_ativos(valores)]
    if not nomes:
        return ""
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def logica_circuito(valores, ciclo=0, grupo="coleta"):
    """Parte final do Nome do Circuito (D1, SSEG, A3SQS, A2TQ, MSEG, QTER)."""
    dias = dias_ativos(valores)
    n = len(dias)
    if n == 0:
        raise ValueError("Nenhum dia marcado (segunda..domingo).")
    ciclo = int(ciclo or 0)
    if ciclo in (1, 2):
        letra = "Q" if ciclo == 1 else "M"
        if n != 1:
            raise ValueError("Circuito quinzenal/mensal deve ocorrer em um dia específico.")
        return letra + DIAS_SIGLA3[dias[0]]
    if n >= 6:
        return "D1"
    if n == 1:
        return "S" + DIAS_SIGLA3[dias[0]]
    return f"A{n}" + "".join(DIAS_INICIAL[i] for i in dias)


def nome_circuito(servico, codigo_circuito, valores, ciclo=0, codigo_ra=None, lote=None,
                  nome_ra=None):
    """Monta o Nome do Circuito conforme a Tabela 1/2/3 do Anexo G."""
    grupo = SERVICOS[servico]["grupo"]
    logica = logica_circuito(valores, ciclo, grupo)
    if grupo == "demanda":
        return f"Lote {normaliza_lote(lote):02d} {int(codigo_circuito)} {logica}"
    prefixo = nome_ra or RA.get(int(codigo_ra)) if codigo_ra is not None else nome_ra
    if not prefixo:
        raise ValueError("Informe codigo_ra (ou nome_ra) para montar o nome do circuito.")
    return f"{prefixo} {int(codigo_circuito)} {logica}"


def tipo_servico_do_codigo(servico, codigo_circuito):
    """Extrai o tipo de serviço codificado no Código Circuito."""
    s = str(int(codigo_circuito))
    grupo = SERVICOS[servico]["grupo"]
    if grupo == "demanda":
        return int(s[1:3]) if len(s) == 5 else None
    return int(s[1]) if len(s) == 6 else None


def valida_codigo_circuito(servico, lote, codigo, tipo_servico=None):
    """Lista de problemas do Código Circuito (vazia = ok)."""
    erros = []
    if codigo in (None, ""):
        return ["Código Circuito vazio"]
    try:
        s = str(int(codigo))
    except (TypeError, ValueError):
        return [f"Código Circuito não numérico: {codigo!r}"]
    info = SERVICOS[servico]
    grupo = info["grupo"]
    tam = 5 if grupo == "demanda" else 6
    if len(s) != tam:
        return [f"Código Circuito {s} deve ter {tam} dígitos"]
    if lote is not None and s[0] != str(normaliza_lote(lote)):
        erros.append(f"Código Circuito {s}: 1º dígito deve ser o lote ({normaliza_lote(lote)})")
    if grupo == "coleta":
        if int(s[1]) not in info["tipos_servico"]:
            erros.append(f"Código Circuito {s}: 2º dígito deve ser "
                         f"{'/'.join(map(str, info['tipos_servico']))} para {info['nome']}")
        elif tipo_servico is not None and int(s[1]) != int(tipo_servico):
            erros.append(f"Código Circuito {s}: 2º dígito ({s[1]}) difere do Tipo de Serviço "
                         f"({tipo_servico})")
    elif grupo == "varricao":
        if int(s[1]) != info["codigo"]:
            erros.append(f"Código Circuito {s}: 2º dígito deve ser {info['codigo']} "
                         f"({info['nome']})")
    elif grupo == "demanda":
        if int(s[1:3]) != info["codigo"]:
            erros.append(f"Código Circuito {s}: 2º e 3º dígitos devem ser {info['codigo']}")
        if s[3:] not in ("01", "02"):
            erros.append(f"Código Circuito {s}: 2 últimos dígitos são o turno (01 Diurno, "
                         f"02 Noturno)")
    return erros


def codigo_circuito_demanda(servico, lote, turno):
    """Código de 5 dígitos dos serviços sob demanda (ex.: 11501)."""
    t = {"diurno": 1, "noturno": 2}[str(turno).strip().lower()]
    return int(f"{normaliza_lote(lote)}{SERVICOS[servico]['codigo']:02d}{t:02d}")


def valida_nome_circuito(servico, nome, codigo, valores, ciclo, codigo_ra=None, lote=None):
    """Compara o nome gravado com o nome esperado. Devolve (ok, esperado_ou_motivo)."""
    if not nome:
        return False, "Nome do Circuito vazio"
    try:
        logica = logica_circuito(valores, ciclo, SERVICOS[servico]["grupo"])
    except ValueError as e:
        return False, str(e)
    grupo = SERVICOS[servico]["grupo"]
    if grupo == "demanda":
        esperado = f"Lote {normaliza_lote(lote):02d} {int(codigo)} {logica}"
        return nome.strip() == esperado, esperado
    m = re.match(r"^(.+?) (\d{6}) ([A-Z0-9]+)$", nome.strip())
    if not m:
        return False, f"fora do padrão 'Nome RA' + código + lógica (ex.: 'Gama {codigo} {logica}')"
    nome_ra, cod, log = m.groups()
    if int(cod) != int(codigo):
        return False, f"código no nome ({cod}) difere do Código Circuito ({codigo})"
    if log != logica:
        return False, f"lógica '{log}' não confere com os dias/ciclo (esperado '{logica}')"
    if codigo_ra is not None:
        ra = int(codigo_ra)
        if ra == 1:
            if not (nome_ra.startswith("Asa Norte") or nome_ra.startswith("Asa Sul")):
                return False, "RA Plano Piloto: o nome deve começar por 'Asa Norte' ou 'Asa Sul'"
        elif ra in RA and _sem_acento(nome_ra).lower() not in {
                _sem_acento(n).lower() for n in [RA[ra]] + RA_APELIDOS.get(ra, [])}:
            return False, f"nome da RA '{nome_ra}' difere do Código RA {ra} ({RA[ra]})"
    return True, f"{nome_ra} {int(codigo)} {logica}"


# ------------------------------------------------- programação trimestral
def dias_do_trimestre(ano, trimestre):
    """Lista de semanas (segunda a domingo) com as datas do trimestre."""
    trimestre = int(trimestre)
    if trimestre not in (1, 2, 3, 4):
        raise ValueError("Trimestre deve ser 1, 2, 3 ou 4.")
    mes_ini = 3 * (trimestre - 1) + 1
    inicio = _dt.date(int(ano), mes_ini, 1)
    mes_fim = mes_ini + 2
    fim = _dt.date(int(ano), mes_fim, calendar.monthrange(int(ano), mes_fim)[1])
    semanas, atual, dia = [], [], inicio
    while dia <= fim:
        if dia.weekday() == 0 and atual:
            semanas.append(atual)
            atual = []
        atual.append(dia)
        dia += _dt.timedelta(days=1)
    if atual:
        semanas.append(atual)
    return semanas


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
TRIMESTRE_NOME = {1: "Primeiro", 2: "Segundo", 3: "Terceiro", 4: "Quarto"}


def rotulo_semana(datas):
    """'2 a 8 de junho de 2025' / '30 de junho a 6 de julho de 2025'."""
    a, b = datas[0], datas[-1]
    if a.month == b.month:
        return f"{a.day} a {b.day} de {MESES[b.month - 1]} de {b.year}"
    return f"{a.day} de {MESES[a.month - 1]} a {b.day} de {MESES[b.month - 1]} de {b.year}"


# ------------------------------------------------------------ texto (.docx)
# Item 3.1.1: conteúdo mínimo do texto descritivo de cada Plano de Serviço
SECOES_DOCX = [
    ("O que é o serviço", "Descrição do serviço e do escopo atendido no lote."),
    ("Tipo de material coletado", "Quando couber."),
    ("Local de origem e destinação final do material",
     "Origem do material e local de tratamento/destinação (Unidade de Transbordo, UTMB, IRR, "
     "Aterro etc.)."),
    ("Planejamento das rotas e frequências",
     "Como foram planejados os circuitos, rotas, frequências e turnos."),
    ("Veículos utilizados e placas", "Relação dos veículos com placas."),
    ("Tipos de caminhões utilizados", "Conforme a Tabela 4 do Anexo G."),
    ("Pessoal da operação", "Quantitativo e funções."),
    ("Horários", "Horários de início e término por turno."),
    ("Procedimentos operacionais", "Coleta/execução, pesagem e descarga do resíduo."),
    ("Equipe e contatos-chave",
     "Preposto, responsáveis pela operação e responsáveis pela construção do planejamento "
     "(nome, função, telefone, e-mail)."),
]
