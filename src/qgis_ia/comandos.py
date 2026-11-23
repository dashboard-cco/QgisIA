# -*- coding: utf-8 -*-
"""
Comandos simples em português, interpretados SEM IA.

    interpretar("criar campo area tipo decimal na camada lotes", ctx)
    -> {"descricao": "Criar o campo 'area' (Decimal) na camada 'lotes'",
        "steps": [{"action": "add_field", "params": {...}}],
        "destrutivo": False}

Vantagens sobre mandar tudo para a IA: resposta instantânea, sem custo, funciona
sem internet e faz sempre a mesma coisa para a mesma frase. O que não casar com
nenhum comando (devolve None) segue para a IA.

ctx = {"camadas": [nomes], "campos": {camada: [campos]}, "ativa": nome ou None}

Sem dependências do QGIS, para poder ser testado sozinho.
"""
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


ATIVA = {"", "ativa", "a ativa", "camada ativa", "a camada ativa", "atual", "a atual",
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


def _camada(nome, ctx):
    nome = _limpa(nome)
    if sem_acento(nome) in ATIVA:
        if not ctx.get("ativa"):
            raise ErroComando("Nenhuma camada ativa. Diga o nome da camada "
                              "(ex.: '... na camada lotes') ou clique nela no painel de camadas.")
        return ctx["ativa"]
    return _achar(nome, ctx.get("camadas", []), "a camada")


def _campo(nome, camada, ctx):
    return _achar(nome, ctx.get("campos", {}).get(camada, []), f"o campo (em '{camada}')")


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
            return texto[:m.start()].strip(), _achar(cand, ctx.get("camadas", []), "a camada",
                                                     parcial=False)
        except ErroComando:
            continue
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


def _valor(v, campos, lado_campo=False):
    v = v.strip()
    if not v:
        return v
    if v[0] in "\"'" and v[-1] == v[0] and len(v) > 1:
        dentro = v[1:-1]
        if v[0] == '"' and dentro in campos:
            return v
        return "'" + dentro.replace("'", "''") + "'"
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", v):
        return v.replace(",", ".")
    if lado_campo:
        v = re.sub(rf"^{ART}(?:{_alt('campo', 'coluna')}\s+)?", "", v, flags=re.I)
    try:
        return '"' + _achar(v, campos, "o campo", parcial=lado_campo) + '"'
    except ErroComando:
        pass
    if lado_campo:  # 'area' sem campo com esse nome = área da geometria
        for pad, geo in _GEOMETRIA:
            if re.fullmatch(pad, v, re.I):
                return geo
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
    if re.search(r'"[^"]+"\s*(=|<>|!=|>=|<=|>|<|\bilike\b|\blike\b|\bis\b|\bin\b)', texto, re.I) \
            or re.search(r"\$\w+|@\w+|\w+\(", texto):
        return texto
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
        out.append(_condicao(p.strip(), campos))
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


def comando(padrao, exemplo):
    def deco(fn):
        COMANDOS.append((re.compile("^" + padrao + FIM, re.I), fn, exemplo))
        return fn
    return deco


def _plano(descricao, action, params, destrutivo=False):
    return {"descricao": descricao, "destrutivo": destrutivo,
            "steps": [{"action": action, "params": params}]}


# --- camadas
@comando(rf"(?:{V_COPIAR}|{V_CRIAR}\s+uma\s+{_k('cópia')}(?:\s+d[aeo])?)(?:\s+{ART}(?:{_k('camada')})?\s*(?P<resto>.*?))?",
         "copiar camada lotes como lotes_backup")
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


@comando(rf"{V_RENOMEAR}\s+(?:d[ao]\s+)?{ART}{_k('camada')}\s+(?P<camada>.+?)\s+(?:para|pra|como)\s+(?P<novo>.+?)",
         "renomear camada lotes para lotes_2026")
def _renomear_camada(m, ctx):
    camada = _camada(m.group("camada"), ctx)
    novo = _limpa(m.group("novo"))
    return _plano(f"Renomear a camada '{camada}' para '{novo}'", "rename_layer",
                  {"layer_name": camada, "new_name": novo})


@comando(rf"{V_APAGAR}\s+{ART}{_k('camada')}\s*(?P<camada>.*?)(?:\s+d[oa]\s+(?:projeto|mapa))?",
         "remover camada lotes_copia")
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
         "criar campo area tipo decimal na camada lotes")
