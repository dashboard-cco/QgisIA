# -*- coding: utf-8 -*-
"""
Comandos simples em português, interpretados SEM IA.

    interpretar('criar campo "area" tipo decimal', ctx)
    -> {"descricao": "Criar o campo 'area' (Decimal) na camada 'lotes'",
        "steps": [{"action": "add_field", "params": {...}}],
        "destrutivo": False}

Vantagens sobre mandar tudo para a IA: resposta instantânea, sem custo, funciona
sem internet e faz sempre a mesma coisa para a mesma frase. O que não casar com
nenhum comando (devolve None) segue para a IA.

ctx = {"camadas": [nomes], "campos": {camada: [campos]}, "ativa": nome ou None,
       "layouts": [nomes dos layouts de impressão]}

REGRAS (pedido do usuário, 2026-11-24):
  1. Os comandos valem só para a CAMADA SELECIONADA no painel de camadas
     (ctx["ativa"]). Não precisa dizer a camada; citar outra camada dá erro.
  2. Nome de campo/coluna vai SEMPRE entre aspas duplas: criar campo "area".
     Sem aspas: "Edição de campos: escreva o nome do campo entre aspas".
     Em condições, area/comprimento sem aspas = medida da geometria.

Sem dependências do QGIS, para poder ser testado sozinho.
"""
import os
import re
import unicodedata


class ErroComando(ValueError):
    """Frase reconhecida, mas com camada/campo que não existe ou ambíguo."""


# --------------------------------------------------------------------- texto
def sem_acento(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


_VAR = {"a": "[aáàâã]", "e": "[eéê]", "i": "[ií]", "o": "[oóôõ]", "u": "[uúü]", "c": "[cç]"}


def _k(palavra):
    """Padrão de uma palavra-chave que aceita com ou sem acento."""
    out = []
    for ch in sem_acento(palavra):
        if ch == " ":
            out.append(r"\s+")
        else:
            out.append(_VAR.get(ch, re.escape(ch)))
    return "".join(out)


def _alt(*palavras):
    ps = sorted(palavras, key=len, reverse=True)
    return "(?:" + "|".join(_k(p) for p in ps) + ")"


def _limpa(nome):
    nome = (nome or "").strip().strip(".,;:!?").strip()
    if len(nome) >= 2 and nome[0] == nome[-1] and nome[0] in "\"'`“”":
        nome = nome[1:-1]
    return nome.strip("“”").strip()


ATIVA = {"", "camada", "a camada", "da camada", "na camada", "ativa", "a ativa", "camada ativa", "a camada ativa", "atual", "a atual",
         "camada atual", "esta", "essa", "esta camada", "essa camada", "nesta", "nessa",
         "selecionada", "camada selecionada", "a camada selecionada"}

# ----------------------------------------------------------------- vocabulário
V_CRIAR = _alt("criar", "crie", "cria", "adicionar", "adicione", "adiciona", "incluir", "inclua",
               "inserir", "insira", "fazer", "faça", "gerar", "gere")
V_APAGAR = _alt("apagar", "apague", "apaga", "deletar", "delete", "deleta", "excluir", "exclua",
                "exclui", "remover", "remova", "remove", "tirar", "tire", "tira", "eliminar",
                "elimine")
V_COPIAR = _alt("copiar", "copie", "copia", "duplicar", "duplique", "duplica", "clonar", "clone")
V_RENOMEAR = _alt("renomear", "renomeie", "renomeia", "trocar o nome", "troque o nome",
                  "mudar o nome", "mude o nome", "alterar o nome", "altere o nome")
V_SELEC = _alt("selecionar", "selecione", "seleciona", "marcar", "marque", "marca")
V_CALC = _alt("calcular", "calcule", "calcula", "preencher", "preencha", "preenche",
              "atualizar", "atualize", "atualiza", "popular", "popule")
V_SALVAR = _alt("salvar", "salve", "salva", "gravar", "grave", "grava", "confirmar", "confirme",
                "aplicar", "aplique", "fechar e salvar", "terminar", "termine", "finalizar",
                "finalize", "encerrar", "encerre", "parar", "pare")
V_CANCELAR = _alt("cancelar", "cancele", "cancela", "descartar", "descarte", "descarta",
                  "desfazer todas", "desfaça todas", "jogar fora", "abandonar")
V_INICIAR = _alt("iniciar", "inicie", "inicia", "ligar", "ligue", "liga", "ativar", "ative",
                 "ativa", "abrir", "abra", "abre", "começar", "comece", "habilitar", "habilite",
                 "entrar em", "entre em", "modo de")
V_LIMPAR = _alt("limpar", "limpe", "limpa", "tirar", "tire", "tira", "remover", "remova",
                "zerar", "zere", "desmarcar", "desmarque", "cancelar", "cancele", "desfazer")
V_LISTAR = _alt("listar", "liste", "lista", "mostrar", "mostre", "mostra", "ver", "exibir",
                "exiba", "quais sao", "quais são", "quais")
N_CAMPO = _alt("campo", "campos", "coluna", "colunas", "atributo", "atributos")
N_FEICAO = _alt("feição", "feições", "feicao", "feicoes", "registro", "registros", "item",
                "itens", "objeto", "objetos", "elemento", "elementos", "linha", "linhas",
                "ponto", "pontos", "polígono", "polígonos", "geometria", "geometrias")
N_EDICAO = _alt("edição", "edicao", "edições", "edicoes", "alteração", "alterações",
                "mudança", "mudanças", "modificação", "modificações")
ART = r"(?:(?:o|a|os|as|um|uma|uns|umas)\s+)?"
FIM = r"\s*[.!?]*\s*$"

TIPOS = [  # (padrão, tipo, rótulo)
    (_alt("data e hora", "datahora", "timestamp", "datetime"), "DateTime", "Data e hora"),
    (_alt("inteiro grande", "long", "bigint", "inteiro longo"), "Long", "Inteiro grande"),
    (_alt("número inteiro", "numero inteiro", "inteiro", "int", "integer", "inteiros"),
     "Integer", "Inteiro"),
    (_alt("decimal", "decimais", "real", "double", "float", "número", "numero", "numérico",
          "numerico", "número decimal", "valor", "moeda"), "Double", "Decimal"),
    (_alt("data", "date"), "Date", "Data"),
    (_alt("booleano", "boolean", "bool", "lógico", "logico", "sim/não", "sim ou não",
          "verdadeiro/falso"), "Boolean", "Sim/Não"),
    (_alt("texto", "string", "caractere", "caracteres", "char", "varchar", "palavra",
          "nome"), "String", "Texto"),
]
_TIPO_ALT = "(?:" + "|".join(p for p, _, _ in TIPOS) + ")"


def _tipo(txt):
    for p, t, rot in TIPOS:
        if re.fullmatch(p, txt.strip(), re.I):
            return t, rot
    return "String", "Texto"


# ------------------------------------------------------------- resolução de nomes
def _normal(s):
    return re.sub(r"[\s_\-]+", " ", sem_acento(s)).strip()


def _achar(nome, opcoes, oque, parcial=True):
    """Acha 'nome' em 'opcoes' sem diferenciar acento/maiúscula; aceita trecho único."""
    alvo = sem_acento(_limpa(nome))
    if not alvo:
        raise ErroComando(f"Faltou dizer {oque}.")
    exatos = [o for o in opcoes if sem_acento(o) == alvo]
    if exatos:
        return exatos[0]
    exatos = [o for o in opcoes if _normal(o) == _normal(alvo)]
    if len(exatos) == 1:
        return exatos[0]
    if not parcial:
        raise ErroComando(f"Não achei {oque} '{_limpa(nome)}'.")
    parciais = [o for o in opcoes if _normal(alvo) in _normal(o)]
    if len(parciais) == 1:
        return parciais[0]
    if len(parciais) > 1:
        raise ErroComando(f"'{_limpa(nome)}' pode ser {oque} {', '.join(repr(p) for p in parciais)}. "
                          "Diga o nome completo.")
    lista = ", ".join(repr(o) for o in opcoes[:30]) or "nenhum"
    raise ErroComando(f"Não achei {oque} '{_limpa(nome)}'. Opções: {lista}.")


MSG_SELECIONE = ("Nenhuma camada selecionada. Clique na camada no painel de Camadas "
                 "e repita o comando (não precisa dizer o nome dela).")


def _ativa(ctx):
    if not ctx.get("ativa"):
        raise ErroComando(MSG_SELECIONE)
    return ctx["ativa"]


def _so_ativa(camada, ctx):
    """Regra 1: o comando só vale para a camada selecionada."""
    ativa = _ativa(ctx)
    if camada != ativa:
        raise ErroComando(f"Os comandos valem só para a camada selecionada ('{ativa}'). "
                          f"Para mexer em '{camada}', clique nela no painel de Camadas e repita.")
    return camada


def _camada(nome, ctx):
    nome = _limpa(nome)
    if sem_acento(nome) in ATIVA:
        return _ativa(ctx)
    return _so_ativa(_achar(nome, ctx.get("camadas", []), "a camada"), ctx)


def _campo(nome, camada, ctx):
    return _achar(nome, ctx.get("campos", {}).get(camada, []), f"o campo (em '{camada}')",
                  parcial=False)


MSG_ASPAS = "Edição de campos: escreva o nome do campo entre aspas. Ex.: {}"
_RE_ASPAS = r'"([^"]+)"'


def _aspas(txt):
    """Nomes entre aspas duplas, na ordem em que aparecem."""
    return re.findall(_RE_ASPAS, txt or "")


def _sem_aspas(txt):
    """Texto sem os trechos entre aspas duplas."""
    return re.sub(_RE_ASPAS, " ", txt or "")


def _exige_aspas(txt, exemplo, minimo=1):
    nomes = _aspas(txt)
    if len(nomes) < minimo:
        raise ErroComando(MSG_ASPAS.format(exemplo))
    return nomes


def _camada_de(txt, ctx):
    """Camada em trechos como 'lotes', 'da camada lotes', 'as feições de lotes', ''."""
    txt = (txt or "").strip()
    txt = re.sub(rf"^{_alt('todos os', 'todas as', 'todos', 'todas')}\s+", "", txt, flags=re.I)
    sem_prep = re.sub(rf"^(?:{_PREP}\s+)?{ART}(?:{_k('camada')}(?:\s+|$))?", "", txt, flags=re.I)
    try:
        return _camada(sem_prep, ctx)
    except ErroComando as erro:
        t2 = re.sub(rf"^{ART}{N_FEICAO}(?:\s+|$)", "", txt, flags=re.I)
        if t2 == txt:
            raise erro
        t2 = re.sub(rf"^(?:{_PREP}\s+)?{ART}(?:{_k('camada')}(?:\s+|$))?", "", t2, flags=re.I)
        return _camada(t2, ctx)


_PREP = r"(?:n[ao]s?|d[ao]s?|de|em|para|pra|à|a)"


def _separar_camada(texto, ctx, obrigatoria=False):
    """Separa '... na camada X' do fim do texto. Devolve (resto, camada).

    Aceita 'na camada lotes', 'da camada lotes', 'em lotes', 'de lotes' — o
    último só quando 'lotes' é mesmo uma camada, para não confundir com
    'campo nome de rua'.
    """
    texto = texto.strip()
    m = re.search(rf"\s+{_PREP}\s+{ART}(?:{_k('camada')})\s+(.+?)$", texto, re.I)
    if m:
        return texto[:m.start()].strip(), _camada(m.group(1), ctx)
    m = re.search(rf"\s+{_PREP}\s+(?:{_k('camada ativa')}|{_k('camada atual')}|{_k('esta camada')}|{_k('essa camada')})$",
                  texto, re.I)
    if m:
        return texto[:m.start()].strip(), _camada("", ctx)
    for m in re.finditer(rf"\s+{_PREP}\s+", texto, re.I):
        cand = texto[m.end():]
        try:
            achada = _achar(cand, ctx.get("camadas", []), "a camada", parcial=False)
        except ErroComando:
            continue
        return texto[:m.start()].strip(), _so_ativa(achada, ctx)
    if obrigatoria:
        return texto, _camada("", ctx)
    return texto, None


def _ou_ativa(camada, ctx):
    return camada if camada else _camada("", ctx)


def _lista_nomes(txt):
    partes = re.split(r"\s*,\s*|\s+e\s+", _limpa(txt))
    return [_limpa(p) for p in partes if _limpa(p)]


# --------------------------------------------------------- expressões em português
_OPS = [
    (_alt("maior ou igual a", "maior ou igual que", "pelo menos", "no mínimo"), ">="),
    (_alt("menor ou igual a", "menor ou igual que", "no máximo", "até"), "<="),
    (_alt("maior que", "maior do que", "acima de", "mais que", "mais de", "maior"), ">"),
    (_alt("menor que", "menor do que", "abaixo de", "menos que", "menos de", "menor"), "<"),
    (_alt("diferente de", "não é", "nao e", "não igual a", "diferente"), "<>"),
    (_alt("igual a", "igual", "é", "for", "seja", "vale"), "="),
]


_GEOMETRIA = [
    (_alt("área em hectares", "area em hectares", "hectares"), "$area / 10000"),
    (_alt("área", "area", "área em m2"), "$area"),
    (_alt("comprimento em km", "extensão em km"), "$length / 1000"),
    (_alt("comprimento", "extensão", "extensao", "tamanho"), "$length"),
    (_alt("perímetro", "perimetro"), "$perimeter"),
]


EX_CONDICAO = 'selecionar onde "bairro" igual a Centro'


def _valor(v, campos, lado_campo=False):
    v = v.strip()
    if lado_campo:
        v = re.sub(rf"^{ART}(?:{_alt('campo', 'coluna')}\s+)?", "", v, flags=re.I).strip()
    if not v:
        return v
    if len(v) > 1 and v[0] == '"' and v[-1] == '"':
        dentro = v[1:-1]
        if lado_campo:  # campo entre aspas: precisa existir
            return '"' + _achar(dentro, list(campos), "o campo", parcial=False) + '"'
        achados = [c for c in campos if sem_acento(c) == sem_acento(dentro)]
        return '"' + achados[0] + '"' if achados else "'" + dentro.replace("'", "''") + "'"
    if len(v) > 1 and v[0] == "'" and v[-1] == "'":
        return "'" + v[1:-1].replace("'", "''") + "'"
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", v):
        return v.replace(",", ".")
    if lado_campo:  # sem aspas: só medida da geometria (area, comprimento...)
        for pad, geo in _GEOMETRIA:
            if re.fullmatch(pad, v, re.I):
                return geo
        if re.search(r"[$@(]", v):
            return v
        raise ErroComando(MSG_ASPAS.format(EX_CONDICAO))
    if re.search(r"[()$@+*/]|\bnull\b|\btrue\b|\bfalse\b", v, re.I):
        return v
    return "'" + v.replace("'", "''") + "'"


def expressao(texto, campos=()):
    """Converte uma condição simples em português para expressão QGIS.

    'area maior que 100'             -> "area" > 100
    'bairro igual a Centro'          -> "bairro" = 'Centro'
    'nome contém rua'                -> "nome" ILIKE '%rua%'
    'tipo vazio'                     -> "tipo" IS NULL
    'area > 100 e uso = residencial' -> "area" > 100 AND "uso" = 'residencial'
    Expressões já escritas em sintaxe QGIS passam quase sem mudança.
    """
    texto = texto.strip()
    if not texto:
        return ""
    campos = list(campos)
    if re.search(r"\$\w+|@\w+|\w+\(|\b(?:ilike|like|is|in|and|or)\b", texto, re.I):
        return texto  # já é expressão QGIS
    guardados = []

    def _guarda(m):
        guardados.append(m.group(0))
        return f"\x00{len(guardados) - 1}\x00"

    texto = re.sub(r'"[^"]*"|\'[^\']*\'', _guarda, texto)

    def _volta(t):
        return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], t)

    texto = re.sub(r"\b(entre\s+\S+)\s+e\s+", r"\1 __E__ ", texto, flags=re.I)
    texto = re.sub(rf"\s+{_alt('maior ou igual a', 'maior ou igual que', 'maior ou igual')}\s+", " >= ", texto, flags=re.I)
    texto = re.sub(rf"\s+{_alt('menor ou igual a', 'menor ou igual que', 'menor ou igual')}\s+", " <= ", texto, flags=re.I)
    partes = re.split(r"(\s+(?:e|and)\s+|\s+(?:ou|or)\s+)", texto, flags=re.I)
    out = []
    for p in partes:
        if re.fullmatch(r"\s+(?:e|and)\s+", p, re.I):
            out.append(" AND ")
            continue
        if re.fullmatch(r"\s+(?:ou|or)\s+", p, re.I):
            out.append(" OR ")
            continue
        out.append(_condicao(_volta(p.strip()), campos))
    return "".join(out)


