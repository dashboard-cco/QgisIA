# -*- coding: utf-8 -*-
"""
Actions: camadas - Salvar, criar, abrir e organizar camadas pelos comandos simples.

"Salvar na pasta do projeto" olha os arquivos que o projeto já usa e grava
igual: mesma pasta, mesmo formato (o mesmo GeoPackage, se for o caso) e o
mesmo sistema de coordenadas. A camada temporária é trocada pela gravada,
com o mesmo nome, estilo e posição no painel.
"""
import os
import re
from collections import Counter

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsField, QgsFields,
    QgsWkbTypes, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsVectorFileWriter, QgsMapLayerStyle, QgsProviderRegistry, QgsProviderSublayerDetails,
    QgsLayerTreeGroup,
)
from qgis.PyQt.QtCore import QMetaType

# driver OGR -> (chave, extensão)
DRIVERS = {"GPKG": ("gpkg", "gpkg"), "ESRI Shapefile": ("shp", "shp"), "GeoJSON": ("geojson", "geojson"),
           "KML": ("kml", "kml"), "CSV": ("csv", "csv"), "OpenFileGDB": ("gdb", "gdb"), "FileGDB": ("gdb", "gdb")}
EXT_DRIVER = {".gpkg": "GPKG", ".shp": "ESRI Shapefile", ".geojson": "GeoJSON", ".json": "GeoJSON",
              ".kml": "KML", ".csv": "CSV", ".gdb": "OpenFileGDB"}
EXT_VETOR = (".shp", ".gpkg", ".geojson", ".json", ".kml", ".kmz", ".gml", ".dxf", ".tab", ".mif", ".csv")
EXT_RASTER = (".tif", ".tiff", ".jpg", ".jpeg", ".png", ".ecw", ".jp2", ".img", ".vrt", ".asc")

TIPOS_GEOM = {"point": QgsWkbTypes.Point, "line": QgsWkbTypes.LineString, "polygon": QgsWkbTypes.Polygon,
              "multipoint": QgsWkbTypes.MultiPoint, "multiline": QgsWkbTypes.MultiLineString,
              "multipolygon": QgsWkbTypes.MultiPolygon, "none": QgsWkbTypes.NoGeometry}
_T = QMetaType.Type
TIPOS_CAMPO = {"string": _T.QString, "integer": _T.Int, "int": _T.Int, "long": _T.LongLong,
               "double": _T.Double, "date": _T.QDate, "datetime": _T.QDateTime, "boolean": _T.Bool,
               "bool": _T.Bool}


def _proj():
    return QgsProject.instance()


def _layer(nome):
    ls = _proj().mapLayersByName(nome)
    if not ls:
        raise ValueError(f"Camada não encontrada: {nome}")
    return ls[0]


def _vetor(nome):
    c = _layer(nome)
    if not isinstance(c, QgsVectorLayer):
        raise ValueError(f"'{nome}' não é uma camada vetorial.")
    return c


def _arquivo(camada):
    """(caminho do arquivo, nome da tabela, driver) de uma camada OGR em arquivo; None se não for."""
    if not isinstance(camada, QgsVectorLayer) or camada.providerType() != "ogr":
        return None
    partes = QgsProviderRegistry.instance().decodeUri("ogr", camada.source())
    caminho = partes.get("path") or ""
    if not caminho or not os.path.exists(caminho):
        return None
    ext = os.path.splitext(caminho)[1].lower()
    driver = EXT_DRIVER.get(ext) or (camada.dataProvider().storageType() or "")
    return caminho, partes.get("layerName") or "", driver


def _nome_arquivo(nome):
    nome = re.sub(r'[<>:"/\\|?*\s]+', "_", str(nome)).strip(" ._") or "camada"
    return nome


