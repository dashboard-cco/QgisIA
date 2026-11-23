# -*- coding: utf-8 -*-
"""
Actions: layout - Exportação de layouts/mapás
"""
from qgis.core import QgsProject, QgsLayoutExporter


def export_pdf(layout_name, output_path):
    """Exporta layout de impressão para PDF."""
    project = QgsProject.instance()
    manager = project.layoutManager()
    layout = manager.layoutByName(layout_name)

    if not layout:
        layouts = [l.name() for l in manager.layouts()]
        raise ValueError(f"Layout '{layout_name}' não encontrado. Disponíveis: {layouts}")

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.PdfExportSettings()
    result = exporter.exportToPdf(output_path, settings)

    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Falha ao exportar PDF: código {result}")

    return {"success": True, "output_path": output_path}


def export_image(layout_name, output_path, dpi=300):
    """Exporta layout para imagem (PNG/JPG)."""
    project = QgsProject.instance()
    manager = project.layoutManager()
    layout = manager.layoutByName(layout_name)

    if not layout:
        raise ValueError(f"Layout '{layout_name}' não encontrado")

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = dpi
    result = exporter.exportToImage(output_path, settings)

    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Falha ao exportar imagem: código {result}")

    return {"success": True, "output_path": output_path}


def list_layouts():
    """Lista todos os layouts do projeto."""
    return [l.name() for l in QgsProject.instance().layoutManager().layouts()]