def _condicao(c, campos):
    m = re.fullmatch(r"(.+?)\s*(>=|<=|<>|!=|=|>|<)\s*(.+)", c)
    if m:
        op = "<>" if m.group(2) == "!=" else m.group(2)
        return f"{_valor(m.group(1), campos, True)} {op} {_valor(m.group(3), campos)}"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('contém', 'contem', 'tem', 'inclui', 'possui', 'parecido com', 'como')})\s+(.+)", c, re.I)
    if m:
        v = _limpa(m.group(2)).replace("'", "''")
        return f"{_valor(m.group(1), campos, True)} ILIKE '%{v}%'"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('começa com', 'começa por', 'inicia com')})\s+(.+)", c, re.I)
    if m:
        v = _limpa(m.group(2)).replace("'", "''")
        return f"{_valor(m.group(1), campos, True)} ILIKE '{v}%'"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('termina com', 'termina em')})\s+(.+)", c, re.I)
    if m:
        v = _limpa(m.group(2)).replace("'", "''")
        return f"{_valor(m.group(1), campos, True)} ILIKE '%{v}'"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('não vazio', 'nao vazio', 'não está vazio', 'preenchido', 'não nulo', 'nao nulo', 'não é nulo')})", c, re.I)
    if m:
        return f"{_valor(m.group(1), campos, True)} IS NOT NULL"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('vazio', 'em branco', 'nulo', 'está vazio', 'é nulo', 'sem valor')})", c, re.I)
    if m:
        return f"{_valor(m.group(1), campos, True)} IS NULL"
    m = re.fullmatch(rf"(.+?)\s+(?:{_alt('entre')})\s+(\S+)\s+__E__\s+(\S+)", c, re.I)
    if m:
        return f"{_valor(m.group(1), campos, True)} BETWEEN {_valor(m.group(2), campos)} AND {_valor(m.group(3), campos)}"
    for pad, op in _OPS:
        m = re.fullmatch(rf"(.+?)\s+{pad}\s+(.+)", c, re.I)
        if m:
            return f"{_valor(m.group(1), campos, True)} {op} {_valor(m.group(2), campos)}"
    return c


def _onde(texto):
    """Divide 'X onde COND' em (X, COND)."""
    m = re.search(rf"\s+(?:{_alt('onde', 'com', 'que tem', 'que têm', 'cujo', 'cuja', 'em que', 'quando', 'se')})\s+",
                  " " + texto, re.I)
    if not m:
        return texto.strip(), ""
    t = " " + texto
    return t[:m.start()].strip(), t[m.end():].strip()


# ------------------------------------------------------------------- comandos
COMANDOS = []
EXEMPLOS = []


def comando(padrao, exemplo, primeiro=False):
    """Registra um comando. primeiro=True: testado antes dos outros (frases que
    um comando mais genérico, como 'zoom na camada X', engoliria)."""
    def deco(fn):
        item = (re.compile("^" + padrao + FIM, re.I), fn, exemplo)
        EXEMPLOS.append(exemplo)
        if primeiro:
            COMANDOS.insert(0, item)
        else:
            COMANDOS.append(item)
        return fn
    return deco


def _plano(descricao, action, params, destrutivo=False):
    return {"descricao": descricao, "destrutivo": destrutivo,
            "steps": [{"action": action, "params": params}]}


# --- camadas
@comando(rf"(?:{V_COPIAR}|{V_CRIAR}\s+uma\s+{_k('cópia')}(?:\s+d[aeo])?)(?:\s+{ART}(?:{_k('camada')})?\s*(?P<resto>.*?))?",
         "copiar camada como lotes_backup")
def _copiar(m, ctx):
    resto = m.group("resto") or ""
    so_sel = False
    ms = re.search(rf"\s*\(?(?:{_alt('só as selecionadas', 'só selecionadas', 'somente as selecionadas', 'apenas as selecionadas', 'só os selecionados', 'só a seleção', 'só seleção', 'das selecionadas', 'selecionadas')})\)?\s*",
                   resto, re.I)
    if ms:
        so_sel = True
        resto = (resto[:ms.start()] + " " + resto[ms.end():]).strip()
    mn = re.search(rf"\s+(?:como|{_k('com o nome')}(?:\s+de)?|{_k('com nome')}(?:\s+de)?|{_k('chamada')}|{_k('chamado')}|{_k('nomeada')}|para|pra)\s+(?P<novo>.+)$",
                   " " + resto, re.I)
    novo = None
    if mn:
        novo = _limpa(mn.group("novo"))
        resto = (" " + resto)[:mn.start()].strip()
    camada = _camada(resto, ctx)
    params = {"layer_name": camada}
    if novo:
        params["output_name"] = novo
    if so_sel:
        params["only_selected"] = True
    alvo = f" como '{novo}'" if novo else ""
    sel = " (só as feições selecionadas)" if so_sel else ""
    return _plano(f"Copiar a camada '{camada}'{alvo}{sel}", "duplicate_layer", params)


@comando(rf"{V_RENOMEAR}\s+(?:d[ao]\s+)?{ART}{_k('camada')}(?:\s+(?P<camada>.+?))?\s+(?:para|pra|como)\s+(?P<novo>.+?)",
         "renomear camada para lotes_2026")
def _renomear_camada(m, ctx):
    camada = _camada(m.group("camada") or "", ctx)
    novo = _limpa(m.group("novo"))
    return _plano(f"Renomear a camada '{camada}' para '{novo}'", "rename_layer",
                  {"layer_name": camada, "new_name": novo})


@comando(rf"{V_APAGAR}\s+{ART}{_k('camada')}\s*(?P<camada>.*?)(?:\s+d[oa]\s+(?:projeto|mapa))?",
         "remover camada")
def _remover_camada(m, ctx):
    camada = _camada(m.group("camada"), ctx)
    return _plano(f"Remover a camada '{camada}' do projeto (o arquivo não é apagado)",
                  "remove_layer", {"layer_name": camada}, destrutivo=True)


@comando(rf"(?:{V_LISTAR}\s+{ART}|{_alt('quantas')}\s+){_k('camadas')}(?:\s+(?:{_alt('tem', 'há', 'existem')}\s+)?(?:n[oa]|d[oa])\s+(?:projeto|mapa))?",
         "listar camadas")
def _listar_camadas(m, ctx):
    return _plano("Listar as camadas do projeto", "list_layers", {})


# --- campos
@comando(rf"{V_CRIAR}\s+(?:{ART})?(?:{_alt('novo', 'nova')}\s+)?{N_CAMPO}\s+(?P<resto>.+?)",
         'criar campo "area" tipo decimal')
def _criar_campo(m, ctx):
    nome = _exige_aspas(m.group("resto"), 'criar campo "area" tipo decimal')[0].strip()
    resto = " " + _sem_aspas(m.group("resto")) + " "
    tipo, rotulo, tam, prec = "String", "Texto", None, None
    mt = re.search(rf"\s+(?:{_alt('do tipo', 'de tipo', 'tipo', 'como', 'em', 'de')})\s+(?P<t>{_TIPO_ALT})(?=\s|$|,)", resto, re.I)
    if mt:
        tipo, rotulo = _tipo(mt.group("t"))
        resto = (resto[:mt.start()] + resto[mt.end():]).strip()
    mz = re.search(rf"\s*,?\s*(?:com\s+)?(?:{_alt('tamanho', 'comprimento', 'largura')})\s+(?:de\s+)?(\d+)", resto, re.I)
    if mz:
        tam = int(mz.group(1))
        resto = (resto[:mz.start()] + resto[mz.end():]).strip()
    mp = re.search(rf"\s*,?\s*(?:com\s+)?(\d+)\s+(?:{_alt('casas decimais', 'casas', 'decimais')})", resto, re.I)
    if not mp:
        mp = re.search(rf"\s*,?\s*(?:com\s+)?(?:{_alt('precisão', 'precisao')})\s+(?:de\s+)?(\d+)", resto, re.I)
    if mp:
        prec = int(mp.group(1))
        if tipo == "String":
            tipo, rotulo = "Double", "Decimal"
        resto = (resto[:mp.start()] + resto[mp.end():]).strip()
    resto, camada = _separar_camada(resto.strip(), ctx)
    camada = _ou_ativa(camada, ctx)
    if not mt:  # 'criar campo "area" decimal': a palavra que sobrou é o tipo
        mt2 = re.search(rf"(?:^|\s)(?P<t>{_TIPO_ALT})$", resto.strip(), re.I)
        if mt2:
            tipo, rotulo = _tipo(mt2.group("t"))
    if not nome:
        raise ErroComando(MSG_ASPAS.format('criar campo "area" tipo decimal'))
    params = {"layer_name": camada, "field_name": nome, "field_type": tipo}
    extra = []
    if tam:
        params["length"] = tam
        extra.append(f"tamanho {tam}")
    if prec is not None:
        params["precision"] = prec
        extra.append(f"{prec} casas decimais")
    ex = f", {', '.join(extra)}" if extra else ""
    return _plano(f"Criar o campo '{nome}' ({rotulo}{ex}) na camada '{camada}'", "add_field", params)


@comando(rf"{V_APAGAR}\s+{ART}{N_CAMPO}\s+(?P<resto>.+?)", 'apagar campo "obs"')
def _apagar_campo(m, ctx):
    brutos = _exige_aspas(m.group("resto"), 'apagar campo "obs"  ou  apagar campos "obs" e "uso"')
    _, camada = _separar_camada(_sem_aspas(m.group("resto")).strip(), ctx)
    camada = _ou_ativa(camada, ctx)
    nomes = [_campo(n, camada, ctx) for n in brutos]
    alvo = nomes[0] if len(nomes) == 1 else nomes
    txt = ", ".join(f"'{n}'" for n in nomes)
    return _plano(f"Apagar {'o campo' if len(nomes) == 1 else 'os campos'} {txt} da camada '{camada}'",
                  "delete_field", {"layer_name": camada, "field_name": alvo}, destrutivo=True)


@comando(rf"{V_RENOMEAR}\s+(?:d[ao]\s+)?{ART}{N_CAMPO}\s+(?P<resto>.+?)", 'renomear campo "nm" para "nome"')
def _renomear_campo(m, ctx):
    nomes = _exige_aspas(m.group("resto"), 'renomear campo "nm" para "nome"', minimo=2)
    _, camada = _separar_camada(_sem_aspas(m.group("resto")).strip(), ctx)
    camada = _ou_ativa(camada, ctx)
    antigo = _campo(nomes[0], camada, ctx)
    novo = nomes[1].strip()
    return _plano(f"Renomear o campo '{antigo}' para '{novo}' na camada '{camada}'", "rename_field",
                  {"layer_name": camada, "field_name": antigo, "new_name": novo})


@comando(rf"{V_LISTAR}\s+{ART}{N_CAMPO}(?P<resto>.*?)", "listar campos")
def _listar_campos(m, ctx):
    resto = m.group("resto").strip()
    camada = _camada(re.sub(rf"^{_PREP}\s+{ART}(?:{_k('camada')}\s+)?", "", resto, flags=re.I), ctx) \
        if resto else _camada("", ctx)
    return _plano(f"Listar os campos da camada '{camada}'", "list_fields", {"layer_name": camada})


_EXPR_SEP = rf"(?:\s*=\s*|\s+(?:com|como|usando|igual a|recebendo|pela expressão|pela expressao|por)\s+)"


@comando(rf"{V_CALC}\s+{ART}{N_CAMPO}\s+(?P<resto>.+?)", 'calcular campo "area_ha" com área em hectares')
def _calcular_campo(m, ctx):
    resto = m.group("resto")
    so_sel = False
    ms = re.search(rf"\s+(?:{_alt('só nas selecionadas', 'só das selecionadas', 'só nos selecionados', 'nas selecionadas', 'apenas nas selecionadas')})", resto, re.I)
    if ms:
        so_sel = True
        resto = (resto[:ms.start()] + resto[ms.end():]).strip()
    mn = re.match(r'\s*"([^"]+)"', resto)
    if not mn:
        raise ErroComando(MSG_ASPAS.format('calcular campo "area_ha" com área em hectares'))
    nome_alvo = mn.group(1).strip()
    partes = re.split(_EXPR_SEP, " " + resto[mn.end():], maxsplit=1, flags=re.I)
    if len(partes) != 2:
        raise ErroComando('Use: calcular campo "NOME" com EXPRESSÃO (ex.: com $area / 10000).')
    esquerda, expr = partes
    camada = None
    mc = re.search(rf"\s+{_PREP}\s+{ART}{_k('camada')}\s+(?P<c>.+)$", expr, re.I)
    if mc:  # '... com $area na camada lotes'
        try:
            camada = _camada(mc.group("c"), ctx)
            expr = expr[:mc.start()]
        except ErroComando:
            camada = None
    esquerda, cam2 = _separar_camada(esquerda.strip(), ctx)
    if not cam2 and esquerda.strip():
        cam2 = _camada_de(esquerda, ctx)
    camada = camada or _ou_ativa(cam2, ctx)
    campos = ctx.get("campos", {}).get(camada, [])
    try:
        nome = _campo(nome_alvo, camada, ctx)
    except ErroComando:
        nome = nome_alvo  # campo novo: calculate_field cria
    expr = _expr_calculo(expr.strip(), campos)
    params = {"layer_name": camada, "field_name": nome, "expression": expr}
    if nome not in campos:
        params["field_type"] = _tipo_da_expr(expr)
    if so_sel:
        params["only_selected"] = True
    sel = " (só nas selecionadas)" if so_sel else ""
    return _plano(f"Calcular o campo '{nome}' = {expr} na camada '{camada}'{sel}", "calculate_field", params)


_ATALHOS_EXPR = [
    (_alt("área em hectares", "area em hectares", "hectares", "área em ha", "ha"), "$area / 10000"),
    (_alt("área em km2", "área em km²", "km2", "km²"), "$area / 1000000"),
    (_alt("área", "area", "área em m2", "area em m2", "m2", "metros quadrados"), "$area"),
    (_alt("comprimento em km", "extensão em km", "km"), "$length / 1000"),
    (_alt("comprimento", "extensão", "extensao", "tamanho", "metros", "perímetro", "perimetro"),
     "$length"),
    (_alt("perímetro do polígono", "perimetro do poligono"), "$perimeter"),
    (_alt("coordenada x", "x", "longitude"), "$x"),
    (_alt("coordenada y", "y", "latitude"), "$y"),
    (_alt("id", "número da feição", "numero da feicao", "id da feição"), "$id"),
    (_alt("numeração", "numeracao", "sequencial", "número sequencial", "contador"), "@row_number"),
    (_alt("data de hoje", "hoje", "data atual"), "now()"),
    (_alt("vazio", "nulo", "nada"), "NULL"),
]


def _expr_calculo(txt, campos):
    t = _limpa(txt) if (txt[:1] in "'\"" and txt[-1:] == txt[:1] and txt.count(txt[0]) == 2) else txt.strip()
    for pad, expr in _ATALHOS_EXPR:
        if re.fullmatch(rf"(?:{ART})?(?:{pad})", t, re.I):
            return expr
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", t):
        return t.replace(",", ".")
    if txt.strip()[:1] in "'\"" and txt.strip()[-1:] == txt.strip()[:1]:
        v = txt.strip()[1:-1]
        if txt.strip()[0] == '"' and v in campos:
            return txt.strip()
        return "'" + v.replace("'", "''") + "'"
    if re.search(r'[$@()"+\-*/|]', t) or re.search(r"\b(?:case|when|if|concat|round|to_)\w*", t, re.I):
        return t
    if " " not in t:
        return "'" + t.replace("'", "''") + "'"
    return t


