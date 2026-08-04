import unittest

from dao import Dao


class NicknameRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")

    def tearDown(self):
        self.dao.close()

    def test_add_lookup_and_global_uniqueness(self):
        self.assertTrue(self.dao.nicknames.add(1, "Alice"))
        self.assertTrue(self.dao.nicknames.add(1, "Alice旧名"))
        self.assertFalse(self.dao.nicknames.add(2, "Alice"))
        self.assertEqual(1, self.dao.nicknames.get_uid("Alice"))
        self.assertEqual([1], self.dao.nicknames.find_uids("Alice"))
        self.assertEqual(["Alice", "Alice旧名"], self.dao.nicknames.get_for_uid(1))

    def test_delete_by_name_and_uid(self):
        self.dao.nicknames.add(1, "Alice")
        self.dao.nicknames.add(1, "Alice旧名")
        self.assertTrue(self.dao.nicknames.delete("Alice"))
        self.assertIsNone(self.dao.nicknames.get_uid("Alice"))
        self.assertTrue(self.dao.nicknames.delete_for_uid(1))
        self.assertEqual([], self.dao.nicknames.get_for_uid(1))


if __name__ == "__main__":
    unittest.main()