def padrao_projeto():
    """Como o projeto guarda os dados: pasta, formato, GeoPackage em uso e sistema de coordenadas.

    Olha as camadas vetoriais em arquivo e escolhe o que é mais comum entre elas.
    Sem nenhuma, usa a pasta do projeto, GeoPackage e o sistema do projeto.
    """
    arquivos = [(c, a) for c in _proj().mapLayers().values() for a in [_arquivo(c)] if a]
    home = _proj().homePath()
    formatos = Counter(a[2] for _, a in arquivos if a[2] in ("GPKG", "OpenFileGDB", "ESRI Shapefile", "GeoJSON"))
    driver = formatos.most_common(1)[0][0] if formatos else "GPKG"
    do_formato = [(c, a) for c, a in arquivos if a[2] == driver]
    pastas = Counter(os.path.dirname(a[0]) for _, a in do_formato)
    pasta = pastas.most_common(1)[0][0] if pastas else (home if home and os.path.isdir(home) else "")
    gpkg = None
    if driver in ("GPKG", "OpenFileGDB"):
        gpkgs = Counter(a[0] for _, a in do_formato)
        gpkg = gpkgs.most_common(1)[0][0] if gpkgs else None
    crss = Counter(c.crs().authid() for c, _ in arquivos if c.crs().isValid())
    crs = crss.most_common(1)[0][0] if crss else (_proj().crs().authid() if _proj().crs().isValid() else "")
    return {"pasta": pasta, "driver": driver, "formato": DRIVERS[driver][0], "geopackage": gpkg,
            "crs": crs, "camadas_em_arquivo": len(arquivos), "pasta_do_projeto": home}


def _tabelas_gpkg(caminho):
    if not os.path.exists(caminho):
        return set()
    return {d.name() for d in QgsProviderRegistry.instance().querySublayers(caminho)}