def _criar_campo(m, ctx):
    resto = m.group("resto")
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
    resto, camada = _separar_camada(resto, ctx)
    camada = _ou_ativa(camada, ctx)
    nome = _limpa(resto)
    if not mt:  # 'criar campo area decimal': a última palavra é o tipo
        mt2 = re.fullmatch(rf"(?P<n>.+?)\s+(?P<t>{_TIPO_ALT})", nome, re.I)
        if mt2:
            tipo, rotulo = _tipo(mt2.group("t"))
            nome = mt2.group("n").strip()
    if not nome:
        raise ErroComando("Faltou o nome do campo. Ex.: 'criar campo area tipo decimal'.")
    if re.search(r"\s", nome):
        nome = re.sub(r"\s+", "_", nome)
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


@comando(rf"{V_APAGAR}\s+{ART}{N_CAMPO}\s+(?P<resto>.+?)", "apagar campo area da camada lotes")
def _apagar_campo(m, ctx):
    resto, camada = _separar_camada(m.group("resto"), ctx)
    camada = _ou_ativa(camada, ctx)
    nomes = [_campo(n, camada, ctx) for n in _lista_nomes(resto)]
    if not nomes:
        raise ErroComando("Faltou o nome do campo.")
    alvo = nomes[0] if len(nomes) == 1 else nomes
    txt = ", ".join(f"'{n}'" for n in nomes)
    return _plano(f"Apagar {'o campo' if len(nomes) == 1 else 'os campos'} {txt} da camada '{camada}'",
                  "delete_field", {"layer_name": camada, "field_name": alvo}, destrutivo=True)


@comando(rf"{V_RENOMEAR}\s+(?:d[ao]\s+)?{ART}{N_CAMPO}\s+(?P<resto>.+?)", "renomear campo nm para nome na camada lotes")
def _renomear_campo(m, ctx):
    resto, camada = _separar_camada(m.group("resto"), ctx)
    camada = _ou_ativa(camada, ctx)
    partes = re.split(r"\s+(?:para|pra|como)\s+", resto, maxsplit=1, flags=re.I)
    if len(partes) != 2:
        raise ErroComando("Use: 'renomear campo ANTIGO para NOVO'.")
    antigo = _campo(partes[0], camada, ctx)
    novo = re.sub(r"\s+", "_", _limpa(partes[1]))
    return _plano(f"Renomear o campo '{antigo}' para '{novo}' na camada '{camada}'", "rename_field",
                  {"layer_name": camada, "field_name": antigo, "new_name": novo})


@comando(rf"{V_LISTAR}\s+{ART}{N_CAMPO}(?P<resto>.*?)", "listar campos de lotes")
def _listar_campos(m, ctx):
    resto = m.group("resto").strip()
    camada = _camada(re.sub(rf"^{_PREP}\s+{ART}(?:{_k('camada')}\s+)?", "", resto, flags=re.I), ctx) \
        if resto else _camada("", ctx)
    return _plano(f"Listar os campos da camada '{camada}'", "list_fields", {"layer_name": camada})


_EXPR_SEP = rf"(?:\s*=\s*|\s+(?:com|como|usando|igual a|recebendo|pela expressão|pela expressao|por)\s+)"


@comando(rf"{V_CALC}\s+{ART}{N_CAMPO}\s+(?P<resto>.+?)", "calcular campo area com $area / 10000 na camada lotes")
def _calcular_campo(m, ctx):
    resto = m.group("resto")
    so_sel = False
    ms = re.search(rf"\s+(?:{_alt('só nas selecionadas', 'só das selecionadas', 'só nos selecionados', 'nas selecionadas', 'apenas nas selecionadas')})", resto, re.I)
    if ms:
        so_sel = True
        resto = (resto[:ms.start()] + resto[ms.end():]).strip()
    partes = re.split(_EXPR_SEP, resto, maxsplit=1, flags=re.I)
    if len(partes) != 2:
        raise ErroComando("Use: 'calcular campo NOME com EXPRESSÃO' (ex.: com $area / 10000).")
    esquerda, expr = partes
    camada = None
    mc = re.search(rf"\s+{_PREP}\s+{ART}{_k('camada')}\s+(?P<c>.+)$", expr, re.I)
    if mc:  # '... com $area na camada lotes'
        try:
            camada = _camada(mc.group("c"), ctx)
            expr = expr[:mc.start()]
        except ErroComando:
            camada = None
    esquerda, cam2 = _separar_camada(esquerda, ctx)
    camada = camada or _ou_ativa(cam2, ctx)
    nome = _limpa(esquerda)
    campos = ctx.get("campos", {}).get(camada, [])
    try:
        nome = _campo(nome, camada, ctx)
    except ErroComando:
        nome = re.sub(r"\s+", "_", nome)  # campo novo: calculate_field cria
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
    try:
        return '"' + _achar(t, campos, "o campo") + '"'
    except ErroComando:
        pass
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
         "selecionar tudo em lotes")
