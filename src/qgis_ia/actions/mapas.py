# -*- coding: utf-8 -*-
"""
Actions: mapas - Ajustes de símbolo, ordem/escala do mapa e layouts de impressão.

Complementa actions/styling.py (renderizadores) com o que os comandos simples
precisam: mexer no símbolo atual sem perder o resto, layouts prontos com
legenda/escala/norte, exportação com caminho automático.
"""
import os
import re

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsLineSymbol,
    QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemPicture, QgsLayoutPoint, QgsLayoutSize,
    QgsLayoutItemPage, QgsLayoutExporter, QgsUnitTypes, QgsRectangle, QgsApplication,
    QgsCoordinateTransform, QgsRenderContext,
)
from qgis.PyQt.QtGui import QColor, QFont

from .styling import _layer, _vector, _color, _refresh

MM = QgsUnitTypes.LayoutMillimeters


def _iface():
    try:
        from qgis.utils import iface
        return iface
    except Exception:
        return None


# ------------------------------------------------------------------ símbolos
def _simbolos(renderer):
    """Todos os símbolos do renderizador (único, categorizado, graduado, regras)."""
    try:
        return list(renderer.symbols(QgsRenderContext()))
    except Exception:
        sym = getattr(renderer, "symbol", lambda: None)()
        return [sym] if sym else []


def update_symbol(layer_name, color=None, outline_color=None, outline_width=None,
                  size=None, no_fill=False):
    """Muda cor, contorno ou tamanho do símbolo SEM recriar o resto do estilo.

    color troca para símbolo único (pinta a camada toda de uma cor); contorno e
    tamanho valem para todas as classes de um estilo categorizado/graduado.
    """
    layer = _vector(layer_name)
    renderer = layer.renderer()
    if (color is not None or no_fill) and not isinstance(renderer, QgsSingleSymbolRenderer):
        simbs = _simbolos(renderer) if renderer else []
        base = simbs[0].clone() if simbs else None
        if base is None:
            from qgis.core import QgsSymbol
            base = QgsSymbol.defaultSymbol(layer.geometryType())
        renderer = QgsSingleSymbolRenderer(base)
        layer.setRenderer(renderer)
    simbolos = [renderer.symbol()] if isinstance(renderer, QgsSingleSymbolRenderer) \
        else _simbolos(renderer)
    if not simbolos:
        raise RuntimeError(f"A camada '{layer_name}' não tem símbolo para ajustar.")
    for sym in simbolos:
        if color is not None:
            sym.setColor(_color(color))
        if no_fill:
            c = QColor(sym.color())
            c.setAlpha(0)
            sym.setColor(c)
        if size is not None:
            if isinstance(sym, QgsMarkerSymbol):
                sym.setSize(float(size))
            elif isinstance(sym, QgsLineSymbol):
                sym.setWidth(float(size))
        for i in range(sym.symbolLayerCount()):
            sl = sym.symbolLayer(i)
            if outline_color is not None and hasattr(sl, "setStrokeColor"):
                sl.setStrokeColor(_color(outline_color))
            if outline_width is not None and hasattr(sl, "setStrokeWidth"):
                sl.setStrokeWidth(float(outline_width))
            if no_fill and hasattr(sl, "setStrokeColor") and hasattr(sl, "setFillColor"):
                if sl.strokeColor().alpha() == 0:
                    sl.setStrokeColor(QColor("#000000"))
    _refresh(layer)
    feito = {k: v for k, v in (("cor", color), ("contorno", outline_color),
                               ("espessura_contorno", outline_width), ("tamanho", size))
             if v is not None}
    if no_fill:
        feito["preenchimento"] = "nenhum"
    return {"success": True, "layer": layer_name, "alterado": feito}


