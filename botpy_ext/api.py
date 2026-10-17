from botpy.api import BotAPI
from botpy.http import Route

from .models import GlobalMenuResponse


class ExtendedBotAPI(BotAPI):
    """Extend the installed BotAPI without replacing its HTTP client or credentials."""

    async def get_global_menu(self) -> GlobalMenuResponse | None:
        """Query GET /v2/menu (30 QPM); menu may be null before configuration.

        SDK authentication, sandbox selection and error handling are reused.
        A None response follows botpy's existing timeout behavior. No menu is
        created or modified, and this method is never called automatically.
        """
        return await self._http.request(Route("GET", "/v2/menu"))
