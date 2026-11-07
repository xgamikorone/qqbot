"""Offline multipart protocol tests; no real QQ or storage requests."""

import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from botpy_ext import group_upload


class GroupUploadTests(unittest.IsolatedAsyncioTestCase):
    """Checks upload bytes, control payloads and failure ordering."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "rank.png"
        self.path.write_bytes(b"abcdef")
        self.plan = {
            "upload_id":
                "upload",
            "block_size":
                "4",
            "parts": [
                {
                    "index":
                        1,
                    "block_size":
                        "2",
                    "presigned_url":
                        "https://storage.invalid/1?signature=secret"
                },
                {
                    "index":
                        0,
                    "block_size":
                        "4",
                    "presigned_url":
                        "https://storage.invalid/0?signature=secret"
                },
            ],
        }
        self.api = mock.Mock()
        self.api._http.request = mock.AsyncMock(side_effect=[
            self.plan,
            {},
            {},
            {
                "file_info": "image",
                "file_uuid": "uuid",
                "ttl": 300
            },
        ])
        self.put_response = mock.AsyncMock()
        self.put_response.__aenter__.return_value.status = 200
        self.session = mock.Mock()
        self.session.put.return_value = self.put_response
        self.session_context = mock.AsyncMock()
        self.session_context.__aenter__.return_value = self.session
        self.factory = mock.patch.object(
            group_upload.aiohttp,
            "ClientSession",
            return_value=self.session_context).start()
        self.addCleanup(mock.patch.stopall)
        self.sleep = mock.patch.object(group_upload.asyncio,
                                       "sleep",
                                       new=mock.AsyncMock()).start()

    async def upload(self) -> object:
        """Runs the actual uploader against mocked transports."""
        return await group_upload.upload_group_image(self.api, "group",
                                                     str(self.path))

    async def test_hashes_parts_and_merge_without_auth_on_storage(self) -> None:
        self.assertEqual("image", (await group_upload.upload_group_image(
            self.api, "group", str(self.path)))["file_info"])
        controls = self.api._http.request.await_args_list
        self.assertEqual([
            "/v2/groups/{group_openid}/upload_prepare",
            "/v2/groups/{group_openid}/upload_part_finish",
            "/v2/groups/{group_openid}/upload_part_finish",
            "/v2/groups/{group_openid}/files"
        ], [call.args[0].path for call in controls])
        first = controls[0].kwargs["json"]
        self.assertEqual("6", first["file_size"])
        self.assertEqual(hashlib.md5(b"abcdef").hexdigest(), first["md5"])
        self.assertEqual(hashlib.sha1(b"abcdef").hexdigest(), first["sha1"])
        self.assertEqual(first["md5"], first["md5_10m"])
        puts = self.session.put.call_args_list
        self.assertEqual([b"abcd", b"ef"],
                         [call.kwargs["data"] for call in puts])
        for call in puts:
            self.assertEqual({"data", "allow_redirects"}, set(call.kwargs))
            self.assertFalse(call.kwargs["allow_redirects"])
        self.assertNotIn("headers", self.factory.call_args.kwargs)
        self.assertNotIn("auth", self.factory.call_args.kwargs)
        self.assertFalse(self.factory.call_args.kwargs["trust_env"])
        self.assertEqual(
            {
                "upload_id": "upload",
                "part_index": 1,
                "block_size": "2",
                "md5": hashlib.md5(b"ef").hexdigest()
            }, controls[2].kwargs["json"])
        self.assertEqual(
            {
                "upload_id": "upload",
                "file_name": "rank.png",
                "file_type": 1,
                "srv_send_msg": False
            }, controls[3].kwargs["json"])

    async def test_put_failure_never_confirms_or_merges(self) -> None:
        self.put_response.__aenter__.return_value.status = 500
        with self.assertRaises(ValueError):
            await self.upload()
        self.assertEqual(3, self.session.put.call_count)
        self.assertEqual(1, self.api._http.request.await_count)

    async def test_sdk_json_text_responses_are_decoded(self) -> None:
        self.api._http.request.side_effect = [
            json.dumps(self.plan),
            "{}",
            "{}",
            json.dumps({
                "file_info": "image",
                "file_uuid": "uuid",
                "ttl": 300
            }),
        ]
        media = await group_upload.upload_group_image(self.api, "group",
                                                      str(self.path))
        self.assertEqual("image", media["file_info"])

    async def test_stage_diagnostic_never_logs_network_exception_text(
            self) -> None:
        self.api._http.request.side_effect = RuntimeError(
            "https://storage.invalid?signature=private-value")
        with self.assertLogs(group_upload._LOG, level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                await self.upload()
        self.assertIn("stage=prepare", "".join(logs.output))
        self.assertNotIn("private-value", "".join(logs.output))

    async def test_plan_validation_reports_safe_reason(self) -> None:
        self.api._http.request.side_effect = [{
            "upload_id": "upload",
            "block_size": "4",
            "parts": []
        }]
        with self.assertLogs(group_upload._LOG, level="ERROR") as logs:
            with self.assertRaises(ValueError):
                await self.upload()
        self.assertIn("stage=plan", "".join(logs.output))
        self.assertIn("分片数量与文件大小不符", "".join(logs.output))

    async def test_transient_put_failure_retries_same_bytes(self) -> None:
        bad = mock.AsyncMock()
        bad.__aenter__.return_value.status = 503
        self.session.put.side_effect = [
            bad, self.put_response, self.put_response
        ]
        await self.upload()
        puts = self.session.put.call_args_list
        self.assertEqual(puts[0], puts[1])
        self.assertEqual(4, self.api._http.request.await_count)

    async def test_ack_failure_never_merges(self) -> None:
        self.api._http.request.side_effect = [self.plan, None]
        with self.assertRaises(ValueError):
            await self.upload()
        self.assertEqual(1, self.session.put.call_count)
        self.assertEqual(2, self.api._http.request.await_count)

    async def test_invalid_plans_are_rejected_before_put(self) -> None:
        for parts in ([], [self.plan["parts"][0]], [{
                "index": 0,
                "block_size": "6",
                "presigned_url": "http://storage.invalid/file"
        }]):
            with self.subTest(parts=parts):
                self.api._http.request.side_effect = None
                self.api._http.request.return_value = dict(self.plan,
                                                           parts=parts)
                with self.assertRaises(ValueError):
                    await self.upload()
        self.session.put.assert_not_called()

    async def test_missing_merge_file_info_is_failure(self) -> None:
        self.api._http.request.side_effect = [self.plan, {}, {}, {}]
        with self.assertRaises(ValueError):
            await self.upload()

    async def test_empty_and_oversize_files_fail_before_requests(self) -> None:
        with mock.patch.object(group_upload, "MAX_IMAGE_BYTES", 5):
            with self.assertRaises(ValueError):
                await self.upload()
        self.path.write_bytes(b"")
        with self.assertRaises(ValueError):
            await self.upload()
        self.api._http.request.assert_not_awaited()

    async def test_prefix_hash_uses_exact_documented_byte_count(self) -> None:
        data = b"a" * group_upload.MD5_PREFIX_BYTES + b"tail"
        self.path.write_bytes(data)
        self.api._http.request.side_effect = RuntimeError("stop after prepare")
        with self.assertRaises(RuntimeError):
            await self.upload()
        payload = self.api._http.request.await_args.kwargs["json"]
        self.assertEqual(
            hashlib.md5(data[:10_002_432]).hexdigest(), payload["md5_10m"])
        self.assertNotEqual(payload["md5"], payload["md5_10m"])