def _selecionar_tudo(m, ctx):
    if _onde(m.group("camada"))[1]:
        return None  # 'selecionar todos os lotes onde ...': é seleção por condição
    camada = _camada_de(m.group("camada"), ctx)
    return _plano(f"Selecionar todas as feições de '{camada}'", "select_features", {"layer_name": camada})


@comando(rf"{V_SELEC}\s+(?P<resto>.+?)", "selecionar lotes onde area maior que 1000")
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


@comando(rf"{_alt('inverter', 'inverta', 'inverte')}\s+{ART}{_k('seleção')}(?P<resto>.*?)", "inverter seleção de lotes")
def _inverter(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Inverter a seleção de '{camada}'", "invert_selection", {"layer_name": camada})


@comando(rf"{V_APAGAR}\s+{ART}(?:{N_FEICAO}\s+)?{_alt('selecionadas', 'selecionados', 'seleção', 'a seleção')}(?P<resto>.*?)",
         "apagar feições selecionadas de lotes")
def _apagar_selecionadas(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Apagar as feições selecionadas de '{camada}'", "delete_selected_features",
                  {"layer_name": camada}, destrutivo=True)


@comando(rf"{V_APAGAR}\s+{ART}(?:{N_FEICAO})\s+(?P<resto>.+?)", "apagar feições de lotes onde area menor que 1")
def _apagar_feicoes(m, ctx):
    esquerda, cond = _onde(m.group("resto"))
    if not cond:
        return None
    camada = _camada_de(esquerda.strip(), ctx)
    expr = expressao(cond, ctx.get("campos", {}).get(camada, []))
    return _plano(f"Apagar as feições de '{camada}' onde {expr}", "delete_features",
                  {"layer_name": camada, "expression": expr}, destrutivo=True)


@comando(rf"{_alt('contar', 'conte', 'conta', 'quantas', 'quantos', 'total de')}\s+(?:{ART}{N_FEICAO}\s+)?(?:{_alt('tem', 'há', 'existem', 'possui')}\s+)?(?P<resto>.*?)",
         "contar feições de lotes onde area maior que 1000")
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
         "editar camada lotes")
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
         "limpar filtro de lotes")
def _limpar_filtro(m, ctx):
    camada = _camada_de(m.group("resto"), ctx)
    return _plano(f"Remover o filtro de '{camada}'", "clear_filter", {"layer_name": camada})


@comando(rf"{_alt('filtrar', 'filtre', 'filtra', 'mostrar só', 'mostre só', 'mostrar apenas', 'mostre apenas', 'exibir só', 'exibir apenas')}\s+(?:{ART}{N_FEICAO}\s+)?(?P<resto>.+?)",
         "filtrar lotes onde bairro igual a Centro")
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
         "zoom na camada lotes")
def _zoom(m, ctx):
    camada = _camada(m.group("camada"), ctx)
    return _plano(f"Aproximar o mapa da camada '{camada}'", "zoom_to_layer", {"layer_name": camada})


# ---------------------------------------------------------------------- API
AJUDA = _alt("ajuda", "help", "comandos", "o que você faz", "o que voce faz", "o que posso pedir",
             "exemplos", "lista de comandos", "?")


def exemplos():
    return [ex for _, _, ex in COMANDOS]


def interpretar(texto, ctx=None):
    """Plano para um comando simples, ou None se não reconheceu (vai para a IA).

    Levanta ErroComando quando reconheceu o comando mas falta/está errado algum
    nome — melhor avisar na hora do que mandar a frase para a IA adivinhar.
    """
    ctx = ctx or {}
    texto = (texto or "").strip()
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