def _tipo_da_expr(expr):
    if re.fullmatch(r"-?\d+", expr) or expr in ("$id", "@row_number"):
        return "Integer"
    if re.fullmatch(r"-?\d+\.\d+", expr) or re.search(r"\$(?:area|length|perimeter|x|y)\b", expr):
        return "Double"
    if expr == "now()":
        return "DateTime"
    return "String"


# --- seleção
@comando(rf"{V_SELEC}\s+(?:{_alt('tudo', 'todas', 'todos', 'todas as feições', 'todos os registros', 'tudo de')})(?:\s+{_PREP})?\s*(?:{ART}{_k('camada')})?\s*(?P<camada>.*?)",
         "selecionar tudo")
def _selecionar_tudo(m, ctx):
    if _onde(m.group("camada"))[1]:
        return None  # 'selecionar todos os lotes onde ...': é seleção por condição
    camada = _camada_de(m.group("camada"), ctx)
    return _plano(f"Selecionar todas as feições de '{camada}'", "select_features", {"layer_name": camada})


@comando(rf"{V_SELEC}\s+(?P<resto>.+?)", 'selecionar onde "bairro" igual a Centro')
def _selecionar(m, ctx):
    resto = m.group("resto")
    modo = "new"
    mm = re.search(rf"\s*\(?(?:{_alt('somando à seleção', 'somar à seleção', 'adicionando à seleção', 'e somar', 'além da seleção')})\)?\s*$", resto, re.I)
    if mm:
        modo, resto = "add", resto[:mm.start()]
    esquerda, cond = _onde(resto)
    if not cond:
        raise ErroComando("Use: 'selecionar CAMADA onde CONDIÇÃO' (ex.: onde area maior que 1000).")
    camada = _camada_de(esquerda, ctx)
    expr = expressao(cond, ctx.get("campos", {}).get(camada, []))
    return _plano(f"Selecionar em '{camada}' onde {expr}", "select_features",
                  {"layer_name": camada, "expression": expr, "mode": modo})


@comando(rf"(?:{V_LIMPAR}\s+{ART}{_alt('seleção', 'seleções', 'selecionados', 'selecionadas')}|{_alt('desselecionar', 'desselecione', 'desmarcar tudo', 'desmarque tudo')})(?P<resto>.*?)",
         "limpar seleção")
def _limpar_selecao(m, ctx):
    resto = re.sub(rf"^\s*(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?", "", m.group("resto"), flags=re.I).strip()
    if not resto or sem_acento(resto) in ("tudo", "todas", "todas as camadas", "de tudo"):
        return _plano("Limpar a seleção de todas as camadas", "clear_selection", {})
    camada = _camada(resto, ctx)
    return _plano(f"Limpar a seleção de '{camada}'", "clear_selection", {"layer_name": camada})


