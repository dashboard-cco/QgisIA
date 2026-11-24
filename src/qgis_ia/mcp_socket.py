# -*- coding: utf-8 -*-
"""
Servidor socket dentro do QGIS.

Recebe pedidos da ponte MCP (mcp_server.py) e executa as mesmas ações do plugin
no thread principal do QGIS (o QTcpServer entrega tudo pelo event loop principal).
Escuta apenas em 127.0.0.1 e exige um token aleatório gerado a cada início.
"""
import json
import os
import secrets
import shutil
import sys

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtNetwork import QTcpServer, QHostAddress

from .executor import ACTIONS
from .actions import inspection, editing, styling, mapas, geoproc, camadas, code as code_actions
from . import protocol

DEFAULT_PORT = 9876
PORT_TRIES = 10
MAX_BUFFER = 50 * 1024 * 1024


def build_funcs():
    funcs = dict(ACTIONS)
    for module in (inspection, editing, styling, mapas, geoproc, camadas, code_actions):
        funcs.update(module.TOOLS)
    return funcs


def _localhost():
    addr = getattr(QHostAddress, "LocalHost", None)
    if addr is None:
        addr = QHostAddress.SpecialAddress.LocalHost
    return addr


class McpSocketServer(QObject):
    status_changed = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = None
        self.clients = {}
        self.token = ""
        self.port = None
        self.read_only = False
        self.allow_code = False
        self.funcs = build_funcs()

    # --- utilidades -------------------------------------------------------
    @staticmethod
    def bridge_path():
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")

    @staticmethod
    def python_path():
        """Caminho de um Python que sirva para rodar a ponte.

        A ponte só usa a biblioteca padrão, então qualquer Python 3.8+ serve.
        Preferimos o do próprio QGIS, que com certeza existe. No Windows,
        sys.executable costuma ser qgis-bin.exe, e aí procuramos o python.exe
        que acompanha a instalação.
        """
        exe = sys.executable or ""
        if "python" in os.path.basename(exe).lower():
            return exe

        base = os.path.dirname(exe)
        names = ["python3.exe", "python.exe"] if os.name == "nt" else ["python3", "python"]
        roots = [base, os.path.join(base, "..", "bin"), os.path.dirname(base)]
        try:
            import sysconfig
            for key in ("scripts", "data", "stdlib"):
                path = sysconfig.get_path(key)
                if path:
                    roots.append(path)
                    roots.append(os.path.dirname(path))
        except Exception:
            pass
        for root in roots:
            for name in names:
                candidate = os.path.normpath(os.path.join(root, name))
                if os.path.isfile(candidate):
                    return candidate

        found = shutil.which("python3") or shutil.which("python")
        return found or ("python" if os.name == "nt" else "python3")

    def is_running(self):
        return self.server is not None and self.server.isListening()

    def set_read_only(self, value):
        self.read_only = bool(value)
        self.log.emit("Modo somente leitura " + ("ligado" if self.read_only else "desligado"))

    def set_allow_code(self, value):
        self.allow_code = bool(value)
        self.log.emit("Execução de código Python "
                      + ("LIBERADA" if self.allow_code else "bloqueada"))

    # --- ciclo de vida ----------------------------------------------------
    def start(self):
        if self.is_running():
            return True
        server = QTcpServer(self)
        port = None
        for candidate in range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES):
            if server.listen(_localhost(), candidate):
                port = candidate
                break
        if port is None:
            msg = f"Não foi possível abrir porta entre {DEFAULT_PORT} e {DEFAULT_PORT + PORT_TRIES - 1}."
            self.status_changed.emit(msg)
            self.log.emit(msg)
            server.deleteLater()
            return False

        self.server = server
        self.port = port
        self.token = secrets.token_hex(16)
        server.newConnection.connect(self._on_new_connection)
        protocol.write_config("127.0.0.1", port, self.token)
        msg = f"Servidor MCP ativo em 127.0.0.1:{port}"
        self.status_changed.emit(msg)
        self.log.emit(msg)
        return True

    def stop(self):
        for sock in list(self.clients):
            try:
                sock.close()
            except Exception:
                pass
        self.clients.clear()
        if self.server is not None:
            self.server.close()
            self.server.deleteLater()
            self.server = None
        self.token = ""
        protocol.remove_config()
        self.status_changed.emit("Servidor parado.")
        self.log.emit("Servidor MCP parado.")

    # --- conexões ---------------------------------------------------------
    def _on_new_connection(self):
        while self.server is not None and self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self.clients[sock] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))

    def _on_disconnected(self, sock):
        self.clients.pop(sock, None)
        sock.deleteLater()

    def _on_ready_read(self, sock):
        buf = self.clients.get(sock)
        if buf is None:
            return
        buf.extend(bytes(sock.readAll()))
        if len(buf) > MAX_BUFFER:
            self.log.emit("Pedido grande demais; conexão encerrada.")
            sock.close()
            return
        while b"\n" in buf:
            idx = buf.index(b"\n")
            line = bytes(buf[:idx])
            del buf[:idx + 1]
            if not line.strip():
                continue
            resp = protocol.handle_request(
                line.decode("utf-8", "replace"), self.funcs, self.token,
                self.read_only, self.allow_code
            )
            tool = resp.get("tool")
            if tool:
                status = "ok" if resp.get("ok") else "ERRO: " + str(resp.get("error"))
                self.log.emit(f"MCP {tool} → {status}")
            sock.write(protocol.encode(resp))
            sock.flush()
