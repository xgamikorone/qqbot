import os
import asyncio
from typing import Optional, Dict, Any, AsyncIterator

import aiohttp
import dotenv

dotenv.load_dotenv()

SHUIMO_TOKEN = os.getenv("SHUIMO_TOKEN", None)
if SHUIMO_TOKEN is None:
    raise ValueError("请设置 SHUIMO_TOKEN 环境变量")


class AsyncShuimoImageClient:
    """
    水墨图床 aiohttp 异步客户端（带自动重试 + 自动分页）
    """

    def __init__(
        self,
        base_url: str="https://img.ink/",
        token: str=SHUIMO_TOKEN,
        *,
        timeout: int = 15,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout)

        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

        self._session: Optional[aiohttp.ClientSession] = None

    # ======================
    # Session 管理
    # ======================

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={
                "token": self.token,
                "User-Agent": "AsyncShuimoImageClient/1.1",
            },
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError(
                "ClientSession 未初始化，请使用 async with"
            )
        return self._session

    # ======================
    # 内部请求（自动重试）
    # ======================

    async def _post(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        session = self._get_session()

        for attempt in range(1, self.max_retries + 1):
            try:
                async with session.post(url, params=params, data=data) as resp:
                    resp.raise_for_status()
                    result = await resp.json()

                if result.get("code") != 200:
                    raise RuntimeError(f"API Error: {result}")

                return result

            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                if attempt >= self.max_retries:
                    raise

                delay = self.retry_base_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        raise RuntimeError("Unreachable")

    # ======================
    # 基础 API
    # ======================

    async def upload_image(
        self,
        image_path: str,
        *,
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)

        
        with open(image_path, "rb") as fp:
            form = aiohttp.FormData()
            form.add_field(
                "image",
                fp,
                filename=os.path.basename(image_path),
                content_type="application/octet-stream",
            )

            if folder:
                form.add_field("folder", folder)

            return await self._post("/api/upload", data=form)

    async def list_images(
        self,
        *,
        page: int = 1,
        rows: int = 20,
    ) -> Dict[str, Any]:
        return await self._post(
            "/api/images",
            params={
                "page": str(page),
                "rows": str(rows),
            },
        )

    async def delete_image(self, image_id: int | str) -> Dict[str, Any]:
        return await self._post(
            "/api/delete",
            params={"id": str(image_id)},
        )

    # ======================
    # 自动分页迭代器 ⭐
    # ======================

    async def iter_images(
        self,
        *,
        rows: int = 50,
        start_page: int = 1,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        自动分页遍历所有图片
        """
        page = start_page

        while True:
            result = await self.list_images(page=page, rows=rows)
            page_data = result["data"]

            for img in page_data["data"]:
                yield img

            if page >= page_data["last_page"]:
                break

            page += 1

    # ======================
    # 不可用接口
    # ======================

    async def get_image(self, image_id: int | str):
        raise NotImplementedError(
            "get_image API 在水墨图床文档中标注为不可用"
        )