# ------------------------------------------------------------- mapa (canvas)
def move_layer(layer_name, position="top"):
    """Muda a ordem de desenho: top (frente), bottom (fundo), up, down."""
    layer = _layer(layer_name)
    root = QgsProject.instance().layerTreeRoot()
    node = root.findLayer(layer.id())
    if node is None:
        raise RuntimeError(f"Camada '{layer_name}' não está na árvore de camadas.")
    parent = node.parent()
    filhos = parent.children()
    idx = filhos.index(node)
    pos = str(position).lower()
    destino = {"top": 0, "bottom": len(filhos), "up": max(idx - 1, 0),
               "down": min(idx + 2, len(filhos))}.get(pos)
    if destino is None:
        raise ValueError("position deve ser top, bottom, up ou down.")
    clone = node.clone()
    parent.insertChildNode(destino, clone)
    parent.removeChildNode(node)
    return {"success": True, "layer": layer_name, "position": pos}


def _extensao_projeto():
    """União das extensões das camadas visíveis, no CRS do projeto."""
    proj = QgsProject.instance()
    root = proj.layerTreeRoot()
    ext = None
    for layer in proj.mapLayers().values():
        node = root.findLayer(layer.id())
        if node is not None and not node.isVisible():
            continue
        if not isinstance(layer, QgsVectorLayer):  # mapas de fundo cobrem o mundo
            continue
        e = layer.extent()
        if e.isEmpty() and layer.featureCount() == 0:
            continue
        if layer.crs() != proj.crs() and proj.crs().isValid():
            e = QgsCoordinateTransform(layer.crs(), proj.crs(), proj).transformBoundingBox(e)
        if ext is None:
            ext = QgsRectangle(e)
        else:
            ext.combineExtentWith(e)
    return ext if ext is not None else QgsRectangle()


def zoom_full():
    """Mostra todas as camadas do projeto no mapa."""
    iface = _iface()
    if iface is None:
        raise RuntimeError("Canvas do QGIS indisponível.")
    canvas = iface.mapCanvas()
    ext = _extensao_projeto()
    if ext.isEmpty():
        canvas.zoomToFullExtent()
    else:
        ext.scale(1.05)
        canvas.setExtent(ext)
    canvas.refresh()
    return {"success": True}


def set_scale(scale):
    """Escala do mapa: 5000 significa 1:5.000."""
    scale = float(str(scale).replace("1:", "").replace(".", "").replace(",", "."))
    if scale <= 0:
        raise ValueError("Escala inválida.")
    iface = _iface()
    if iface is None:
        raise RuntimeError("Canvas do QGIS indisponível.")
    iface.mapCanvas().zoomScale(scale)
    return {"success": True, "scale": f"1:{int(scale):,}".replace(",", ".")}


def _pasta_saida():
    home = QgsProject.instance().homePath()
    if home and os.path.isdir(home):
        return home
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    pasta = os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "QGIS_IA")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _nome_arquivo(nome):
    nome = re.sub(r'[<>:"/\\|?*]+', "_", str(nome)).strip(" .") or "mapa"
    return nome


def _caminho(output_path, nome, ext):
    """Completa o caminho: pasta → pasta/nome.ext; sem extensão → .ext; vazio → pasta padrão."""
    ext = ext.lower().lstrip(".")
    if not output_path:
        return os.path.join(_pasta_saida(), f"{_nome_arquivo(nome)}.{ext}")
    output_path = os.path.expanduser(str(output_path).strip().strip('"'))
    if os.path.isdir(output_path) or output_path.endswith(("/", "\\")):
        os.makedirs(output_path, exist_ok=True)
        return os.path.join(output_path, f"{_nome_arquivo(nome)}.{ext}")
    if not os.path.splitext(output_path)[1]:
        output_path += f".{ext}"
    pasta = os.path.dirname(output_path)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    return output_path


def export_map_image(output_path=None):
    """Salva o que está no mapa (canvas) como imagem PNG/JPG."""
    iface = _iface()
    if iface is None:
        raise RuntimeError("Canvas do QGIS indisponível.")
    caminho = _caminho(output_path, "mapa", "png")
    iface.mapCanvas().saveAsImage(caminho)
    return {"success": True, "output_path": caminho}


