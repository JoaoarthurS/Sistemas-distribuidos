"""Interface gráfica do servidor: painel web servido por HTTP e atualizado por SSE."""

from .handler import AdminService, DashboardServer

__all__ = ["AdminService", "DashboardServer"]
