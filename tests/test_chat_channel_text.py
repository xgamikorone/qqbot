"""Regression cases for URL rejection in final QQ chat output."""

import unittest

from chat import channel_text


class ChannelTextTests(unittest.TestCase):
    """Checks final display filtering without changing evidence URLs."""

    def test_urls_and_bare_domains_are_removed(self) -> None:
        cases = (
            "参考https://time.is/。",
            "访问 time.is 获取时间。",
            "www.example.com/path?q=1",
            "EXAMPLE.COM:443/path",
            "FTP://example.com/file",
            "https://127.0.0.1:8080/a",
            "192.168.1.1",
            "https://[::1]/foo",
            "例子.中国",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertIn("链接已省略", channel_text.without_links(text))

    def test_markdown_link_labels_survive(self) -> None:
        self.assertEqual("时钟",
                         channel_text.without_links("[时钟](https://time.is/)"))
        self.assertEqual(
            "图片",
            channel_text.without_links("![图片](https://example.com/a.png)"))
        result = channel_text.without_links(
            "查看[资料][ref]\n[ref]: https://time.is/\n")
        self.assertEqual("查看资料\n", result)

    def test_source_label_removes_domain_only_titles(self) -> None:
        self.assertEqual("", channel_text.source_label("time.is"))
        self.assertEqual("当前时间", channel_text.source_label("time.is 当前时间"))

    def test_plain_text_versions_and_decimals_remain(self) -> None:
        text = "温度3.14度，Python 3.12.7，四禧丸子。"
        self.assertEqual(text, channel_text.without_links(text))