# ------------------------------------------------------------------ layouts
def _layout(layout_name=None):
    manager = QgsProject.instance().layoutManager()
    layouts = manager.printLayouts()
    if not layout_name:
        if len(layouts) == 1:
            return layouts[0]
        if not layouts:
            raise ValueError("O projeto não tem layout. Crie um: 'criar layout com título ...'.")
        raise ValueError("Há mais de um layout; diga qual: " + ", ".join(l.name() for l in layouts))
    layout = manager.layoutByName(layout_name)
    if layout is None:
        alvo = str(layout_name).lower()
        achados = [l for l in layouts if l.name().lower() == alvo]
        if not achados:
            raise ValueError(f"Layout '{layout_name}' não encontrado. Existentes: "
                             + (", ".join(l.name() for l in layouts) or "nenhum"))
        layout = achados[0]
    return layout


def _mapa_do_layout(layout):
    for item in layout.items():
        if isinstance(item, QgsLayoutItemMap):
            return item
    return None


def _nome_livre(base):
    manager = QgsProject.instance().layoutManager()
    if manager.layoutByName(base) is None:
        return base
    n = 2
    while manager.layoutByName(f"{base} {n}") is not None:
        n += 1
    return f"{base} {n}"


def _ancorar(item, x, y, canto="UpperLeft"):
    """Posiciona pelo canto indicado: com 'UpperRight' o item cresce para a
    esquerda quando o QGIS recalcula o tamanho (legenda), sem sair da folha."""
    from qgis.core import QgsLayoutItem
    item.setReferencePoint(getattr(QgsLayoutItem, canto))
    item.attemptMove(QgsLayoutPoint(x, y, MM))


def _texto(layout, texto, tamanho, x, y, largura, negrito=False):
    label = QgsLayoutItemLabel(layout)
    label.setText(texto)
    fonte = QFont("Arial", int(tamanho))
    fonte.setBold(negrito)
    try:
        from qgis.core import QgsTextFormat
        fmt = QgsTextFormat()
        fmt.setFont(fonte)
        fmt.setSize(float(tamanho))
        label.setTextFormat(fmt)
    except Exception:
        label.setFont(fonte)
    label.attemptMove(QgsLayoutPoint(x, y, MM))
    label.attemptResize(QgsLayoutSize(largura, tamanho * 0.6 + 2, MM))
    layout.addLayoutItem(label)
    return label


def _norte(layout, mapa, x, y, lado=15, canto="UpperLeft"):
    pic = QgsLayoutItemPicture(layout)
    caminho = ""
    for base in QgsApplication.svgPaths():
        for nome in ("arrows/NorthArrow_02.svg", "arrows/NorthArrow_04.svg",
                     "arrows/NorthArrow_01.svg"):
            p = os.path.join(base, nome)
            if os.path.exists(p):
                caminho = p
                break
        if caminho:
            break
    if caminho:
        pic.setPicturePath(caminho)
    if mapa is not None:
        try:
            pic.setLinkedMap(mapa)
        except Exception:
            pass
    pic.attemptResize(QgsLayoutSize(lado, lado, MM))
    layout.addLayoutItem(pic)
    _ancorar(pic, x, y, canto)
    return pic


def _legenda(layout, mapa, x, y, titulo="Legenda", canto="UpperLeft"):
    leg = QgsLayoutItemLegend(layout)
    leg.setTitle(titulo)
    if mapa is not None:
        leg.setLinkedMap(mapa)
    # só camadas visíveis e vetoriais (mapa de fundo não entra)
    try:
        leg.setAutoUpdateModel(False)
        root = leg.model().rootGroup()
        for node in list(root.findLayers()):
            lyr = node.layer()
            if lyr is None or not node.isVisible() or not isinstance(lyr, QgsVectorLayer):
                node.parent().removeChildNode(node)
    except Exception:
        pass
    leg.setBackgroundEnabled(True)
    layout.addLayoutItem(leg)
    _ancorar(leg, x, y, canto)
    try:
        leg.adjustBoxSize()
    except Exception:
        pass
    return leg