@comando(rf"{_alt('inverter', 'inverta', 'inverte')}\s+{ART}{_k('seleção')}(?P<resto>.*?)", "inverter seleção")
def _inverter(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Inverter a seleção de '{camada}'", "invert_selection", {"layer_name": camada})


@comando(rf"{V_APAGAR}\s+{ART}(?:{N_FEICAO}\s+)?{_alt('selecionadas', 'selecionados', 'seleção', 'a seleção')}(?P<resto>.*?)",
         "apagar feições selecionadas")
def _apagar_selecionadas(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Apagar as feições selecionadas de '{camada}'", "delete_selected_features",
                  {"layer_name": camada}, destrutivo=True)


@comando(rf"{V_APAGAR}\s+{ART}(?:{N_FEICAO})\s+(?P<resto>.+?)", 'apagar feições onde "uso" vazio')
def _apagar_feicoes(m, ctx):
    esquerda, cond = _onde(m.group("resto"))
    if not cond:
        return None
    camada = _camada_de(esquerda.strip(), ctx)
    expr = expressao(cond, ctx.get("campos", {}).get(camada, []))
    return _plano(f"Apagar as feições de '{camada}' onde {expr}", "delete_features",
                  {"layer_name": camada, "expression": expr}, destrutivo=True)


@comando(rf"{_alt('contar', 'conte', 'conta', 'quantas', 'quantos', 'total de')}\s+(?:{ART}{N_FEICAO}\s+)?(?:{_alt('tem', 'há', 'existem', 'possui')}\s+)?(?P<resto>.*?)",
         'contar feições onde area maior que 1000')
def _contar(m, ctx):
    esquerda, cond = _onde(m.group("resto"))
    camada = _camada_de(esquerda.strip(), ctx)
    if cond:
        expr = expressao(cond, ctx.get("campos", {}).get(camada, []))
        return _plano(f"Contar as feições de '{camada}' onde {expr}", "count_features",
                      {"layer_name": camada, "expression": expr})
    return _plano(f"Contar as feições de '{camada}'", "count_features", {"layer_name": camada})


# --- sessão de edição
@comando(rf"(?:{V_INICIAR}\s+{ART}{N_EDICAO}|{_alt('editar', 'edite', 'edita')})(?:\s+(?P<resto>.*?))?",
         "editar camada")
def _iniciar_edicao(m, ctx):
    camada = _camada_de((m.group("resto") or "").strip(), ctx)
    return _plano(f"Ligar a edição da camada '{camada}'", "start_editing", {"layer_name": camada})


@comando(rf"{V_SALVAR}\s+{ART}(?:{N_EDICAO}|{_alt('modo de edição', 'modo edição')})(?P<resto>.*?)",
         "salvar edição")
def _salvar_edicao(m, ctx):
    resto = re.sub(rf"^\s*(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?", "", m.group("resto"), flags=re.I).strip()
    if not resto or sem_acento(resto) in ("tudo", "todas", "todas as camadas"):
        return _plano("Salvar as edições de todas as camadas em edição", "commit_edits", {})
    camada = _camada(resto, ctx)
    return _plano(f"Salvar as edições de '{camada}'", "commit_edits", {"layer_name": camada})


@comando(rf"{V_CANCELAR}\s+{ART}(?:{N_EDICAO})(?P<resto>.*?)", "cancelar edição")
def _cancelar_edicao(m, ctx):
    resto = re.sub(rf"^\s*(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?", "", m.group("resto"), flags=re.I).strip()
    if not resto or sem_acento(resto) in ("tudo", "todas", "todas as camadas"):
        return _plano("Descartar as edições não salvas de todas as camadas", "rollback_edits", {},
                      destrutivo=True)
    camada = _camada(resto, ctx)
    return _plano(f"Descartar as edições não salvas de '{camada}'", "rollback_edits",
                  {"layer_name": camada}, destrutivo=True)


@comando(rf"(?P<verbo>{_alt('desfazer', 'desfaça', 'desfaz', 'voltar', 'volte', 'refazer', 'refaça', 'refaz')})"
         rf"(?:\s+(?P<n>\d+)(?:\s+{_alt('vezes', 'vez', 'passos', 'passo', 'alterações', 'alteração')})?)?"
         rf"(?:\s+{_alt('a última', 'última', 'ultima', 'o último', 'último')}(?:\s+{_alt('alteração', 'edição', 'coisa')})?)?"
         rf"(?:\s+(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?(?P<camada>.+?))?",
         "desfazer 2 vezes")
def _desfazer(m, ctx):
    refazer = sem_acento(m.group("verbo")).startswith("ref")
    n = int(m.group("n") or 1)
    camada = _camada(m.group("camada") or "", ctx)
    acao = "Refazer" if refazer else "Desfazer"
    vezes = f" {n} alterações" if n > 1 else " a última alteração"
    return _plano(f"{acao}{vezes} em '{camada}'", "redo_edit" if refazer else "undo_edit",
                  {"layer_name": camada, "steps": n})


@comando(rf"{_alt('o que está em edição', 'o que esta em edicao', 'status da edição', 'status de edição', 'edições pendentes', 'o que falta salvar', 'tem algo para salvar', 'tem edição pendente')}\??",
         "o que está em edição?")
def _status(m, ctx):
    return _plano("Mostrar as camadas em edição e as alterações pendentes", "edit_status", {})


# --- filtro e navegação
@comando(rf"(?:{_alt('limpar', 'limpe', 'tirar', 'tire', 'remover', 'remova', 'desligar', 'desligue', 'apagar', 'apague')})\s+{ART}{_alt('filtro', 'filtros')}(?P<resto>.*?)",
         "limpar filtro")
def _limpar_filtro(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Remover o filtro de '{camada}'", "clear_filter", {"layer_name": camada})


@comando(rf"{_alt('filtrar', 'filtre', 'filtra', 'mostrar só', 'mostre só', 'mostrar apenas', 'mostre apenas', 'exibir só', 'exibir apenas')}\s+(?:{ART}{N_FEICAO}\s+)?(?P<resto>.+?)",
         'filtrar onde "bairro" igual a Centro')
def _filtrar(m, ctx):
    esquerda, cond = _onde(m.group("resto"))
    if not cond:
        raise ErroComando("Use: 'filtrar CAMADA onde CONDIÇÃO'.")
    camada = _camada_de(esquerda.strip(), ctx)
    expr = expressao(cond, ctx.get("campos", {}).get(camada, []))
    return _plano(f"Filtrar '{camada}' para mostrar só onde {expr}", "filter_layer",
                  {"layer_name": camada, "expression": expr})


@comando(rf"(?:{_alt('zoom', 'dar zoom', 'dê zoom', 'aproximar', 'aproxime', 'enquadrar', 'enquadre', 'ir para', 'vá para', 'centralizar', 'centralize')})"
         rf"\s+(?:{_PREP}\s+)?{ART}{_alt('seleção', 'selecionadas', 'selecionados', 'feições selecionadas')}(?P<resto>.*?)",
         "zoom na seleção")
def _zoom_selecao(m, ctx):
    resto = re.sub(rf"^\s*(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?", "", m.group("resto"), flags=re.I).strip()
    if not resto:
        return _plano("Aproximar o mapa da seleção", "zoom_to_selection", {})
    camada = _camada(resto, ctx)
    return _plano(f"Aproximar o mapa da seleção de '{camada}'", "zoom_to_selection", {"layer_name": camada})


@comando(rf"(?:{_alt('zoom', 'dar zoom', 'dê zoom', 'aproximar', 'aproxime', 'enquadrar', 'enquadre', 'ir para', 'vá para', 'centralizar', 'centralize')})"
         rf"(?:\s+{_PREP})?\s+{ART}(?:{_k('camada')}\s+)?(?P<camada>.+?)",
         "zoom na camada")
def _zoom(m, ctx):
    camada = _camada(m.group("camada"), ctx)
    return _plano(f"Aproximar o mapa da camada '{camada}'", "zoom_to_layer", {"layer_name": camada})


# ======================================================== mapas e layouts
CORES = {
    "vermelho": "#e31a1c", "vermelha": "#e31a1c", "azul": "#1f78b4", "verde": "#33a02c",
    "amarelo": "#ffd92f", "amarela": "#ffd92f", "laranja": "#ff7f00", "roxo": "#6a3d9a",
    "roxa": "#6a3d9a", "rosa": "#f781bf", "preto": "#000000", "preta": "#000000",
    "branco": "#ffffff", "branca": "#ffffff", "cinza": "#969696", "marrom": "#8c510a",
    "bege": "#f5deb3", "vinho": "#7b1e3a", "ciano": "#00bcd4", "magenta": "#e7298a",
    "lilas": "#c39bd3", "dourado": "#d4af37", "dourada": "#d4af37", "turquesa": "#40e0d0",
    "salmao": "#fa8072", "creme": "#fffdd0", "violeta": "#8a2be2", "anil": "#3f51b5",
    "azul claro": "#a6cee3", "azul escuro": "#08306b", "azul marinho": "#001f5b",
    "azul celeste": "#87ceeb", "verde claro": "#b2df8a", "verde escuro": "#00441b",
    "verde limao": "#a4de02", "verde agua": "#66cdaa", "verde musgo": "#556b2f",
    "cinza claro": "#d9d9d9", "cinza escuro": "#525252", "vermelho escuro": "#99000d",
    "vermelho claro": "#fb9a99", "amarelo claro": "#ffffb3", "amarelo escuro": "#d4a017",
    "laranja claro": "#fdbf6f", "laranja escuro": "#d95f02", "roxo claro": "#cab2d6",
    "roxo escuro": "#3f007d", "rosa claro": "#fccde5", "rosa choque": "#ff1493",
    "marrom claro": "#bf812d", "marrom escuro": "#543005",
    "red": "#e31a1c", "blue": "#1f78b4", "green": "#33a02c", "yellow": "#ffd92f",
    "black": "#000000", "white": "#ffffff", "gray": "#969696", "orange": "#ff7f00",
}
SEM_COR = {"transparente", "sem preenchimento", "sem cor", "vazado", "vazio", "oco"}


def _cor(txt):
    """'azul', 'azul-escuro', 'verde clara', '#ff0000', '255,0,0' -> '#rrggbb'; None se não for cor."""
    t = sem_acento(_limpa(txt or "")).strip()
    t = re.sub(r"^(?:a\s+|o\s+)?(?:cor\s+)?(?:d[eo]\s+)?", "", t)
    t = re.sub(r"[-_]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if re.fullmatch(r"#[0-9a-f]{6}(?:[0-9a-f]{2})?|#[0-9a-f]{3}", t):
        return t
    m = re.fullmatch(r"(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", t)
    if m:
        return "#" + "".join(f"{min(int(v), 255):02x}" for v in m.groups())
    if t in CORES:
        return CORES[t]
    t2 = re.sub(r"\b(clar|escur)a\b", r"\1o", t)  # 'verde clara' -> 'verde claro'
    t2 = re.sub(r"^(vermelh|amarel|rox|pret|branc|dourad)a\b", r"\1o", t2)
    return CORES.get(t2)


def _eh_sem_cor(txt):
    return sem_acento(_limpa(txt or "")).strip() in SEM_COR


def _clarear(hexcor, f=0.85):
    """Mistura a cor com branco: começo de uma rampa 'em tons de X'."""
    h = hexcor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(f"{int(v + (255 - v) * f):02x}" for v in (r, g, b))


def _num(txt):
    return float(txt.replace(",", "."))


_SEP_COR = (r"\s+(?:" + _alt("com a cor", "com cor", "na cor", "da cor", "de cor", "para a cor",
                             "de", "para", "pra", "em", "com", "na", "como") + r")\s+")
_PREPS_SOLTAS = (r"(?:(?:" + _PREP + "|com|" + _k("a camada") + "|" + _k("da camada") + "|"
                 + _k("na camada") + "|" + _k("camada") + r")\s+)+")


def _camada_sobra(txt, ctx):
    """Camada no que sobrou da frase, ignorando preposições soltas; vazio = ativa."""
    t = re.sub(rf"^{_PREPS_SOLTAS}", "", " ".join((txt or "").split()) + " ", flags=re.I).strip()
    t = re.sub(rf"\s+(?:{_PREP}|com|e)$", "", t, flags=re.I).strip()
    return _camada_de(t, ctx) if t else _camada("", ctx)


def _camada_e_cor(resto, ctx):
    """'lotes de azul', 'de azul', 'azul em lotes', 'lotes azul' -> (camada, cor).

    cor 'sem' = sem preenchimento. (None, None) se não achou cor nenhuma.
    """
    resto = " " + " ".join(resto.split())
    erro = None
    for m in re.finditer(_SEP_COR, resto, re.I):
        direita = resto[m.end():].strip()
        c = _cor(direita) or ("sem" if _eh_sem_cor(direita) else None)
        if c:
            try:
                return _camada_sobra(resto[:m.start()], ctx), c
            except ErroComando as e:
                erro = e
    palavras = resto.split()
    for k in (3, 2, 1):
        if len(palavras) < k:
            continue
        for cor_txt, sobra in ((" ".join(palavras[:k]), palavras[k:]),
                               (" ".join(palavras[-k:]), palavras[:-k])):
            c = _cor(cor_txt) or ("sem" if _eh_sem_cor(cor_txt) else None)
            if c:
                try:
                    return _camada_sobra(" ".join(sobra), ctx), c
                except ErroComando as e:
                    erro = e
    if erro:
        raise erro
    return None, None


def _tirar(regex, texto):
    """Remove o trecho que casa com regex; devolve (texto_sem, match)."""
    m = re.search(regex, texto, re.I)
    if not m:
        return texto, None
    return (texto[:m.start()] + " " + texto[m.end():]), m


_MODOS = [
    (_alt("quantil", "quantis", "quartis", "mesma quantidade", "quantidade igual"), "Quantile"),
    (_alt("quebras naturais", "jenks"), "Jenks"),
    (_alt("intervalos iguais", "intervalo igual", "intervalos regulares"), "EqualInterval"),
    (_alt("desvio padrão", "desvio padrao", "desvios"), "StdDev"),
    (_alt("arredondados", "arredondado", "números redondos", "pretty"), "Pretty"),
]
_POR = (r"\s+(?:por|pelo|pela|" + _k("pelo campo") + "|" + _k("pela coluna") + "|" + _k("conforme")
        + "|" + _k("de acordo com") + "|" + _k("segundo") + r")\s+")


def _por_campo(resto, ctx, graduado):
    """'lotes por bairro', 'lotes por area em 5 classes', 'bairro em lotes' -> plano."""
    classes, modo, inicio, fim = 5, "EqualInterval", None, None
    resto = " " + resto + " "
    resto, mc = _tirar(r"\s,?\s*(?:em\s+|com\s+)?(\d+)\s+" + _alt("classes", "classe", "faixas", "faixa", "intervalos", "níveis", "niveis") + r"(?=\s)", resto)
    if mc:
        classes, graduado = int(mc.group(1)), True
    for pad, nome in _MODOS:
        resto, mm = _tirar(r"\s,?\s*(?:por\s+|em\s+|usando\s+|com\s+)?" + pad + r"(?=\s)", resto)
        if mm:
            modo, graduado = nome, True
            break
    resto, mt = _tirar(r"\s,?\s*(?:em\s+|com\s+|usando\s+)?" + _alt("tons de", "tom de", "degradê de", "degrade de", "gradiente de") + r"\s+(?P<c>[\w#,\- ]+?)(?=\s+(?:em|na|no|por|pelo|pela)\s|\s*$)", resto)
    if mt:
        if not _cor(mt.group("c")):
            raise ErroComando(f"Não conheço a cor '{mt.group('c').strip()}'.")
        fim = _cor(mt.group("c"))
        inicio = _clarear(fim)
        graduado = True
    md = re.search(r"\s(?:d[oa]|de)\s+(?P<a>[\w#\- ]+?)\s+(?:a[o]?|até|ate|para)\s+(?P<b>[\w#\- ]+?)(?=\s+(?:em|na|no|por)\s|\s*$)", resto, re.I)
    if md and _cor(md.group("a")) and _cor(md.group("b")):
        inicio, fim, graduado = _cor(md.group("a")), _cor(md.group("b")), True
        resto = resto[:md.start()] + " " + resto[md.end():]
    resto = " ".join(resto.split())
    partes = re.split(_POR, " " + resto, maxsplit=1, flags=re.I)
    if len(partes) == 2:
        esquerda, direita = partes
    else:  # 'cores por bairro em lotes': o 'por' já ficou no verbo
        esquerda, direita = "", resto
    direita = re.sub(rf"^(?:{ART})?(?:{N_CAMPO}\s+)?", "", direita.strip(), flags=re.I)
    entre_aspas = _aspas(direita)
    direita_sem = _sem_aspas(direita).strip() if entre_aspas else direita
    direita_sem, camada = _separar_camada(direita_sem, ctx)
    camada = camada or _camada_sobra(esquerda, ctx)
    if entre_aspas:
        campo = _campo(entre_aspas[0], camada, ctx)
    else:
        alvo = _limpa(direita_sem)
        campo = None
        for pad, geo in _GEOMETRIA:
            if re.fullmatch(pad, alvo, re.I):
                campo, graduado = geo, True
                break
        if campo is None:
            raise ErroComando(MSG_ASPAS.format('cores por "bairro"'))
    if graduado:
        params = {"layer_name": camada, "field": campo, "classes": classes, "mode": modo}
        if inicio:
            params.update(color_start=inicio, color_end=fim)
        return _plano(f"Colorir '{camada}' por '{campo}' em {classes} classes ({modo})",
                      "set_graduated_style", params)
    return _plano(f"Colorir '{camada}' com uma cor para cada valor de '{campo}'",
                  "set_categorized_style", {"layer_name": camada, "field": campo})


V_AJUSTAR = _alt("colocar", "coloque", "coloca", "deixar", "deixe", "deixa", "aplicar", "aplique",
                 "definir", "defina", "mudar", "mude", "muda", "ajustar", "ajuste", "pôr", "ponha",
                 "dar", "dê", "trocar", "troque", "alterar", "altere", "usar", "use", "botar",
                 "bote", "mudar a", "mude a", "trocar a", "alterar a", "aumentar", "aumente",
                 "diminuir", "diminua")
V_PINTAR = _alt("pintar", "pinte", "pinta", "colorir", "colora", "colore", "deixar", "deixe",
                "deixa", "mudar a cor de", "mude a cor de", "muda a cor de", "mudar a cor da",
                "mude a cor da", "mudar a cor do", "mude a cor do", "trocar a cor de",
                "troque a cor de", "trocar a cor da", "troque a cor da", "alterar a cor de",
                "altere a cor de", "alterar a cor da", "altere a cor da", "mudar cor de",
                "mude cor de", "mudar a cor", "mude a cor", "trocar a cor", "troque a cor",
                "cor de", "cor da", "cor do", "cor")
_K_TRANSP = _alt("transparência", "transparencia", "transparente", "semitransparente",
                 "semi transparente", "opacidade", "opaca", "opaco", "translúcida", "translucida",
                 "translúcido", "translucido")


# --- simbologia
@comando(rf"(?:{V_AJUSTAR}\s+)?(?P<resto>.*?{_K_TRANSP}.*?)", "transparência 50%")
def _opacidade(m, ctx):
    t = m.group("resto")
    if re.search(_alt("sem preenchimento", "pintar", "pinte", "rótulo", "rótulos"), t, re.I):
        return None
    n = re.search(r"(\d+(?:[.,]\d+)?)\s*(%|por\s*cento)?", t)
    fala_transp = re.search(_alt("transparência", "transparencia", "transparente", "semitransparente", "translúcida", "translucida"), t, re.I)
    if n:
        v = _num(n.group(1))
        frac = v / 100 if (n.group(2) or v > 1) else v
        opac = 1 - frac if fala_transp else frac
    elif re.search(_alt("sem transparência", "sem transparencia", "opaca", "opaco"), t, re.I) and \
            not re.search(_alt("semitransparente", "semi transparente"), t, re.I):
        opac = 1.0
    else:
        opac = 0.5
    sobra = re.sub(r"\d+(?:[.,]\d+)?\s*(?:%|por\s*cento)?", " ", t)
    sobra = re.sub(_alt("sem transparência", "sem transparencia", "totalmente", "nível de", "nivel de")
                   + "|" + _K_TRANSP, " ", sobra, flags=re.I)
    camada = _camada_sobra(sobra, ctx)
    opac = max(0.0, min(round(opac, 3), 1.0))
    return _plano(f"Deixar '{camada}' com {round((1 - opac) * 100)}% de transparência",
                  "set_layer_opacity", {"layer_name": camada, "opacity": opac})


@comando(_alt("sem contorno", "tirar o contorno", "tire o contorno", "remover o contorno",
              "remova o contorno", "tirar contorno", "tire contorno", "tirar a borda",
              "tire a borda", "sem borda") + r"(?P<resto>.*?)",
         "sem contorno", primeiro=True)
def _sem_contorno(m, ctx):
    camada = _camada_sobra(m.group("resto"), ctx)
    return _plano(f"Tirar o contorno de '{camada}'", "update_symbol",
                  {"layer_name": camada, "outline_color": "#00000000"})


@comando(rf"(?:{V_AJUSTAR}\s+)?(?:{ART})?" + _alt("contorno", "contornos", "borda", "bordas")
         + r"\s+(?P<resto>.+?)", "contorno preto de 0.5")
def _contorno(m, ctx):
    resto = " " + m.group("resto") + " "
    params = {}
    resto, mw = _tirar(r"\s(?:com\s+|de\s+)?(?:" + _alt("espessura", "largura") + r"\s+(?:de\s+)?)?(\d+(?:[.,]\d+)?)\s*(?:mm|milímetros?|milimetros?)?(?=\s)", resto)
    if mw:
        params["outline_width"] = _num(mw.group(1))
    camada, cor = _camada_e_cor(resto, ctx) if resto.strip() else (None, None)
    if cor is None:
        camada = _camada_sobra(resto, ctx)
    if cor == "sem":
        params["outline_color"] = "#00000000"
    elif cor:
        params["outline_color"] = cor
    if not params:
        raise ErroComando("Diga a cor ou a espessura do contorno. Ex.: 'contorno preto de 0.5 em lotes'.")
    params["layer_name"] = camada
    partes = []
    if cor:
        partes.append("sem cor" if cor == "sem" else f"cor {cor}")
    if mw:
        partes.append(f"espessura {params['outline_width']:g} mm")
    return _plano(f"Contorno de '{camada}': {' e '.join(partes)}", "update_symbol", params)


@comando(rf"(?:{V_AJUSTAR}\s+)?(?:{ART})?" + _alt("espessura", "largura", "grossura", "tamanho")
         + r"\s+(?:d[aoe]s?\s+(?P<o>" + _alt("linhas", "linha", "pontos", "ponto", "símbolos", "símbolo",
                                           "simbolos", "simbolo", "contorno", "borda", "traço", "traco")
         + r")\s+)?(?P<resto>.+?)", "espessura 1.5")
def _tamanho(m, ctx):
    resto = " " + m.group("resto") + " "
    resto, mn = _tirar(r"\s(?:para|pra|em|de|com|=)?\s*(\d+(?:[.,]\d+)?)\s*(?:mm|milímetros?|milimetros?)?(?=\s)", resto)
    if not mn:
        return None
    v = _num(mn.group(1))
    contorno = m.group("o") and sem_acento(m.group("o")) in ("contorno", "borda")
    camada = _camada_sobra(resto, ctx)
    if contorno:
        return _plano(f"Contorno de '{camada}' com {v:g} mm", "update_symbol",
                      {"layer_name": camada, "outline_width": v})
    return _plano(f"Tamanho/espessura do símbolo de '{camada}' = {v:g} mm", "update_symbol",
                  {"layer_name": camada, "size": v})


@comando(r"(?P<v>" + _alt("cores por", "cor por", "categorizar", "categorize", "categoriza",
                          "colorir por", "pintar por", "simbologia por", "estilo por", "classificar",
                          "classifique", "classifica", "graduar", "gradue", "degradê", "degrade",
                          "mapa temático", "mapa tematico", "mapa de cores")
         + r")\s+(?P<resto>.+?)", 'cores por "bairro"')
def _cores_por(m, ctx):
    v = sem_acento(m.group("v"))
    graduado = v.startswith(("classific", "gradu", "degrad"))
    return _por_campo(m.group("resto"), ctx, graduado)


@comando(rf"(?P<v>{V_PINTAR})\s+(?P<resto>.+?)", "pintar de azul")
def _pintar(m, ctx):
    resto = m.group("resto")
    if re.search(_POR, " " + resto + " ", re.I):
        return _por_campo(resto, ctx, False)
    params = {}
    resto, mc = _tirar(r"\s+(?:e\s+)?(?:com\s+)?(?:o\s+)?" + _alt("contorno", "borda") + r"\s+(?P<c>.+)$", " " + resto)
    if mc:
        oc = _cor(mc.group("c"))
        if oc is None:
            raise ErroComando(f"Não conheço a cor '{_limpa(mc.group('c'))}'. Ex.: preto, azul escuro, #ff0000.")
        params["outline_color"] = oc
    camada, cor = _camada_e_cor(resto, ctx)
    if cor is None:
        if sem_acento(m.group("v")).startswith(("deix", "cor")):
            return None  # 'deixar lotes visível' etc.: não é pintar
        raise ErroComando(f"Não reconheci a cor em '{_limpa(resto)}'. Ex.: azul, verde escuro, #ff0000, 255,0,0.")
    params["layer_name"] = camada
    if cor == "sem":
        params["no_fill"] = True
        return _plano(f"Deixar '{camada}' sem preenchimento (só o contorno)", "update_symbol", params)
    params["color"] = cor
    extra = f" com contorno {params['outline_color']}" if "outline_color" in params else ""
    return _plano(f"Pintar '{camada}' de {cor}{extra}", "update_symbol", params)


# --- rótulos
N_ROTULO = _alt("rótulo", "rótulos", "rotulo", "rotulos", "etiqueta", "etiquetas", "label", "labels")
V_SUMIR = _alt("desligar", "desligue", "desliga", "desativar", "desative", "esconder", "esconda",
               "ocultar", "oculte", "apagar", "apague", "sem")


@comando(rf"(?:{V_LIMPAR}|{V_SUMIR})\s+{ART}{N_ROTULO}(?P<resto>.*?)", "tirar rótulos")
def _sem_rotulos(m, ctx):
    camada = _camada_sobra(m.group("resto"), ctx)
    return _plano(f"Desligar os rótulos de '{camada}'", "set_labels",
                  {"layer_name": camada, "enabled": False})


_V_ROTULAR = _alt("ligar", "ligue", "ativar", "ative", "mostrar", "mostre", "exibir", "exiba")


@comando(rf"(?:(?:{V_CRIAR}|{V_AJUSTAR}|{_V_ROTULAR})\s+{ART}{N_ROTULO}|"
         + _alt("rotular", "rotule", "rotula", "etiquetar", "etiquete") + rf"|{ART}{N_ROTULO})(?P<resto>.*?)",
         'rótulos com "nome"')
def _rotulos(m, ctx):
    resto = " " + m.group("resto") + " "
    params = {}
    resto, mt = _tirar(r"\s,?\s*(?:com\s+|de\s+|e\s+)?" + _alt("tamanho", "fonte", "letra") + r"\s+(?:de\s+)?(\d+(?:[.,]\d+)?)(?=\s)", resto)
    if mt:
        params["size"] = _num(mt.group(1))
    resto, mb = _tirar(r"\s,?\s*(?:em\s+|com\s+|e\s+)?" + _alt("negrito", "bold") + r"(?=\s)", resto)
    if mb:
        params["bold"] = True
    resto, mh = _tirar(r"\s,?\s*(?:e\s+)?" + _alt("sem halo", "sem contorno", "sem fundo", "sem borda") + r"(?=\s)", resto)
    if mh:
        params["buffer"] = False
    resto, mcr = _tirar(r"\s,?\s*(?:na\s+|em\s+|de\s+|e\s+|com\s+)?" + _k("cor") + r"\s+(?P<c>[\w#,\- ]+?)(?=\s+(?:em|na|no|de|da|do|com)\s|\s*$)", resto)
    if mcr:
        c = _cor(mcr.group("c"))
        if c is None:
            raise ErroComando(f"Não conheço a cor '{mcr.group('c').strip()}'.")
        params["color"] = c
    resto = " ".join(resto.split())
    camada = campo_txt = None
    erro = None
    mA = re.fullmatch(rf"(?:{_PREP}\s+)?{ART}(?:{_k('camada')}\s+)?(?P<cam>.+?)\s+(?:com|por|pelo|pela|usando|mostrando|{_k('do campo')}|{_k('da coluna')})\s+(?:{ART})?(?:{N_CAMPO}\s+)?(?P<campo>.+)", resto, re.I)
    if mA:
        try:
            camada, campo_txt = _camada(mA.group("cam"), ctx), mA.group("campo")
        except ErroComando as e:
            erro = e
    if camada is None:
        r2, cam = _separar_camada(resto, ctx)
        if cam is None and erro is not None:
            raise erro
        camada = _ou_ativa(cam, ctx)
        campo_txt = re.sub(rf"^(?:(?:com|de|do|da|dos|das|por|pelo|pela|usando|mostrando)\s+)?(?:{ART})?(?:{N_CAMPO}\s+)?", "", r2.strip(), flags=re.I)
    bruto = (campo_txt or "").strip()
    if re.search(r"\|\||[()+$]", bruto) or bruto.count('"') > 2:
        campo = bruto  # expressão QGIS: usa como veio
    elif re.fullmatch(r'"[^"]+"', bruto):
        campo = _campo(bruto[1:-1], camada, ctx)
    else:
        raise ErroComando(MSG_ASPAS.format('rótulos com "nome"'))
    params.update(layer_name=camada, field=campo)
    extra = []
    if "size" in params:
        extra.append(f"tamanho {params['size']:g}")
    if params.get("bold"):
        extra.append("negrito")
    if "color" in params:
        extra.append(f"cor {params['color']}")
    ex = f" ({', '.join(extra)})" if extra else ""
    return _plano(f"Rótulos de '{camada}' com '{campo}'{ex}", "set_labels", params)


# --- mapa de fundo
_FUNDOS = [
    (_alt("google satélite", "google satelite", "satélite do google", "satelite do google",
          "satélite google", "satelite google", "google earth", "imagem do google",
          "imagem de satélite do google", "imagem de satelite do google"), "google_satellite", "satélite do Google"),
    (_alt("google híbrido", "google hibrido", "híbrido", "hibrido", "satélite com ruas",
          "satelite com ruas"), "google_hybrid", "satélite com ruas (Google)"),
    (_alt("google maps", "google", "mapa do google"), "google_maps", "Google Maps"),
    (_alt("satélite", "satelite", "imagem de satélite", "imagem de satelite", "imagem", "esri",
          "foto aérea", "foto aerea", "ortofoto"), "esri_satellite", "satélite (Esri)"),
    (_alt("topográfico", "topografico", "topo", "relevo"), "esri_topo", "topográfico (Esri)"),
    (_alt("claro", "cinza", "light", "neutro", "branco"), "carto_light", "claro (Carto)"),
    (_alt("escuro", "dark", "preto", "noturno"), "carto_dark", "escuro (Carto)"),
    (_alt("osm", "openstreetmap", "open street map", "ruas", "padrão", "padrao", "normal"), "osm", "OpenStreetMap"),
]


def _qual_fundo(f):
    f = re.sub(rf"^(?:(?:d[eo]|com|em|o|a)\s+)+", "", " ".join(f.split()), flags=re.I)
    f = re.sub(r"\s+(?:" + _alt("de fundo", "no fundo", "como fundo") + r")$", "", f, flags=re.I)
    for pad, chave, nome in _FUNDOS:
        if re.fullmatch(rf"(?:{pad})", f, re.I):
            return chave, nome
    return None


@comando(rf"(?:(?:{V_CRIAR}|{V_AJUSTAR}|" + _alt("carregar", "carregue", "abrir", "abra") + r")\s+)?(?:"
         + ART + r")?(?:" + _alt("mapa de fundo", "mapa base", "fundo", "basemap", "camada de fundo")
         + r")(?:\s+(?P<f>.+?))?", "mapa de fundo satélite")
def _fundo(m, ctx):
    f = (m.group("f") or "").strip()
    achado = _qual_fundo(f) if f else ("osm", "OpenStreetMap")
    if achado is None:
        raise ErroComando("Mapa de fundo desconhecido. Opções: satélite, google satélite, híbrido, "
                          "google maps, osm, topográfico, claro, escuro.")
    return _plano(f"Adicionar mapa de fundo {achado[1]}", "add_basemap", {"source": achado[0]})


@comando(rf"(?:{V_CRIAR}|{V_AJUSTAR}|" + _alt("carregar", "carregue") + r")\s+(?:" + ART + r")?(?P<f>(?:"
         + _alt("imagem de satélite", "imagem de satelite", "satélite", "satelite", "google satélite",
                "google satelite", "google maps", "google híbrido", "google hibrido", "openstreetmap",
                "osm", "ortofoto", "foto aérea", "foto aerea")
         + r")(?:\s+(?:d[eo]\s+)?google)?(?:\s+" + _alt("de fundo", "no fundo", "como fundo") + r")?)",
         "colocar imagem de satélite do google")
def _fundo2(m, ctx):
    achado = _qual_fundo(m.group("f"))
    if achado is None:
        return None
    return _plano(f"Adicionar mapa de fundo {achado[1]}", "add_basemap", {"source": achado[0]})


# --- visualização do mapa
@comando(r"(?P<v>" + _alt("zoom", "dar zoom", "dê zoom", "enquadrar", "enquadre", "ver", "mostrar",
                          "mostre", "afastar", "afaste") + r")\s+(?:" + _alt("total", "geral", "em tudo", "tudo",
         "no projeto", "no projeto todo", "em todas as camadas", "todas as camadas", "o mapa todo",
         "o mapa inteiro", "extensão total", "extensao total", "completo") + ")",
         "zoom total", primeiro=True)
def _zoom_total(m, ctx):
    t = sem_acento(m.group(0))
    if t.startswith("mostr") and "camadas" in t:
        return None  # 'mostrar todas as camadas' é visibilidade
    return _plano("Mostrar todas as camadas no mapa", "zoom_full", {})


@comando(r"(?:(?:" + V_AJUSTAR + "|" + _alt("ir para", "vá para", "zoom na", "zoom em", "zoom para")
         + r")\s+)?(?:" + ART + r")?" + _k("escala") + r"\s+(?:(?:para|pra|de|em)\s+)?(?:1\s*[:/]\s*)?(?P<n>\d[\d.,]*)\s*(?P<mil>mil)?",
         "escala 1:5000", primeiro=True)
def _escala_mapa(m, ctx):
    n = m.group("n").replace(".", "").replace(",", ".")
    v = float(n) * (1000 if m.group("mil") else 1)
    return _plano(f"Mudar a escala do mapa para 1:{int(v):,}".replace(",", "."), "set_scale", {"scale": v})


@comando(r"(?P<v>" + _alt("trazer", "traga", "traz", "subir", "suba", "sobe", "mandar", "mande", "manda",
                          "enviar", "envie", "levar", "leve", "descer", "desça", "desce", "mover", "mova",
                          "move", "colocar", "coloque", "jogar", "jogue")
         + r")\s+" + ART + "(?:(?:" + _k("camada") + r"\s+)?(?P<camada>.+?)\s+)?(?P<d>"
         + _alt("para frente", "pra frente", "para a frente", "à frente", "na frente", "para cima",
                "pra cima", "para o topo", "pro topo", "no topo", "em cima", "por cima", "para trás",
                "para tras", "pra trás", "pra tras", "para baixo", "pra baixo", "para o fundo",
                "pro fundo", "no fundo", "atrás", "por baixo", "embaixo", "uma posição acima",
                "uma posição abaixo", "um nível acima", "um nível abaixo") + ")",
         "trazer para frente")
def _ordem(m, ctx):
    camada = _camada(m.group("camada") or "", ctx)
    d = sem_acento(m.group("d"))
    if "posicao" in d or "nivel" in d:
        pos = "up" if "acima" in d else "down"
    elif any(k in d for k in ("tras", "baixo", "fundo")):
        pos = "bottom"
    else:
        pos = "top"
    nomes = {"top": "para a frente", "bottom": "para trás", "up": "uma posição acima",
             "down": "uma posição abaixo"}
    return _plano(f"Mover '{camada}' {nomes[pos]}", "move_layer", {"layer_name": camada, "position": pos})


@comando(_alt("salvar o projeto", "salve o projeto", "salva o projeto", "salvar projeto", "salve projeto",
              "gravar o projeto", "grave o projeto", "gravar projeto")
         + r"(?:\s+(?:em|como|no arquivo)\s+(?P<p>.+?))?", "salvar projeto", primeiro=True)
def _salvar_projeto(m, ctx):
    params = {"path": _limpa(m.group("p"))} if m.group("p") else {}
    return _plano("Salvar o projeto" + (f" em {params['path']}" if params else ""), "save_project", params)


# --- layouts
N_LAYOUT = _alt("layout", "layouts", "leiaute", "prancha", "pranchas", "mapa para impressão",
                "mapa para impressao", "mapa para imprimir", "folha de impressão", "folha de impressao",
                "composição de impressão", "composicao de impressao")
_TAMANHO = r"(?P<pg>[aA][0-5]|carta|letter|of[ií]cio|legal)"
_ORIENT = _alt("paisagem", "horizontal", "deitado", "deitada", "retrato", "vertical", "em pé", "em pe")


def _layout_ctx(nome, ctx):
    layouts = ctx.get("layouts")
    if layouts is None:
        return _limpa(nome)
    return _achar(nome, layouts, "o layout")


@comando(r"(?:" + V_CRIAR + "|" + _alt("montar", "monte", "monta", "preparar", "prepare", "prepara")
         + r")\s+(?:" + ART + r")?(?:" + _alt("novo", "nova") + r"\s+)?" + N_LAYOUT + r"(?P<resto>.*?)",
         "criar layout A4 com título Mapa de Lotes")
def _criar_layout(m, ctx):
    resto = " " + m.group("resto") + " "
    params = {}
    for chave, pal in (("subtitle", _alt("subtítulo", "subtitulo")), ("title", _alt("título", "titulo"))):
        mt = re.search(r"\s(?:com\s+|e\s+)?(?:o\s+)?" + pal + r"\s+(?:de\s+)?[\"“'](?P<t>.+?)[\"”']", resto, re.I)
        if mt:
            params[chave] = mt.group("t").strip()
            resto = resto[:mt.start()] + " " + resto[mt.end():]
    resto, mp = _tirar(r"\s(?:em\s+|tamanho\s+|folha\s+|papel\s+|no\s+)?" + _TAMANHO + r"(?=[\s,])", resto)
    if mp:
        pg = sem_acento(mp.group("pg"))
        params["page_size"] = {"carta": "Letter", "letter": "Letter", "oficio": "Legal",
                               "legal": "Legal"}.get(pg, pg.upper())
    resto, mo = _tirar(r"\s(?:em\s+|no\s+formato\s+|modo\s+|na\s+)?(?P<o>" + _ORIENT + r")(?=[\s,])", resto)
    if mo:
        o = sem_acento(mo.group("o"))
        params["orientation"] = "portrait" if o in ("retrato", "vertical", "em pe") else "landscape"
    resto, msimples = _tirar(r"\s" + _alt("só o mapa", "só com o mapa", "so o mapa", "simples", "limpo",
                                          "sem nada", "sem enfeites") + r"(?=[\s,])", resto)
    if msimples:
        params.update(legend=False, scalebar=False, north_arrow=False)
    for chave, pad in (("legend", _alt("legenda")),
                       ("scalebar", _alt("barra de escala", "escala")),
                       ("north_arrow", _alt("seta de norte", "seta norte", "rosa dos ventos", "norte"))):
        resto, mx = _tirar(r"\s,?\s*(?:e\s+)?sem\s+(?:" + ART + r")?(?:" + pad + r")(?=[\s,])", resto)
        if mx:
            params[chave] = False
        resto, _ = _tirar(r"\s,?\s*(?:com\s+|e\s+)?(?:" + ART + r")?(?:" + pad + r")(?=[\s,])", resto)
    if "title" not in params:
        mt = re.search(r"\s(?:com\s+|e\s+)?(?:o\s+)?" + _alt("título", "titulo") + r"\s+(?:de\s+)?(?P<t>.+?)\s*$", resto, re.I)
        if mt:
            params["title"] = _limpa(mt.group("t").strip(" ,"))
            resto = resto[:mt.start()]
    mn = re.search(r"\s(?:" + _alt("chamado", "chamada", "com nome", "com o nome", "nomeado", "de nome")
                   + r")\s+(?P<n>.+?)\s*$", resto, re.I)
    if mn:
        params["layout_name"] = _limpa(mn.group("n").strip(" ,"))
        resto = resto[:mn.start()]
    sobra = re.sub(r"[,\s]+", " ", re.sub(r"\b(?:com|e|em|o|a|um|uma)\b", " ", resto, flags=re.I)).strip()
    if sobra and "layout_name" not in params:
        params["layout_name"] = _limpa(sobra)
    pagina = f"{params.get('page_size', 'A4')} {'retrato' if params.get('orientation') == 'portrait' else 'paisagem'}"
    itens = [n for k, n in (("legend", "legenda"), ("scalebar", "escala"), ("north_arrow", "norte"))
             if params.get(k, True)]
    tit = f", título '{params['title']}'" if params.get("title") else ""
    com = f", com {', '.join(itens)}" if itens else ", só o mapa"
    nome = f" '{params['layout_name']}'" if params.get("layout_name") else ""
    return _plano(f"Criar layout{nome} {pagina}{tit}{com}", "create_print_layout", params)


_FORMATOS = {"pdf": "pdf", "png": "png", "jpg": "jpg", "jpeg": "jpg", "tif": "tif", "tiff": "tif",
             "svg": "svg", "imagem": "png", "figura": "png"}
_CAMINHO = r"(?P<p>[A-Za-z]:[\\/].*|\\\\.+|~[\\/].*)"
_V_EXPORTAR = _alt("exportar", "exporte", "exporta", "salvar", "salve", "salva", "gerar", "gere", "gera",
                   "imprimir", "imprima", "imprime", "tirar", "tire")


@comando(r"(?P<v>" + _V_EXPORTAR + r")\s+(?P<resto>.*?(?:" + N_LAYOUT + "|"
         + _alt("mapa", "pdf", "png", "jpg", "imagem", "print", "captura") + r").*?)",
         "exportar layout em pdf")
def _exportar(m, ctx):
    resto = " " + m.group("resto") + " "
    params = {}
    resto, mc = _tirar(r"\s(?:em|para|pra|na pasta|no arquivo|no caminho|como|no)\s+" + _CAMINHO + r"\s*$", resto)
    if mc:
        params["output_path"] = mc.group("p").strip().strip('"')
        ext = os.path.splitext(params["output_path"])[1].lower().lstrip(".")
    else:
        ext = ""
    resto, md = _tirar(r"\s(?:com\s+|em\s+)?(\d+)\s*dpi(?=\s)", resto)
    if md:
        params["dpi"] = int(md.group(1))
    fmt = _FORMATOS.get(ext)
    for k in sorted(_FORMATOS, key=len, reverse=True):
        resto, mf = _tirar(r"\s(?:(?:em|para|como|no formato|formato|de|do|um|uma)\s+)?" + k + r"(?=\s)", resto)
        if mf:
            fmt = fmt or _FORMATOS[k]
    eh_layout = re.search(N_LAYOUT, resto, re.I)
    imprimir = sem_acento(m.group("v")).startswith("impri")
    if not (fmt or eh_layout or imprimir or re.search(_alt("print", "captura"), resto, re.I)):
        return None  # 'gerar mapa temático por RA': não é exportação
    if re.search(_alt("print", "captura"), resto, re.I):
        fmt = fmt or "png"
    resto = re.sub(N_LAYOUT, " ", resto, flags=re.I)
    layouts = ctx.get("layouts") or []
    candidato = re.sub(rf"^{_PREPS_SOLTAS}", "", " ".join(resto.split()) + " ", flags=re.I).strip()
    candidato = re.sub(rf"^(?:{ART})", "", candidato, flags=re.I).strip()
    for lay in layouts:  # layout chamado 'Mapa', 'Mapa Geral'...
        if candidato and _normal(candidato) == _normal(lay):
            resto = " "
            params["layout_name"] = lay
    resto = re.sub(r"(?<!\w)" + _alt("do mapa", "o mapa", "mapa", "print", "captura", "da tela", "tela")
                   + r"(?!\w)", " ", resto, flags=re.I)
    nome = re.sub(rf"^{_PREPS_SOLTAS}", "", " ".join(resto.split()) + " ", flags=re.I).strip()
    nome = re.sub(rf"(?:^|\s+)(?:{_PREP}|com|e)$", "", nome, flags=re.I).strip()
    nome = re.sub(rf"^(?:{ART})", "", nome, flags=re.I).strip()
    if "layout_name" in params:
        pass
    elif nome:
        params["layout_name"] = _layout_ctx(nome, ctx)
    elif layouts or eh_layout:
        if len(layouts) > 1:
            raise ErroComando("Há mais de um layout; diga qual: " + ", ".join(repr(l) for l in layouts) + ".")
        if layouts:
            params["layout_name"] = layouts[0]
    fmt = fmt or "pdf"
    if "layout_name" in params or eh_layout:
        params["format"] = fmt
        alvo = f"o layout '{params['layout_name']}'" if params.get("layout_name") else "o layout"
        return _plano(f"Exportar {alvo} em {fmt.upper()}", "export_layout", params)
    if fmt == "pdf":  # projeto sem layout: monta um padrão e exporta
        return {"descricao": "Criar um layout A4 (mapa, legenda, escala, norte) e exportar em PDF",
                "destrutivo": False,
                "steps": [{"action": "create_print_layout",
                           "params": {"layout_name": "Mapa", "open_designer": False}},
                          {"action": "export_layout",
                           "params": dict(params, layout_name="Mapa", format="pdf")}]}
    params.pop("dpi", None)
    return _plano("Salvar o mapa atual como imagem", "export_map_image", params)


@comando(r"(?:" + _alt("abrir", "abra", "abre", "editar", "edite", "edita", "ver", "mostrar", "mostre")
         + r")\s+(?:" + ART + r")?" + N_LAYOUT + r"(?P<resto>.*?)", "abrir layout Mapa", primeiro=True)
def _abrir_layout(m, ctx):
    nome = re.sub(rf"^\s*(?:{ART})", "", m.group("resto")).strip()
    params = {"layout_name": _layout_ctx(nome, ctx)} if nome else {}
    alvo = f" '{params['layout_name']}'" if params else ""
    return _plano(f"Abrir o layout{alvo}", "open_layout", params)


@comando(r"(?:" + V_LISTAR + r"\s+" + ART + "|" + _alt("quantos", "quais") + r"\s+(?:(?:os|as)\s+)?)"
         + _alt("layouts", "leiautes", "pranchas") + r"(?:\s+.*)?", "listar layouts")
def _listar_layouts(m, ctx):
    return _plano("Listar os layouts do projeto", "list_print_layouts", {})


@comando(V_APAGAR + r"\s+" + ART + N_LAYOUT + r"\s+(?P<nome>.+?)", "apagar layout Mapa 2")
def _apagar_layout(m, ctx):
    nome = _layout_ctx(m.group("nome"), ctx)
    return _plano(f"Apagar o layout '{nome}'", "remove_layout", {"layout_name": nome}, destrutivo=True)


@comando(r"(?:" + V_CRIAR + "|" + V_AJUSTAR + "|" + _alt("acrescentar", "acrescente", "acrescenta")
         + r")\s+(?:" + ART + r")?(?P<item>" + _alt("legenda", "barra de escala", "escala", "seta de norte",
                                                    "seta norte", "norte", "rosa dos ventos", "título",
                                                    "titulo", "texto", "nota", "fonte")
         + r")(?P<resto>(?:\s.*?)?)", "adicionar legenda no layout")
def _item_layout(m, ctx):
    it = sem_acento(m.group("item"))
    item = ("legend" if it == "legenda" else "scalebar" if "escala" in it
            else "north_arrow" if ("norte" in it or "rosa" in it) else "title" if "titulo" in it else "text")
    resto = " " + m.group("resto") + " "
    params = {"item": item}
    mtxt = re.search(r"[\"“'](?P<t>.+?)[\"”']", resto)
    if mtxt:
        params["text"] = mtxt.group("t")
        resto = resto[:mtxt.start()] + " " + resto[mtxt.end():]
    ml = re.search(r"\s(?:n[oa]|a[oa]|em|para)\s+(?:" + ART + r")?" + N_LAYOUT + r"(?:\s+(?P<n>.+?))?\s*$", resto, re.I)
    if ml:
        if ml.group("n"):
            params["layout_name"] = _layout_ctx(ml.group("n"), ctx)
        resto = resto[:ml.start()]
    elif not ctx.get("layouts"):
        return None  # sem layout no projeto e sem 'no layout': não é item de layout
    if item in ("title", "text") and "text" not in params:
        t = re.sub(r"^\s*(?::|de|com|dizendo)?\s*", "", resto).strip()
        if not t:
            raise ErroComando('Diga o texto entre aspas. Ex.: adicionar título "Coleta 2026" no layout.')
        params["text"] = _limpa(t)
    nomes = {"legend": "a legenda", "scalebar": "a barra de escala", "north_arrow": "a seta de norte",
             "title": "o título", "text": "o texto"}
    alvo = f" '{params['layout_name']}'" if params.get("layout_name") else ""
    return _plano(f"Adicionar {nomes[item]} no layout{alvo}", "add_layout_item", params)


# ======================================================== geoprocessamento
# Entrada = camada selecionada. A "outra" camada (molde) é citada pelo nome.

def _outra(nome, ctx):
    """Segunda camada (molde/referência): qualquer camada do projeto, menos a selecionada."""
    nome = _limpa(re.sub(rf"^(?:{ART})?(?:{_k('camada')}\s+)?", "", (nome or "").strip(), flags=re.I))
    if not nome:
        raise ErroComando("Diga a outra camada. Ex.: recortar pela camada Regiões.")
    achada = _achar(nome, ctx.get("camadas", []), "a camada")
    if achada == ctx.get("ativa"):
        raise ErroComando(f"A outra camada não pode ser a própria selecionada ('{achada}').")
    return achada


def _dist(txt):
    """'50 m', '2 km', '1,5 quilômetros', '300' -> metros (float) ou None."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|quil[oô]metros?|m|metros?)?(?=\s|$|,)", txt or "", re.I)
    if not m:
        return None
    v = _num(m.group(1))
    return v * 1000 if m.group(2) and sem_acento(m.group(2)).startswith(("km", "quil")) else v


_SO_SEL = _alt("só nas selecionadas", "só das selecionadas", "só as selecionadas", "nas selecionadas",
               "das selecionadas", "apenas nas selecionadas", "só da seleção", "só na seleção",
               "da seleção", "só os selecionados", "nos selecionados")
_COMO = r"\s+(?:como|" + _k("com o nome") + "|" + _k("com nome") + "|" + _k("chamada") + "|" + _k("chamado") + r")\s+(?P<saida>.+?)\s*$"


def _opcoes_geo(resto):
    """Tira 'só nas selecionadas' e 'como NOME' do texto. Devolve (resto, params extras)."""
    extra = {}
    resto = " " + resto + " "
    resto, ms = _tirar(r"\s,?\s*\(?" + _SO_SEL + r"\)?(?=\s)", resto)
    if ms:
        extra["only_selected"] = True
    mc = re.search(_COMO, resto, re.I)
    if mc:
        extra["output_name"] = _limpa(mc.group("saida"))
        resto = resto[:mc.start()]
    return " ".join(resto.split()), extra


def _geo(descricao, tool, ctx, extra, **params):
    camada = _ativa(ctx)
    p = {"tool": tool, "layer_name": camada}
    p.update({k: v for k, v in params.items() if v is not None})
    p.update(extra)
    sel = " (só nas selecionadas)" if extra.get("only_selected") else ""
    return _plano(f"{descricao} de '{camada}'{sel}", "geoprocess", p)


def _sem_camada_propria(txt, ctx):
    """O que sobrou da frase só pode ser a própria camada selecionada ('nos lotes',
    'na camada lotes'); outra camada ou palavra desconhecida dá erro (regra 1)."""
    return _camada_sobra(txt or "", ctx)


@comando(r"(?:(?:" + V_CRIAR + r")\s+)?(?:" + ART + r")?(?:" + _alt("buffer", "área de influência", "area de influencia",
         "zona de influência", "faixa", "entorno", "raio") + r")(?:\s+(?P<resto>.+?))?", "buffer de 50 m")
def _buffer(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto") or "")
    resto, md = _tirar(r"\s,?\s*(?:e\s+)?(?:" + _alt("dissolvido", "dissolvida", "dissolver", "unido", "unida",
                       "juntando tudo", "juntando", "unificado", "sem sobreposição") + r")(?=\s|$)", " " + resto + " ")
    d = _dist(resto)
    if d is None:
        raise ErroComando("Diga a distância. Ex.: buffer de 50 m · buffer de 2 km dissolvido.")
    _sem_camada_propria(re.sub(r"\d+(?:[.,]\d+)?\s*\w*", " ", resto).strip(), ctx)
    return _geo(f"Buffer de {d:g} m{' dissolvido' if md else ''}", "buffer", ctx, extra,
                distance=d, dissolve=True if md else None)


@comando(r"(?:" + _alt("dissolver", "dissolva", "dissolve", "juntar tudo", "junte tudo", "unir tudo",
                       "una tudo", "agrupar geometrias", "agrupe as geometrias", "juntar as feições",
                       "juntar feições", "fundir", "funda") + r")(?P<resto>(?:\s.*?)?)", 'dissolver por "bairro"')
def _dissolver(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    if re.search(r"\b(?:por|pelo|pela|usando)\b", resto, re.I) or _aspas(resto):
        nomes = _exige_aspas(resto, 'dissolver por "bairro"')
        camada = _ativa(ctx)
        campos = [_campo(n, camada, ctx) for n in nomes]
        txt = ", ".join(f"'{c}'" for c in campos)
        return _geo(f"Dissolver por {txt}", "dissolve", ctx, extra,
                    field=campos if len(campos) > 1 else campos[0])
    return _geo("Dissolver tudo numa geometria", "dissolve", ctx, extra)


_MOLDE = r"\s+(?:(?:" + _alt("pela", "pelo", "por", "com", "usando", "contra", "em relação a", "e") + r")\s+)?(?P<outra>.+?)"


@comando(r"(?:" + _alt("recortar", "recorte", "recorta", "cortar", "corte", "clip", "clipar") + r")(?:\s+"
         + ART + r"(?:" + _k("camada") + r"|" + N_FEICAO + r"))?" + _MOLDE, "recortar pela camada Regiões")
def _recortar(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    o = _outra(outra, ctx)
    return _geo(f"Recortar pelo limite de '{o}'", "clip", ctx, extra, overlay=o)


@comando(r"(?:" + _alt("interseção", "intersecção", "intersecao", "interseccao", "intersectar", "intersecte",
                       "fazer interseção", "faça a interseção", "cruzar", "cruze", "sobrepor", "sobreponha")
         + r")" + _MOLDE, "interseção com Regiões")
def _intersecao(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    if re.search(_alt("atributos", "dados", "campos"), outra, re.I):
        return None  # 'cruzar atributos com X' é junção espacial
    o = _outra(outra, ctx)
    return _geo(f"Interseção com '{o}'", "intersection", ctx, extra, overlay=o)


@comando(r"(?:" + _alt("diferença", "diferenca", "subtrair", "subtraia", "subtrai", "apagar a parte que está em",
                       "tirar a parte que está em", "tirar a área de", "remover a área de", "excluir a área de",
                       "apagar o que está dentro de", "tirar o que está dentro de", "descontar") + r")" + _MOLDE,
         "diferença com Regiões", primeiro=True)
def _diferenca(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    o = _outra(outra, ctx)
    return _geo(f"Tirar a parte que cai em '{o}'", "difference", ctx, extra, overlay=o)


@comando(r"(?:" + _alt("união com", "uniao com", "unir com", "una com", "fazer união com") + r")\s+(?P<outra>.+?)",
         "união com Regiões")
def _uniao(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    o = _outra(outra, ctx)
    return _geo(f"União com '{o}'", "union", ctx, extra, overlay=o)


@comando(r"(?:" + _alt("mesclar", "mescle", "mescla", "juntar", "junte", "junta", "combinar", "combine", "somar",
                       "agregar") + r")\s+(?:com|a|às|as)\s+(?:" + ART + r")?(?:" + _alt("camadas", "camada") + r"\s+)?(?P<outras>.+?)",
         "mesclar com lotes_sul e lotes_norte")
def _mesclar(m, ctx):
    outras, extra = _opcoes_geo(m.group("outras"))
    if re.search(_alt("atributos", "dados", "campos", "mais próximo", "mais proximo"), outras, re.I):
        return None
    nomes = [_outra(n, ctx) for n in re.split(r"\s*,\s*|\s+e\s+", outras) if n.strip()]
    txt = ", ".join(f"'{n}'" for n in nomes)
    return _geo(f"Mesclar com {txt}", "merge", ctx, extra, overlays=nomes)


_CRS_NOMES = [
    (_alt("sirgas 2000 utm 23s", "sirgas utm 23s", "utm 23s", "utm 23 sul", "utm zona 23s", "utm 23"), "EPSG:31983"),
    (_alt("sirgas 2000 utm 22s", "sirgas utm 22s", "utm 22s", "utm 22 sul", "utm 22"), "EPSG:31982"),
    (_alt("sirgas 2000 utm 24s", "sirgas utm 24s", "utm 24s", "utm 24 sul", "utm 24"), "EPSG:31984"),
    (_alt("wgs84", "wgs 84", "graus", "lat long", "latitude e longitude", "geográfica", "geografica",
          "gps", "google earth"), "EPSG:4326"),
    (_alt("sirgas 2000", "sirgas", "sirgas geográfico"), "EPSG:4674"),
    (_alt("web mercator", "pseudo mercator", "google maps"), "EPSG:3857"),
]


def _crs_txt(txt):
    t = re.sub(rf"^(?:{ART})?(?:{_alt('o sistema', 'sistema', 'crs', 'projeção', 'projecao', 'srid')}\s+)?", "",
               _limpa(txt), flags=re.I).strip()
    m = re.fullmatch(r"(?:epsg\s*[: ]?\s*)?(\d{4,6})", t, re.I)
    if m:
        return f"EPSG:{m.group(1)}"
    for pad, cod in _CRS_NOMES:
        if re.fullmatch(rf"(?:{pad})", t, re.I):
            return cod
    return None


@comando(r"(?:" + _alt("reprojetar", "reprojete", "reprojeta", "converter o sistema", "mudar o sistema",
                       "mude o sistema", "mudar a projeção", "mude a projeção", "converter as coordenadas",
                       "transformar o sistema", "converter", "converta", "transformar", "transforme")
         + r")(?:\s+" + ART + _k("camada") + r")?\s+(?:para|pra|em)\s+(?P<crs>.+?)", "reprojetar para 31983")
def _reprojetar(m, ctx):
    crs_txt, extra = _opcoes_geo(m.group("crs"))
    crs = _crs_txt(crs_txt)
    if crs is None:
        verbo = sem_acento(m.group(0)).split()[0]
        if verbo.startswith(("convert", "transform")):
            return None  # 'converter polígonos em linhas' etc.
        raise ErroComando("Sistema não reconhecido. Ex.: reprojetar para 31983 · para SIRGAS 2000 UTM 23S · "
                          "para WGS84.")
    return _geo(f"Reprojetar para {crs}", "reproject", ctx, extra, crs=crs)


@comando(r"(?:(?:" + V_CRIAR + r")\s+)?(?:" + ART + r")?(?:" + _alt("centroides", "centróides", "centroide",
         "centróide", "pontos no centro", "ponto no centro", "ponto central", "pontos centrais") + r")(?P<resto>(?:\s.*?)?)",
         "gerar centroides")
def _centroides(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    return _geo("Gerar um ponto no centro de cada feição", "centroids", ctx, extra)


@comando(r"(?:(?:" + V_CRIAR + r")\s+)?(?:" + ART + r")?(?:" + _alt("fecho convexo", "envoltória", "envoltoria",
         "envoltória convexa", "polígono envolvente", "poligono envolvente", "contorno externo") + r")(?P<resto>(?:\s.*?)?)",
         "envoltória de tudo")
def _envoltoria(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    if re.search(_alt("de tudo", "geral", "única", "unica", "do conjunto", "de todas", "total"), resto, re.I):
        return _geo("Envoltória de todas as feições juntas", "convex_hull_all", ctx, extra)
    return _geo("Envoltória de cada feição", "convex_hull", ctx, extra)


@comando(r"(?:" + _alt("simplificar", "simplifique", "simplifica", "generalizar", "generalize") + r")(?P<resto>(?:\s.*?)?)",
         "simplificar 5 m")
def _simplificar(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    d = _dist(resto)
    if d is None:
        raise ErroComando("Diga a tolerância. Ex.: simplificar 5 m.")
    return _geo(f"Simplificar com tolerância de {d:g} m", "simplify", ctx, extra, tolerance=d)


@comando(r"(?:" + _alt("junção espacial com", "juncao espacial com", "junção espacial de", "join espacial com",
                       "juntar atributos de", "juntar os atributos de", "trazer atributos de", "trazer os atributos de",
                       "trazer os dados de", "trazer dados de", "trazer os campos de", "pegar os atributos de",
                       "pegar atributos de", "pegar os dados de", "cruzar atributos com", "cruzar os atributos com",
                       "cruzar os dados com") + r")\s+(?P<outra>.+?)", "trazer atributos de Regiões")
def _juncao(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    outra, mt = _tirar(r"\s,?\s*\(?" + _alt("todos", "um para muitos", "todas as correspondências", "repetindo")
                       + r"\)?(?=\s|$)", " " + outra + " ")
    o = _outra(outra.strip(), ctx)
    return _geo(f"Trazer os atributos de '{o}' pela localização", "spatial_join", ctx, extra,
                overlay=o, one_to_one=False if mt else None)


@comando(r"(?:" + _alt("mais próximo de", "mais proximo de", "o mais próximo de", "a mais próxima de",
                       "juntar pelo mais próximo de", "juntar ao mais próximo de", "ligar ao mais próximo de",
                       "distância até", "distancia ate", "distância para", "distância ao mais próximo de",
                       "vizinho mais próximo em", "trazer o mais próximo de") + r")\s+(?P<outra>.+?)",
         "mais próximo de pontos_coleta")
def _mais_proximo(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    o = _outra(outra, ctx)
    return _geo(f"Achar o mais próximo em '{o}' (com a distância)", "nearest_join", ctx, extra, overlay=o)


@comando(r"(?:" + _alt("contar", "conte", "conta", "quantos", "quantas") + r")\s+(?:" + ART + r")?(?:"
         + _alt("pontos", "feições", "feicoes", "registros", "itens") + r"\s+)?(?:(?:de|da|do|dos|das)\s+)?(?:"
         + _k("camada") + r"\s+)?(?P<outra>.+?)\s+(?:" + _alt("em cada", "dentro de cada", "por", "tem em cada",
         "há em cada", "caem em cada", "existem em cada") + r")\s+(?:" + _alt("polígono", "poligono", "área",
         "area", "região", "regiao", "feição", "feicao", "setor", "quadra", "lote", "um") + r")",
         "contar pontos de pontos_coleta em cada polígono", primeiro=True)
def _contar_pontos(m, ctx):
    outra, extra = _opcoes_geo(m.group("outra"))
    o = _outra(outra, ctx)
    return _geo(f"Contar quantos '{o}' caem em cada polígono", "count_points", ctx, extra, overlay=o)


def _simples(padrao, tool, descricao, exemplo):
    @comando(padrao + r"(?P<resto>(?:\s.*?)?)", exemplo, primeiro=True)
    def _f(m, ctx):
        resto, extra = _opcoes_geo(m.group("resto"))
        return _geo(descricao, tool, ctx, extra)
    return _f


_simples(r"(?:" + _alt("corrigir", "corrija", "consertar", "conserte", "arrumar", "arrume", "reparar", "repare",
                       "validar e corrigir") + r")\s+(?:" + ART + r")?" + _alt("geometrias", "geometria", "geometrias inválidas"),
         "fix_geometries", "Corrigir as geometrias", "corrigir geometrias")
_simples(r"(?:" + _alt("explodir", "exploda", "separar as partes", "separe as partes", "separar multipartes",
                       "multipartes para partes simples", "multiparte para simples", "desagregar", "desagregue") + r")",
         "single_parts", "Separar as multipartes em feições simples", "explodir multipartes")
_simples(r"(?:" + V_APAGAR + r"|" + _alt("limpar", "limpe") + r")\s+(?:" + ART + r")?(?:" + _alt("geometrias", "feições",
         "feicoes", "registros") + r"\s+)?" + _alt("duplicadas", "duplicados", "repetidas", "repetidos"),
         "delete_duplicates", "Remover geometrias duplicadas", "remover duplicadas")
_simples(r"(?:(?:" + _alt("extrair", "extraia", "gerar", "gere", "criar") + r")\s+)?(?:" + ART + r")?"
         + _alt("vértices", "vertices", "nós dos polígonos"),
         "extract_vertices", "Extrair os vértices", "extrair vértices")
_simples(r"(?:(?:" + _alt("converter", "converta", "transformar", "transforme", "passar") + r")\s+)?(?:" + ART + r")?"
         + _alt("polígonos", "poligonos", "polígono", "poligono") + r"\s+(?:em|para|pra)\s+" + _alt("linhas", "linha"),
         "polygons_to_lines", "Converter polígonos em linhas", "polígonos para linhas")
_simples(r"(?:(?:" + _alt("converter", "converta", "transformar", "transforme", "passar", "fechar") + r")\s+)?(?:" + ART + r")?"
         + _alt("linhas", "linha") + r"\s+(?:em|para|pra)\s+" + _alt("polígonos", "poligonos", "polígono", "poligono"),
         "lines_to_polygons", "Converter linhas em polígonos", "linhas para polígonos")


@comando(r"(?:(?:" + V_CRIAR + r")\s+)?(?:" + ART + r")?(?:" + _alt("grade", "grid", "malha", "quadrícula", "quadricula",
         "grade hexagonal", "malha hexagonal") + r")(?P<resto>(?:\s.*?)?)", "grade de 500 m", primeiro=True)
def _grade(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    extra.pop("only_selected", None)
    d = _dist(resto)
    if d is None:
        raise ErroComando("Diga o tamanho da célula. Ex.: grade de 500 m · grade hexagonal de 1 km.")
    tipo = "hexagon" if re.search(_alt("hexagonal", "hexágonos", "hexagonos", "colmeia"), m.group(0), re.I) else None
    return _geo(f"Grade {'hexagonal ' if tipo else ''}de {d:g} m sobre a extensão", "grid", ctx, extra,
                distance=d, grid_type=tipo)


_RELACOES = [
    (_alt("dentro de", "dentro da", "dentro do", "que estão dentro de", "que estao dentro de", "contidos em",
          "contidas em", "inteiramente em"), "within", "dentro de"),
    (_alt("que tocam", "que encostam em", "que encostam na", "encostando em", "vizinhos de", "vizinhas de"),
     "touches", "que tocam"),
    (_alt("que cruzam", "que atravessam", "atravessando"), "crosses", "que cruzam"),
    (_alt("que contêm", "que contem", "que contém"), "contains", "que contêm"),
    (_alt("fora de", "fora da", "fora do", "que não tocam", "longe de"), "disjoint", "fora de"),
    (_alt("que intersectam", "que cruzam com", "que caem em", "que estão em", "que estao em", "em cima de",
          "sobre", "que pegam", "que tocam em", "dentro ou tocando"), "intersects", "que encostam ou caem em"),
]


@comando(V_SELEC + r"\s+(?:(?:" + _alt("os", "as", "todos os", "todas as", "feições", "feicoes", "as feições",
         "os registros", "os pontos", "os lotes", "as linhas") + r")\s+)*(?P<resto>(?:a\s+até|até|a\s+menos\s+de|"
         r"num\s+raio\s+de|em\s+um\s+raio\s+de|perto\s+de|próximos\s+de|proximos\s+de|próximas\s+de|"
         + "|".join(p for p, _, _ in _RELACOES) + r").+?)", "selecionar dentro de Regiões", primeiro=True)
def _selecionar_local(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    extra.pop("output_name", None)
    md = re.match(r"(?:a\s+até|até|ate|a\s+menos\s+de|num\s+raio\s+de|em\s+um\s+raio\s+de)\s+(?P<d>\d+(?:[.,]\d+)?\s*\w*)\s+(?:de|da|do|dos|das)\s+(?P<o>.+)",
                  resto, re.I)
    camada = _ativa(ctx)
    if md:
        d = _dist(md.group("d"))
        o = _outra(md.group("o"), ctx)
        return _plano(f"Selecionar em '{camada}' as feições a até {d:g} m de '{o}'", "select_by_location",
                      {"layer_name": camada, "overlay": o, "distance": d})
    mp = re.match(r"(?:perto|próximos|proximos|próximas|proximas)\s+(?:de|da|do)\s+(?P<o>.+)", resto, re.I)
    if mp:
        raise ErroComando("Diga a distância. Ex.: selecionar a até 50 m de Vias Principais.")
    for pad, pred, nome in _RELACOES:
        mr = re.match(rf"(?:{pad})\s+(?P<o>.+)", resto, re.I)
        if mr:
            o = _outra(mr.group("o"), ctx)
            return _plano(f"Selecionar em '{camada}' as feições {nome} '{o}'", "select_by_location",
                          {"layer_name": camada, "overlay": o, "predicate": pred})
    return None


# --- consultas
@comando(r"(?:" + _alt("área total", "area total", "qual a área total", "qual a area total", "soma das áreas",
                       "soma das areas", "comprimento total", "extensão total", "extensao total",
                       "qual o comprimento total", "quantos km", "quantos metros", "quantos hectares",
                       "medir", "meça", "medida total") + r")(?P<resto>(?:\s.*?)?)\??", "área total", primeiro=True)
def _medir(m, ctx):
    resto, extra = _opcoes_geo(m.group("resto"))
    _sem_camada_propria(re.sub(rf"^(?:{_PREP}\s+)?", "", resto), ctx) if resto else None
    camada = _ativa(ctx)
    p = {"layer_name": camada}
    if extra.get("only_selected"):
        p["only_selected"] = True
    return _plano(f"Medir área/comprimento total de '{camada}'", "measure_total", p)


@comando(r"(?:" + _alt("estatísticas", "estatisticas", "estatística", "estatistica", "resumo", "resumir", "soma",
                       "média", "media", "mínimo", "minimo", "máximo", "maximo", "total") + r")\s+(?:(?:" + _alt("do campo",
         "da coluna", "de", "do", "da") + r")\s+)?(?P<resto>.+?)", 'estatísticas de "populacao"')
def _estatisticas(m, ctx):
    if not _aspas(m.group("resto")):
        if re.search(_alt("área", "area", "comprimento", "extensão"), m.group("resto"), re.I):
            return None
        raise ErroComando(MSG_ASPAS.format('estatísticas de "populacao"'))
    camada = _ativa(ctx)
    campo = _campo(_aspas(m.group("resto"))[0], camada, ctx)
    return _plano(f"Estatísticas do campo '{campo}' de '{camada}'", "get_field_statistics",
                  {"layer_name": camada, "field": campo})


@comando(r"(?:(?:" + V_LISTAR + r")\s+)?(?:" + ART + r")?(?:" + _alt("valores únicos", "valores unicos",
         "valores distintos", "valores diferentes", "quais valores", "que valores") + r")\s+(?:(?:" + _alt("do campo",
         "da coluna", "de", "do", "da", "tem", "existem em", "há em") + r")\s+)?(?P<resto>.+?)", 'valores únicos de "bairro"')
def _valores(m, ctx):
    nomes = _exige_aspas(m.group("resto"), 'valores únicos de "bairro"')
    camada = _ativa(ctx)
    campo = _campo(nomes[0], camada, ctx)
    return _plano(f"Valores distintos de '{campo}' em '{camada}'", "get_unique_values",
                  {"layer_name": camada, "field": campo, "limit": 200})


# --- gravar camada em arquivo
_FMT_CAMADA = _alt("gpkg", "geopackage", "shp", "shapefile", "geojson", "json", "csv", "kml", "dxf", "xlsx", "excel")


@comando(r"(?:" + _alt("exportar", "exporte", "exporta", "salvar", "salve", "salva", "gravar", "grave", "grava")
         + r")\s+(?P<resto>(?:" + ART + r")?(?:" + _k("camada") + r"|" + _alt("selecionadas", "seleção") + r"|.*?" + _FMT_CAMADA
         + r").*?)", "exportar camada em shapefile", primeiro=True)
def _salvar_camada(m, ctx):
    resto = " " + m.group("resto") + " "
    if re.search(N_LAYOUT, resto, re.I) or \
            re.search(r"\b(?:pdf|png|jpg|jpeg|svg|tif)\b", resto, re.I) or re.search(r"\bprojeto\b", resto, re.I):
        return None  # layout / imagem / projeto têm comando próprio
    if re.search(_alt("edição", "edicao", "edições", "alterações"), resto, re.I):
        return None  # 'salvar edição'
    params = {}
    resto, mc = _tirar(r"\s(?:em|para|pra|na pasta|no arquivo|no caminho|como|no)\s+(?P<p>[A-Za-z]:[\\/].*|\\\\.+|~[\\/].*)\s*$", resto)
    if mc:
        params["output_path"] = mc.group("p").strip().strip('"')
    resto, ms = _tirar(r"\s,?\s*\(?(?:" + _SO_SEL + "|" + _alt("selecionadas", "a seleção", "seleção") + r")\)?(?=\s)", resto)
    if ms:
        params["only_selected"] = True
    mf = re.search(r"(?:^|\s)(?:em\s+|para\s+|como\s+|no\s+formato\s+|formato\s+)?(?P<f>" + _FMT_CAMADA + r")(?=\s|$)", resto, re.I)
    if mf:
        f = sem_acento(mf.group("f"))
        params["format"] = {"geopackage": "gpkg", "shapefile": "shp", "json": "geojson", "excel": "xlsx"}.get(f, f)
        resto = resto[:mf.start()] + " " + resto[mf.end():]
    sobra = re.sub(rf"(?:{ART})?{_k('camada')}|\b(?:em|para|como|no|na|a|o|de|da)\b", " ", resto, flags=re.I).strip()
    if sobra:
        _camada(sobra, ctx)  # só a selecionada
    camada = _ativa(ctx)
    params["layer_name"] = camada
    fmt = params.get("format") or (os.path.splitext(params.get("output_path", ""))[1].lstrip(".") or "gpkg")
    onde = params.get("output_path", "pasta do projeto")
    return _plano(f"Gravar '{camada}' em {fmt.upper()} ({onde})", "save_layer_as", params)


# ============================================================ camadas
# Salvar na pasta do projeto (igual aos outros arquivos), criar, abrir, grupos,
# sistema de coordenadas, estilo e informações.

_V_GUARDAR = _alt("salvar", "salve", "salva", "gravar", "grave", "grava", "guardar", "guarde", "guarda")
_DEST_PROJ = _alt("na pasta do projeto", "para a pasta do projeto", "pra pasta do projeto", "na pasta",
                  "no projeto", "junto do projeto", "junto com o projeto", "igual aos outros",
                  "igual às outras", "igual as outras", "como os outros", "de vez", "permanente",
                  "permanentemente", "em definitivo", "definitivo")
_PERMANENTE = _alt("tornar permanente", "torne permanente", "torna permanente", "deixar permanente",
                   "deixe permanente", "tornar a camada permanente", "torne a camada permanente",
                   "deixar a camada permanente", "deixe a camada permanente")


@comando(r"(?:" + _V_GUARDAR + r"\s+" + ART + r"(?:" + _k("camada") + r"(?P<a>(?:\s.*?)?)|(?P<b>.*?"
         + _DEST_PROJ + r".*?))|" + _PERMANENTE + r"(?P<c>.*?))", "salvar camada na pasta do projeto",
         primeiro=True)
def _salvar_no_projeto(m, ctx):
    resto = " " + " ".join(g for g in (m.group("a"), m.group("b"), m.group("c")) if g) + " "
    if re.search(_FMT_CAMADA + r"(?=\s)", resto, re.I) or re.search(r"[A-Za-z]:[\\/]|\\\\", resto) or \
            re.search(N_LAYOUT + "|" + _alt("edição", "edicao", "edições", "alterações", "selecionadas", "seleção")
                      + r"|\b(?:pdf|png|jpg|svg|tif)\b", resto, re.I):
        return None  # formato/caminho/seleção: exportar cópia (save_layer_as); edição/layout: outro comando
    resto, _ = _tirar(r"\s" + _DEST_PROJ + r"(?=\s)", resto)
    params = {}
    mc = re.search(_COMO, resto, re.I)
    if mc:
        params["output_name"] = _limpa(mc.group("saida"))
        resto = resto[:mc.start()]
    if re.search(r"\bprojeto\b", resto, re.I):
        return None  # 'salvar o projeto' tem comando próprio
    camada = _sem_camada_propria(resto, ctx)
    params["layer_name"] = camada
    nome = f" como '{params['output_name']}'" if "output_name" in params else ""
    return _plano(f"Salvar '{camada}'{nome} na pasta do projeto, no mesmo formato e sistema dos outros "
                  "arquivos do projeto", "save_layer_to_project", params)


_GEOMS = [
    (_alt("multipontos", "multiponto"), "multipoint", "multipontos"),
    (_alt("multilinhas", "multilinha"), "multiline", "multilinhas"),
    (_alt("multipolígonos", "multipoligonos", "multipolígono", "multipoligono"), "multipolygon", "multipolígonos"),
    (_alt("pontos", "ponto", "pontual", "pontuais"), "point", "pontos"),
    (_alt("linhas", "linha", "linear", "lineares"), "line", "linhas"),
    (_alt("polígonos", "poligonos", "polígono", "poligono", "áreas", "areas", "área", "area", "poligonal"),
     "polygon", "polígonos"),
    (_alt("tabela", "sem geometria", "só tabela", "só atributos"), "none", "tabela"),
]
_GEOM_ALT = "(?:" + "|".join(p for p, _, _ in _GEOMS) + ")"
_TIPO_CRIAR = {"String": "string", "Integer": "integer", "Long": "long", "Double": "double",
               "Date": "date", "DateTime": "datetime", "Boolean": "boolean"}
_TEMP = _alt("temporária", "temporaria", "temporário", "temporario", "na memória", "na memoria",
             "em memória", "em memoria", "só na memória", "provisória", "provisoria")


@comando(r"(?:" + V_CRIAR + r")\s+" + ART + r"(?:" + _alt("nova", "novo") + r"\s+)?(?P<n>" + _k("camada")
         + "|" + _k("tabela") + r")(?:\s+(?P<resto>.*?))?", "criar camada de pontos chamada postes", primeiro=True)
def _criar_camada(m, ctx):
    resto = " " + (m.group("resto") or "") + " "
    if re.match(r"\s*(?:" + _alt("de buffer", "de centroides", "de centróides", "de vértices", "de vertices",
                                  "de grade", "de envoltória") + r")\s", resto, re.I):
        return None  # 'criar camada de centroides' -> geoprocessamento
    params = {}
    resto, mt = _tirar(r"\s,?\s*\(?" + _TEMP + r"\)?(?=\s)", resto)
    if mt:
        params["temporary"] = True
    # campos: tudo depois de 'com (os) campos'
    mf = re.search(r"\s(?:com|e)\s+(?:(?:o|os)\s+)?" + N_CAMPO + r"\s*:?\s+(?P<f>.*)$", resto, re.I)
    if mf:
        trecho = mf.group("f")
        resto = resto[:mf.start()] + " "
        campos = []
        for q in re.finditer(r'"([^"]+)"\s*(?:\(?\s*(?:(?:do\s+)?tipo\s+|como\s+|de\s+)?(?P<t>' + _TIPO_ALT
                             + r")(?![\w])\s*\)?)?", trecho, re.I):
            tipo = _tipo(q.group("t"))[0] if q.group("t") else "String"
            campos.append({"name": q.group(1).strip(), "type": _TIPO_CRIAR[tipo]})
        if not campos:
            raise ErroComando(MSG_ASPAS.format(
                'criar camada de pontos postes com campos "nome" texto e "altura" decimal'))
        params["fields"] = campos
    # sistema de coordenadas
    for ms in re.finditer(r"\s(?:em|no|sistema|crs|" + _k("no sistema") + "|" + _k("projeção")
                          + r")\s+(?P<c>.+?)(?=\s+(?:" + _alt("chamada", "chamado", "com o nome", "como", "nomeada")
                          + r")\s|\s*$)", resto, re.I):
        crs = _crs_txt(ms.group("c"))
        if crs:
            params["crs"] = crs
            resto = resto[:ms.start()] + " " + resto[ms.end():]
            break
    # geometria
    mg = re.search(r"(?:^|\s)(?:(?:de|com|do tipo|tipo|para)\s+)?(?P<g>" + _GEOM_ALT + r")(?=\s|$)", resto, re.I)
    if sem_acento(m.group("n")).startswith("tabela"):
        geom, rot = "none", "tabela"
    elif mg:
        geom, rot = next((g, r) for p, g, r in _GEOMS if re.fullmatch(p, mg.group("g"), re.I))
        resto = resto[:mg.start()] + " " + resto[mg.end():]
    else:
        raise ErroComando("Diga o tipo da camada: criar camada de pontos · de linhas · de polígonos · "
                          "criar tabela (sem geometria).")
    # nome
    mn = re.search(r"(?:^|\s)(?:" + _alt("chamada", "chamado", "com o nome de", "com o nome", "com nome",
                                         "nomeada", "nomeado", "como", "de nome") + r")\s+(?P<nome>.+)$", resto, re.I)
    if mn:
        sobra = resto[:mn.start()].strip()
        if sobra:
            raise ErroComando(f"Não entendi '{sobra}'. Ex.: criar camada de pontos chamada postes.")
        nome = _limpa(mn.group("nome"))
    else:
        nome = _limpa(" ".join(resto.split()))
    nome = nome or {"point": "pontos", "line": "linhas", "polygon": "poligonos", "none": "tabela"}.get(
        geom, geom) + "_novos"
    if nome in ctx.get("camadas", []):
        raise ErroComando(f"Já existe a camada '{nome}'. Escolha outro nome: ... chamada {nome}_2")
    params.update(name=nome, geometry_type=geom)
    campos_txt = (" com " + ", ".join(f"'{c['name']}'" for c in params["fields"])) if params.get("fields") else ""
    onde = " (temporária)" if params.get("temporary") else " na pasta do projeto"
    return _plano(f"Criar a camada de {rot} '{nome}'{campos_txt}{onde}, pronta para desenhar",
                  "create_layer", params)


@comando(r"(?:" + _alt("abrir", "abra", "abre", "carregar", "carregue", "carrega", "adicionar", "adicione",
                       "adiciona", "importar", "importe", "importa", "trazer", "traga")
         + r")\s+(?P<pre>.*?)(?P<p>[A-Za-z]:[\\/].*|\\\\.+)", r"abrir C:\dados\lotes.shp", primeiro=True)
def _abrir_arquivo(m, ctx):
    caminho = m.group("p").strip().strip('"').rstrip(" .")
    pasta = not os.path.splitext(caminho)[1] or caminho.lower().rstrip("\\/").endswith(".gdb")
    return _plano(f"Abrir {'os arquivos de' if pasta else 'o arquivo'} {caminho}", "load_files", {"path": caminho})


_GRUPO = _alt("grupo", "pasta de camadas")


@comando(r"(?:" + V_CRIAR + r")\s+" + ART + r"(?:" + _alt("novo") + r"\s+)?" + _GRUPO
         + r"(?:\s+(?:" + _alt("chamado", "com o nome", "de nome", "nomeado") + r"))?\s+(?P<nome>.+?)",
         "criar grupo Coleta", primeiro=True)
def _criar_grupo(m, ctx):
    nome = _limpa(m.group("nome"))
    return _plano(f"Criar o grupo '{nome}' no painel de camadas", "create_group", {"name": nome})


@comando(r"(?:" + _alt("mover", "mova", "move", "colocar", "coloque", "coloca", "pôr", "ponha", "põe",
                       "jogar", "jogue", "levar", "leve", "passar", "passe") + r")(?:\s+(?P<c>.*?))?\s+(?:"
         + _alt("para o", "pro", "no", "dentro do", "ao", "para") + r")\s+" + _GRUPO + r"\s+(?P<g>.+?)",
         "mover para o grupo Coleta", primeiro=True)
def _mover_grupo(m, ctx):
    camada = _sem_camada_propria(m.group("c") or "", ctx)
    grupo = _limpa(m.group("g"))
    return _plano(f"Pôr '{camada}' no grupo '{grupo}'", "move_layer_to_group",
                  {"layer_name": camada, "group": grupo})


@comando(r"(?:" + _alt("definir", "defina", "define", "atribuir", "atribua", "atribui", "corrigir", "corrija",
                       "corrige", "informar", "informe", "setar", "sete") + r")\s+" + ART
         + r"(?:" + _alt("sistema de coordenadas", "sistema de referência", "sistema", "crs", "src", "projeção",
                         "projecao", "epsg") + r")(?:\s+(?:" + _alt("da camada", "na camada", "desta camada") + r"))?"
         + r"\s+(?:(?:como|para|pra|em|=|igual a)\s+)?(?P<crs>.+?)", "definir sistema 31983", primeiro=True)
def _definir_crs(m, ctx):
    crs = _crs_txt(m.group("crs"))
    if crs is None:
        raise ErroComando("Sistema não reconhecido. Ex.: definir sistema 31983 · definir sistema SIRGAS 2000 UTM 23S.")
    camada = _ativa(ctx)
    return _plano(f"Definir o sistema de '{camada}' como {crs} (só a etiqueta: as coordenadas não mudam; "
                  "para converter use 'reprojetar para ...')", "set_layer_crs", {"layer_name": camada, "crs": crs})


@comando(r"(?:(?:" + _alt("copiar", "copie", "copia", "usar", "use", "usa", "aplicar", "aplique", "aplica", "pegar",
                          "pegue", "pega", "deixar com", "deixe com") + r")\s+" + ART
         + r"(?:" + _alt("mesmo", "mesma") + r"\s+)?|" + _alt("mesmo", "o mesmo") + r"\s+)(?:"
         + _alt("estilo", "simbologia", "visual") + r")\s+(?:(?:" + _alt("igual ao", "igual à", "igual a")
         + r")\s+)?(?:" + _alt("de", "da", "do", "dos", "das") + r")\s+(?P<outra>.+?)",
         "copiar estilo de Regiões", primeiro=True)
def _copiar_estilo(m, ctx):
    outra = _outra(m.group("outra"), ctx)
    camada = _ativa(ctx)
    return _plano(f"Copiar o estilo de '{outra}' para '{camada}'", "copy_style",
                  {"from_layer": outra, "to_layer": camada})


@comando(r"(?:(?:" + _alt("informações", "informacoes", "informação", "informacao", "info", "infos", "propriedades",
                          "detalhes", "sobre") + r")(?:\s+(?:" + _alt("da camada", "sobre a camada", "desta camada",
                                                                     "da camada selecionada", "da camada ativa", "camada")
         + r"))?|(?:" + _alt("qual o sistema", "qual é o sistema", "qual sistema", "qual a projeção", "qual o crs",
                             "onde está salva", "onde esta salva", "onde fica o arquivo", "que tipo de camada")
         + r")(?:\s+(?:" + _alt("da camada", "desta camada", "a camada", "ela", "dela") + r"))?)\??",
         "informações da camada")
def _info_camada(m, ctx):
    camada = _ativa(ctx)
    return _plano(f"Informações da camada '{camada}'", "get_layer_info", {"layer_name": camada})


@comando(r"(?:" + _alt("como o projeto salva", "como o projeto grava", "como o projeto guarda", "onde o projeto salva",
                       "padrão do projeto", "padrao do projeto", "formato do projeto", "pasta do projeto",
                       "onde salvar", "qual a pasta do projeto", "qual o formato do projeto",
                       "sistema do projeto", "qual o sistema do projeto") + r")\??", "padrão do projeto", primeiro=True)
def _padrao_projeto(m, ctx):
    return _plano("Ver como o projeto guarda os dados (pasta, formato e sistema)", "project_storage_info", {})


# --- visibilidade (por último: 'mostrar X' é bem genérico)
@comando(r"(?P<v>" + _alt("esconder", "esconda", "esconde", "ocultar", "oculte", "oculta", "desligar",
                          "desligue", "desliga", "mostrar", "mostre", "mostra", "exibir", "exiba", "exibe",
                          "ligar", "ligue", "liga", "reexibir", "acender", "acenda")
         + r")(?:\s+(?:" + ART + r")?(?:" + _k("camada") + r"(?:\s+|$))?(?P<camada>.*?))?", "esconder camada")
def _visibilidade(m, ctx):
    v = sem_acento(m.group("v"))
    visivel = not v.startswith(("escond", "ocult", "deslig"))
    alvo = sem_acento(_limpa(m.group("camada") or ""))
    if alvo in ("todas", "todas as camadas", "tudo", "todas camadas", "as camadas"):
        return _plano(f"{'Mostrar' if visivel else 'Esconder'} todas as camadas", "set_layer_visibility",
                      {"visible": visivel})
    camada = _camada(m.group("camada") or "", ctx)
    return _plano(f"{'Mostrar' if visivel else 'Esconder'} a camada '{camada}'", "set_layer_visibility",
                  {"layer_name": camada, "visible": visivel})


# ---------------------------------------------------------------------- API
AJUDA = _alt("ajuda", "help", "comandos", "o que você faz", "o que voce faz", "o que posso pedir",
             "exemplos", "lista de comandos", "?")


def exemplos():
    return list(EXEMPLOS)


def interpretar(texto, ctx=None):
    """Plano para um comando simples, ou None se não reconheceu (vai para a IA).

    Levanta ErroComando quando reconheceu o comando mas falta/está errado algum
    nome — melhor avisar na hora do que mandar a frase para a IA adivinhar.
    """
    ctx = ctx or {}
    texto = (texto or "").strip()
    texto = texto.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # Ditado por voz: "criar campo aspas área aspas" -> criar campo "área"
    texto = re.sub(r"\b(?:abre\s+|abrir\s+)?aspas\s+(.+?)\s+(?:fecha\s+|fechar\s+)?aspas\b",
                   lambda m: '"' + m.group(1).strip(" .,") + '"', texto, flags=re.I)
    if not texto:
        return None
    if re.fullmatch(AJUDA + FIM, texto, re.I):
        return {"descricao": "Comandos simples que funcionam sem IA", "ajuda": exemplos(),
                "steps": [], "destrutivo": False}
    if "\n" in texto or ";" in texto:
        return None  # vários pedidos de uma vez: deixa para a IA encadear
    texto = re.sub(r"^(?:por favor[,\s]+|pf[,\s]+|agora[,\s]+|quero\s+|gostaria de\s+|pode\s+|poderia\s+|me\s+)+",
                   "", texto, flags=re.I)
    texto = re.sub(r"[,\s]+por favor$", "", texto, flags=re.I)
    for regex, fn, _ in COMANDOS:
        m = regex.match(texto)
        if m:
            plano = fn(m, ctx)
            if plano is not None:
                return plano
    return None