def _gravar(camada, nome, padrao, crs=None):
    """Grava a camada seguindo o padrão do projeto. Devolve (uri para abrir, caminho, nome usado)."""
    if not padrao["pasta"]:
        raise ValueError("O projeto ainda não foi salvo e não usa nenhum arquivo, então não há pasta "
                         "do projeto. Salve o projeto primeiro ('salvar o projeto como C:\\pasta\\projeto.qgz').")
    driver = padrao["driver"]
    destino = QgsCoordinateReferenceSystem(crs or padrao["crs"]) if (crs or padrao["crs"]) else camada.crs()
    opcoes = QgsVectorFileWriter.SaveVectorOptions()
    opcoes.driverName = driver
    opcoes.fileEncoding = "UTF-8"
    if destino.isValid() and camada.crs().isValid() and destino != camada.crs() and camada.isSpatial():
        opcoes.ct = QgsCoordinateTransform(camada.crs(), destino, _proj().transformContext())
    base = _nome_arquivo(nome)
    if driver in ("GPKG", "OpenFileGDB"):
        caminho = padrao["geopackage"] or os.path.join(padrao["pasta"], "dados." + DRIVERS[driver][1])
        existentes = {t.lower() for t in _tabelas_gpkg(caminho)}
        tabela, n = base, 2
        while tabela.lower() in existentes:
            tabela, n = f"{base}_{n}", n + 1
        opcoes.layerName = tabela
        if os.path.exists(caminho):
            opcoes.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        uri = f"{caminho}|layername={tabela}"
        usado = tabela
    else:
        ext = DRIVERS[driver][1]
        usado, n = base, 2
        while os.path.exists(os.path.join(padrao["pasta"], f"{usado}.{ext}")):
            usado, n = f"{base}_{n}", n + 1
        caminho = os.path.join(padrao["pasta"], f"{usado}.{ext}")
        uri = caminho
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    erro = QgsVectorFileWriter.writeAsVectorFormatV3(camada, caminho, _proj().transformContext(), opcoes)
    if erro[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Falha ao gravar: {erro[1]}")
    return uri, caminho, usado


def _no_lugar_de(antiga, nova):
    """Põe a camada nova na mesma posição/grupo da antiga, com o mesmo estilo."""
    estilo = QgsMapLayerStyle()
    estilo.readFromLayer(antiga)
    estilo.writeToLayer(nova)
    raiz = _proj().layerTreeRoot()
    no = raiz.findLayer(antiga.id())
    _proj().addMapLayer(nova, False)
    if no is not None:
        pai = no.parent()
        pai.insertLayer(pai.children().index(no), nova)
        visivel = no.isVisible()
        _proj().removeMapLayer(antiga.id())
        no_novo = raiz.findLayer(nova.id())
        if no_novo is not None:
            no_novo.setItemVisibilityChecked(visivel)
    else:
        raiz.insertLayer(0, nova)


def save_layer_to_project(layer_name, output_name=None, keep_temporary=False):
    """Grava a camada na pasta do projeto do mesmo jeito que os outros arquivos do projeto
    (mesma pasta, formato — o mesmo GeoPackage, se for o caso — e sistema de coordenadas).

    Camada temporária (memória) é trocada pela gravada, com nome, estilo e posição iguais.
    Camada que já é arquivo: a cópia gravada entra no projeto ao lado da original.
    """
    camada = _vetor(layer_name)
    if camada.isEditable() and camada.isModified():
        raise ValueError(f"'{layer_name}' tem edição não salva. Diga 'salvar edição' antes.")
    padrao = padrao_projeto()
    uri, caminho, usado = _gravar(camada, output_name or camada.name(), padrao)
    nome = output_name or camada.name()
    temporaria = camada.providerType() == "memory"
    nova = QgsVectorLayer(uri, nome, "ogr")
    if not nova.isValid():
        raise RuntimeError(f"Gravou em {caminho}, mas não conseguiu abrir de volta.")
    if temporaria and not keep_temporary:
        _no_lugar_de(camada, nova)
        acao = "trocada pela camada gravada"
    else:
        estilo = QgsMapLayerStyle()
        estilo.readFromLayer(camada)
        estilo.writeToLayer(nova)
        if nome == camada.name():
            nova.setName(f"{nome} ({padrao['formato']})")
        _proj().addMapLayer(nova)
        acao = "cópia adicionada ao projeto"
    return {"success": True, "output_layer": nova.name(), "output_path": caminho,
            "formato": padrao["formato"].upper() + (f" (tabela {usado})" if padrao["driver"] in ("GPKG", "OpenFileGDB") else ""),
            "sistema": nova.crs().authid(), "aviso": None, "acao": acao}


def fill_field_by_location(layer_name, field, overlay, overlay_field=None, only_empty=False):
    """Preenche um campo que já existe na camada com o valor do polígono de 'overlay' onde
    cada feição está (ex.: "codigo_ra" pela camada de limites das RAs).

    overlay_field: campo de onde vem o valor; sem informar, usa o campo de mesmo nome.
    Se a camada estiver em edição, as mudanças ficam pendentes até salvar a edição.
    """
    from qgis.core import QgsSpatialIndex
    camada, ref = _vetor(layer_name), _vetor(overlay)
    if camada.fields().indexOf(field) < 0:
        raise ValueError(f"'{layer_name}' não tem o campo '{field}'. Crie antes: criar campo \"{field}\".")
    if ref.geometryType() != QgsWkbTypes.PolygonGeometry:
        raise ValueError(f"'{overlay}' precisa ser uma camada de polígonos.")
    if not overlay_field:
        nomes = {f.name().lower(): f.name() for f in ref.fields()}
        overlay_field = nomes.get(field.lower())
        if not overlay_field:
            raise ValueError(f"'{overlay}' não tem campo '{field}'. Diga qual usar: ... campo \"nome\". "
                             f"Campos: {', '.join(ref.fields().names())}")
    elif ref.fields().indexOf(overlay_field) < 0:
        raise ValueError(f"'{overlay}' não tem o campo '{overlay_field}'.")
    idx = camada.fields().indexOf(field)
    polis = {f.id(): f for f in ref.getFeatures()}
    indice = QgsSpatialIndex(ref.getFeatures())
    xf = QgsCoordinateTransform(camada.crs(), ref.crs(), _proj().transformContext())
    mudancas, sem = {}, 0
    for f in camada.getFeatures():
        if only_empty and f[field] not in (None, "") and str(f[field]) != "NULL":
            continue
        g = f.geometry()
        if g is None or g.isEmpty():
            sem += 1
            continue
        p = g.pointOnSurface()
        if camada.crs() != ref.crs():
            p.transform(xf)
        valor = None
        for fid in indice.intersects(p.boundingBox()):
            if polis[fid].geometry().contains(p):
                valor = polis[fid][overlay_field]
                break
        if valor is None:
            sem += 1
            continue
        mudancas[f.id()] = valor
    ja_editando = camada.isEditable()
    if not ja_editando and not camada.startEditing():
        raise RuntimeError(f"Não foi possível editar '{layer_name}'.")
    try:
        for fid, v in mudancas.items():
            camada.changeAttributeValue(fid, idx, v)
        if not ja_editando and not camada.commitChanges():
            raise RuntimeError("; ".join(camada.commitErrors()))
    except Exception:
        if not ja_editando:
            camada.rollBack()
        raise
    return {"success": True, "layer": layer_name, "campo": field, "updated": len(mudancas),
            "sem_correspondencia": sem, "pending": ja_editando}


def project_storage_info():
    """Mostra como o projeto guarda os dados (pasta, formato, GeoPackage e sistema mais usados)."""
    p = padrao_projeto()
    return {"pasta": p["pasta"] or "(projeto não salvo)", "formato": p["formato"].upper(),
            "geopackage": p["geopackage"], "sistema": p["crs"], "camadas_em_arquivo": p["camadas_em_arquivo"]}


def create_layer(name, geometry_type="point", fields=None, crs=None, temporary=False, start_editing=True):
    """Cria uma camada nova, vazia, pronta para desenhar.

    geometry_type: point, line, polygon, multipoint, multiline, multipolygon ou none (tabela).
    fields: [{"name": "nome", "type": "string|integer|double|date|boolean"}].
    crs: sem informar, usa o sistema dos arquivos do projeto (ou o do projeto).
    Por padrão grava na pasta do projeto, no formato que o projeto usa; temporary=True cria só na memória.
    Entra em modo de edição e vira a camada selecionada.
    """
    tipo = TIPOS_GEOM.get(str(geometry_type).lower())
    if tipo is None:
        raise ValueError(f"Tipo de geometria inválido: {geometry_type}. Use: {', '.join(TIPOS_GEOM)}")
    padrao = padrao_projeto()
    sistema = QgsCoordinateReferenceSystem(crs or padrao["crs"] or "EPSG:31983")
    if not sistema.isValid():
        raise ValueError(f"Sistema de coordenadas inválido: {crs}")
    geom = QgsWkbTypes.displayString(tipo) if tipo != QgsWkbTypes.NoGeometry else "None"
    mem = QgsVectorLayer(f"{geom}?crs={sistema.authid()}", name, "memory")
    qfields = []
    for f in fields or []:
        t = str(f.get("type", "string")).lower()
        if t not in TIPOS_CAMPO:
            raise ValueError(f"Tipo de campo inválido: {t}")
        qfields.append(QgsField(f["name"], TIPOS_CAMPO[t]))
    if qfields:
        mem.dataProvider().addAttributes(qfields)
        mem.updateFields()
    if _proj().mapLayersByName(name):
        raise ValueError(f"Já existe uma camada chamada '{name}'. Escolha outro nome.")
    caminho = None
    if temporary or not padrao["pasta"]:
        nova = mem
        _proj().addMapLayer(nova)
    else:
        uri, caminho, _ = _gravar(mem, name, padrao, crs=sistema.authid())
        nova = QgsVectorLayer(uri, name, "ogr")
        if not nova.isValid():
            raise RuntimeError(f"Gravou em {caminho}, mas não conseguiu abrir de volta.")
        _proj().addMapLayer(nova)
    if start_editing and nova.isSpatial():
        nova.startEditing()
    out = {"success": True, "output_layer": nova.name(), "sistema": sistema.authid(),
           "geometria": geom, "editing": bool(start_editing and nova.isSpatial())}
    if caminho:
        out["output_path"] = caminho
    elif not padrao["pasta"]:
        out["aviso"] = ("projeto ainda não salvo: camada criada na memória; salve o projeto e diga "
                        "'salvar camada na pasta do projeto'")
    else:
        out["aviso"] = "camada temporária (some ao fechar o QGIS); para guardar diga 'salvar camada na pasta do projeto'"
    return out


def _abrir_um(caminho):
    """Camadas de um arquivo (todas as tabelas de um GeoPackage/GDB)."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in EXT_RASTER:
        r = QgsRasterLayer(caminho, os.path.splitext(os.path.basename(caminho))[0])
        return [r] if r.isValid() else []
    subs = QgsProviderRegistry.instance().querySublayers(caminho)
    opcoes = QgsProviderSublayerDetails.LayerOptions(_proj().transformContext())
    camadas = []
    for d in subs:
        if d.type() not in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
            continue
        c = d.toLayer(opcoes)
        if c is not None and c.isValid():
            if len(subs) == 1:
                c.setName(os.path.splitext(os.path.basename(caminho.rstrip("\\/")))[0])
            camadas.append(c)
    return camadas


def load_files(path):
    """Abre no projeto um arquivo (shp, gpkg, geojson, kml, csv, tif...), um .gdb ou todos os arquivos de uma pasta."""
    path = os.path.expanduser(str(path).strip().strip('"'))
    if not os.path.exists(path):
        raise ValueError(f"Não encontrei: {path}")
    if os.path.isdir(path) and not path.lower().rstrip("\\/").endswith(".gdb"):
        alvos = []
        for nome in sorted(os.listdir(path)):
            cheio = os.path.join(path, nome)
            if nome.lower().endswith(".gdb") and os.path.isdir(cheio):
                alvos.append(cheio)
            elif os.path.isfile(cheio) and nome.lower().endswith(EXT_VETOR + EXT_RASTER):
                alvos.append(cheio)
        if not alvos:
            raise ValueError(f"Nenhum arquivo de mapa em {path}.")
    else:
        alvos = [path]
    nomes = []
    for a in alvos:
        for c in _abrir_um(a):
            _proj().addMapLayer(c)
            nomes.append(c.name())
    if not nomes:
        raise ValueError(f"Não consegui abrir nenhuma camada de {path}.")
    out = {"success": True, "adicionadas": nomes}
    if len(nomes) == 1:
        out["output_layer"] = nomes[0]
    return out


def _grupo(nome, criar=True):
    raiz = _proj().layerTreeRoot()
    g = raiz.findGroup(nome)
    if g is None:
        alvo = nome.lower()
        g = next((x for x in raiz.findGroups(True) if x.name().lower() == alvo), None)
    if g is None and criar:
        g = raiz.insertGroup(0, nome)
    return g


def create_group(name):
    """Cria um grupo no painel de camadas (se ainda não existir)."""
    existia = _grupo(name, criar=False) is not None
    _grupo(name)
    return {"success": True, "grupo": name, "aviso": "o grupo já existia" if existia else None}


def move_layer_to_group(layer_name, group):
    """Põe a camada dentro de um grupo do painel (cria o grupo se não existir)."""
    camada = _layer(layer_name)
    g = _grupo(group)
    raiz = _proj().layerTreeRoot()
    no = raiz.findLayer(camada.id())
    if no is None:
        raise ValueError(f"'{layer_name}' não está no painel de camadas.")
    clone = no.clone()
    g.insertChildNode(0, clone)
    no.parent().removeChildNode(no)
    return {"success": True, "layer": layer_name, "grupo": g.name()}


def set_layer_crs(layer_name, crs):
    """Define (corrige) o sistema de coordenadas da camada SEM mexer nas coordenadas.
    Para converter as coordenadas use a reprojeção."""
    camada = _layer(layer_name)
    destino = QgsCoordinateReferenceSystem(str(crs))
    if not destino.isValid():
        raise ValueError(f"Sistema de coordenadas inválido: {crs}")
    antes = camada.crs().authid()
    camada.setCrs(destino)
    camada.triggerRepaint()
    return {"success": True, "layer": layer_name, "antes": antes, "sistema": destino.authid()}


def copy_style(from_layer, to_layer):
    """Copia o estilo inteiro (cores, classes, rótulos, transparência) de uma camada para outra."""
    origem, destino = _layer(from_layer), _layer(to_layer)
    if origem.type() != destino.type():
        raise ValueError("As duas camadas precisam ser do mesmo tipo (vetor com vetor, raster com raster).")
    estilo = QgsMapLayerStyle()
    estilo.readFromLayer(origem)
    estilo.writeToLayer(destino)
    destino.triggerRepaint()
    return {"success": True, "layer": to_layer, "estilo_de": from_layer}


TOOLS = {
    "save_layer_to_project": save_layer_to_project,
    "project_storage_info": project_storage_info,
    "create_layer": create_layer,
    "load_files": load_files,
    "create_group": create_group,
    "move_layer_to_group": move_layer_to_group,
    "set_layer_crs": set_layer_crs,
    "copy_style": copy_style,
    "fill_field_by_location": fill_field_by_location,
}