def _escala(layout, mapa, x, y, largura_max=60.0, canto="UpperLeft"):
    bar = QgsLayoutItemScaleBar(layout)
    bar.setStyle("Single Box")
    if mapa is not None:
        bar.setLinkedMap(mapa)
    bar.applyDefaultSize()
    bar.setNumberOfSegmentsLeft(0)
    bar.setNumberOfSegments(2)
    try:  # a barra inteira cabe em largura_max (o QGIS escolhe um valor redondo)
        from qgis.core import Qgis
        bar.setSegmentSizeMode(Qgis.ScaleBarSegmentSizeMode.FitWidth)
        bar.setMinimumBarWidth(largura_max * 0.4)
        bar.setMaximumBarWidth(largura_max * 0.75)
    except Exception:
        pass
    layout.addLayoutItem(bar)
    _ancorar(bar, x, y, canto)
    try:
        bar.update()
    except Exception:
        pass
    return bar


def create_print_layout(layout_name=None, title=None, orientation="landscape",
                        page_size="A4", legend=True, scalebar=True, north_arrow=True,
                        subtitle=None, open_designer=True):
    """Cria um layout pronto: título, mapa com o enquadramento atual, legenda,
    barra de escala e seta de norte. Abre o layout para edição se houver interface."""
    project = QgsProject.instance()
    manager = project.layoutManager()
    nome = layout_name or _nome_livre(title or "Mapa")
    if manager.layoutByName(nome) is not None:
        raise ValueError(f"Já existe um layout chamado '{nome}'.")

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(nome)
    paisagem = str(orientation).lower() in ("landscape", "paisagem", "horizontal")
    page = layout.pageCollection().page(0)
    ok = page.setPageSize(str(page_size).upper(),
                          QgsLayoutItemPage.Landscape if paisagem else QgsLayoutItemPage.Portrait)
    if not ok:
        raise ValueError(f"Tamanho de página desconhecido: {page_size} (use A0 a A5, Letter...).")
    W = page.pageSize().width()
    H = page.pageSize().height()
    m = 10.0
    topo = m
    if title:
        _texto(layout, title, 18, m, m - 2, W - 2 * m, negrito=True)
        topo += 12
    if subtitle:
        _texto(layout, subtitle, 11, m, topo - 2, W - 2 * m)
        topo += 7

    tem_lado = legend or scalebar or north_arrow
    painel = 55.0 if (tem_lado and paisagem) else 0.0
    rodape = 45.0 if (tem_lado and not paisagem) else 0.0
    mapa_w = W - 2 * m - (painel + 5 if painel else 0)
    mapa_h = H - topo - m - (rodape + 5 if rodape else 0)

    mapa = QgsLayoutItemMap(layout)
    mapa.attemptMove(QgsLayoutPoint(m, topo, MM))
    mapa.attemptResize(QgsLayoutSize(mapa_w, mapa_h, MM))
    mapa.setFrameEnabled(True)
    iface = _iface()
    ext = None
    if iface is not None:
        try:
            ext = iface.mapCanvas().extent()
        except Exception:
            ext = None
    if ext is None or ext.isEmpty():
        ext = _extensao_projeto()
    layout.addLayoutItem(mapa)
    if ext is not None and not ext.isEmpty():
        mapa.zoomToExtent(ext)

    itens = ["mapa"] + (["título"] if title else [])
    if painel:
        px = m + mapa_w + 5
        y = topo
        if north_arrow:
            _norte(layout, mapa, px + (painel - 15) / 2, y)
            y += 20
            itens.append("norte")
        if legend:
            _legenda(layout, mapa, px, y)
            itens.append("legenda")
        if scalebar:
            _escala(layout, mapa, px, H - m, largura_max=painel, canto="LowerLeft")
            itens.append("escala")
    elif rodape:
        y = topo + mapa_h + 5
        if legend:
            _legenda(layout, mapa, m, y)
            itens.append("legenda")
        if north_arrow:
            _norte(layout, mapa, W - m - 15, y)
            itens.append("norte")
        if scalebar:
            _escala(layout, mapa, W - m, H - m, largura_max=80, canto="LowerRight")
            itens.append("escala")

    manager.addLayout(layout)
    if open_designer and iface is not None:
        try:
            iface.openLayoutDesigner(layout)
        except Exception:
            pass
    return {"success": True, "layout_name": nome, "pagina": f"{str(page_size).upper()} "
            f"{'paisagem' if paisagem else 'retrato'}", "itens": itens}


