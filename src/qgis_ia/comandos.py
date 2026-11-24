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

ctx = {"camadas": [nomes], "campos": {camada: [campos]}, "ativa": nome ou None,
       "layouts": [nomes dos layouts de impressão]}

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
    direita, camada = _separar_camada(direita, ctx)
    camada = camada or _camada_sobra(esquerda, ctx)
    alvo = _limpa(direita)
    try:
        campo = _campo(alvo, camada, ctx)
    except ErroComando:
        campo = None
        for pad, geo in _GEOMETRIA:
            if re.fullmatch(pad, alvo, re.I):
                campo, graduado = geo, True
                break
        if campo is None:
            raise
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
@comando(rf"(?:{V_AJUSTAR}\s+)?(?P<resto>.*?{_K_TRANSP}.*?)", "transparência 50% em lotes")
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
         "sem contorno em lotes", primeiro=True)
def _sem_contorno(m, ctx):
    camada = _camada_sobra(m.group("resto"), ctx)
    return _plano(f"Tirar o contorno de '{camada}'", "update_symbol",
                  {"layer_name": camada, "outline_color": "#00000000"})


@comando(rf"(?:{V_AJUSTAR}\s+)?(?:{ART})?" + _alt("contorno", "contornos", "borda", "bordas")
         + r"\s+(?P<resto>.+?)", "contorno preto de 0.5 em lotes")
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
         + r")\s+)?(?P<resto>.+?)", "espessura 1.5 em vias")
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
         + r")\s+(?P<resto>.+?)", "cores por bairro em lotes")
def _cores_por(m, ctx):
    v = sem_acento(m.group("v"))
    graduado = v.startswith(("classific", "gradu", "degrad"))
    return _por_campo(m.group("resto"), ctx, graduado)


@comando(rf"(?P<v>{V_PINTAR})\s+(?P<resto>.+?)", "pintar lotes de azul")
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


@comando(rf"(?:{V_LIMPAR}|{V_SUMIR})\s+{ART}{N_ROTULO}(?P<resto>.*?)", "tirar rótulos de lotes")
def _sem_rotulos(m, ctx):
    camada = _camada_sobra(m.group("resto"), ctx)
    return _plano(f"Desligar os rótulos de '{camada}'", "set_labels",
                  {"layer_name": camada, "enabled": False})


_V_ROTULAR = _alt("ligar", "ligue", "ativar", "ative", "mostrar", "mostre", "exibir", "exiba")


@comando(rf"(?:(?:{V_CRIAR}|{V_AJUSTAR}|{_V_ROTULAR})\s+{ART}{N_ROTULO}|"
         + _alt("rotular", "rotule", "rotula", "etiquetar", "etiquete") + rf"|{ART}{N_ROTULO})(?P<resto>.*?)",
         "rótulos com nome em lotes")
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
    else:
        campo_txt = _limpa(bruto)
        if not campo_txt:
            raise ErroComando("Diga o campo do rótulo. Ex.: 'rótulos com nome em lotes'.")
        campo = _campo(campo_txt, camada, ctx)
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
         + r")\s+" + ART + "(?:" + _k("camada") + r"\s+)?(?P<camada>.+?)\s+(?P<d>"
         + _alt("para frente", "pra frente", "para a frente", "à frente", "na frente", "para cima",
                "pra cima", "para o topo", "pro topo", "no topo", "em cima", "por cima", "para trás",
                "para tras", "pra trás", "pra tras", "para baixo", "pra baixo", "para o fundo",
                "pro fundo", "no fundo", "atrás", "por baixo", "embaixo", "uma posição acima",
                "uma posição abaixo", "um nível acima", "um nível abaixo") + ")",
         "trazer lotes para frente")
def _ordem(m, ctx):
    camada = _camada(m.group("camada"), ctx)
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


# --- visibilidade (por último: 'mostrar X' é bem genérico)
@comando(r"(?P<v>" + _alt("esconder", "esconda", "esconde", "ocultar", "oculte", "oculta", "desligar",
                          "desligue", "desliga", "mostrar", "mostre", "mostra", "exibir", "exiba", "exibe",
                          "ligar", "ligue", "liga", "reexibir", "acender", "acenda")
         + r")\s+(?:" + ART + r")?(?:" + _k("camada") + r"\s+)?(?P<camada>.+?)", "esconder camada lotes")
def _visibilidade(m, ctx):
    v = sem_acento(m.group("v"))
    visivel = not v.startswith(("escond", "ocult", "deslig"))
    alvo = sem_acento(_limpa(m.group("camada")))
    if alvo in ("todas", "todas as camadas", "tudo", "todas camadas", "as camadas"):
        return _plano(f"{'Mostrar' if visivel else 'Esconder'} todas as camadas", "set_layer_visibility",
                      {"visible": visivel})
    camada = _camada(m.group("camada"), ctx)
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
