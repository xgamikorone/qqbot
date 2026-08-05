import unittest

from commands.base import _command_registry
from commands.help_catalog import CommandHelp, HelpCatalog


class PublicCommand:
    name = "demo"
    cn_name = "示例"
    owner_only = False
    hidden = False
    help = CommandHelp(
        title="示例",
        category="工具",
        summary="演示帮助目录",
        usage="/示例 <参数>",
        examples=("/示例 1",),
        lookup_names=("演示",),
    )


class OwnerCommand:
    name = "owner_demo"
    cn_name = "作者示例"
    owner_only = True
    hidden = False
    help = CommandHelp(
        title="作者示例",
        category="系统",
        summary="仅作者可用",
    )


class HiddenCommand:
    name = "hidden_demo"
    cn_name = "隐藏示例"
    owner_only = False
    hidden = True
    help = CommandHelp(
        title="隐藏示例",
        category="系统",
        summary="不应出现",
    )


class HelpCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = HelpCatalog(
            {
                "示例": PublicCommand,
                "demo": PublicCommand,
                "owner_demo": OwnerCommand,
                "hidden_demo": HiddenCommand,
            }
        )

    def test_overview_groups_documented_commands(self):
        content = self.catalog.render()

        self.assertIn("【工具】", content)
        self.assertIn("/示例 — 演示帮助目录", content)
        self.assertNotIn("作者示例", content)
        self.assertNotIn("隐藏示例", content)

    def test_alias_and_extra_lookup_name_resolve_same_help(self):
        alias_content = self.catalog.render("/demo")
        lookup_name_content = self.catalog.render("演示")

        self.assertEqual(alias_content, lookup_name_content)
        self.assertIn("用法：", alias_content)
        self.assertIn("/示例 <参数>", alias_content)

    def test_category_query_lists_category_commands(self):
        content = self.catalog.render("工具")

        self.assertTrue(content.startswith("【工具】"))
        self.assertIn("/示例", content)

    def test_unknown_query_suggests_close_command(self):
        content = self.catalog.render("示列")

        self.assertIn("你可能想找", content)
        self.assertIn("/帮助 示例", content)

    def test_owner_commands_require_explicit_visibility(self):
        hidden_content = self.catalog.render("owner_demo")
        visible_content = self.catalog.render("owner_demo", include_owner=True)

        self.assertIn("没有找到", hidden_content)
        self.assertIn("仅作者可用", visible_content)


class RegisteredHelpTests(unittest.TestCase):
    def test_feature_commands_are_registered_and_documented(self):
        catalog = HelpCatalog(_command_registry)

        self.assertIn("斗虫", _command_registry)
        self.assertIn("/斗虫", catalog.render())
        self.assertIn("昵称管理帮助", catalog.render("查uid"))
        self.assertIn("查询当前分类舰长数", catalog.render("num_guards"))

    def test_owner_feature_is_filtered_from_public_overview(self):
        catalog = HelpCatalog(_command_registry)

        self.assertNotIn("/老婆刷新时间", catalog.render())
        self.assertIn("/老婆刷新时间", catalog.render(include_owner=True))


if __name__ == "__main__":
    unittest.main()