def add_layout_item(item, layout_name=None, text=None):
    """Acrescenta a um layout: legend, scalebar, north_arrow, title ou text."""
    layout = _layout(layout_name)
    mapa = _mapa_do_layout(layout)
    page = layout.pageCollection().page(0).pageSize()
    W, H = page.width(), page.height()
    item = str(item).lower()
    if mapa is not None:
        r = mapa.rectWithFrame()
        p = mapa.positionWithUnits()
        dir_, topo, base = p.x() + r.width() - 3, p.y() + 3, p.y() + r.height() - 3
        esq = p.x() + 3
    else:
        dir_, topo, base, esq = W - 10, 10, H - 10, 10
    if item == "legend":
        _legenda(layout, mapa, dir_, topo, canto="UpperRight")
    elif item == "scalebar":
        bar = _escala(layout, mapa, esq, base, canto="LowerLeft")
        bar.setBackgroundEnabled(True)
    elif item == "north_arrow":
        _norte(layout, mapa, esq, topo)
    elif item in ("title", "text"):
        if not text:
            raise ValueError("Informe o texto.")
        if item == "title":
            _texto(layout, text, 18, 10, 8, W - 20, negrito=True)
        else:
            _texto(layout, text, 10, 10, H - 9, W - 20)
    else:
        raise ValueError("item deve ser legend, scalebar, north_arrow, title ou text.")
    return {"success": True, "layout_name": layout.name(), "item": item}


def remove_layout(layout_name):
    """Apaga um layout do projeto. [destrutivo]"""
    layout = _layout(layout_name)
    nome = layout.name()
    QgsProject.instance().layoutManager().removeLayout(layout)
    return {"success": True, "removed": nome}


def open_layout(layout_name=None):
    """Abre o layout na janela de edição de layouts do QGIS."""
    layout = _layout(layout_name)
    iface = _iface()
    if iface is None:
        raise RuntimeError("Interface do QGIS indisponível.")
    iface.openLayoutDesigner(layout)
    return {"success": True, "layout_name": layout.name()}


def export_layout(layout_name=None, output_path=None, format="pdf", dpi=300):
    """Exporta um layout para PDF, PNG ou JPG. Sem caminho, salva na pasta do projeto."""
    layout = _layout(layout_name)
    fmt = str(format).lower().lstrip(".")
    if fmt in ("jpeg",):
        fmt = "jpg"
    if fmt not in ("pdf", "png", "jpg", "tif", "svg"):
        raise ValueError("Formato deve ser pdf, png, jpg, tif ou svg.")
    caminho = _caminho(output_path, layout.name(), fmt)
    exp = QgsLayoutExporter(layout)
    if fmt == "pdf":
        cfg = QgsLayoutExporter.PdfExportSettings()
        cfg.dpi = int(dpi)
        res = exp.exportToPdf(caminho, cfg)
    elif fmt == "svg":
        res = exp.exportToSvg(caminho, QgsLayoutExporter.SvgExportSettings())
    else:
        cfg = QgsLayoutExporter.ImageExportSettings()
        cfg.dpi = int(dpi)
        res = exp.exportToImage(caminho, cfg)
    if res != QgsLayoutExporter.Success:
        raise RuntimeError(f"Falha ao exportar (código {res}). O arquivo está aberto em outro programa?")
    return {"success": True, "layout_name": layout.name(), "output_path": caminho}


def list_print_layouts():
    """Layouts do projeto com nome e quantidade de páginas."""
    return [{"name": l.name(), "pages": l.pageCollection().pageCount()}
            for l in QgsProject.instance().layoutManager().printLayouts()]


TOOLS = {
    "update_symbol": update_symbol,
    "move_layer": move_layer,
    "zoom_full": zoom_full,
    "set_scale": set_scale,
    "export_map_image": export_map_image,
    "create_print_layout": create_print_layout,
    "add_layout_item": add_layout_item,
    "remove_layout": remove_layout,
    "open_layout": open_layout,
    "export_layout": export_layout,
    "list_print_layouts": list_print_layouts,
}
