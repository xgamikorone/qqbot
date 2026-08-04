import os
import unittest
from unittest.mock import patch

from dao import Dao


class OwnerRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")

    def tearDown(self):
        self.dao.close()

    def test_database_owners_can_be_added_listed_and_removed(self):
        self.assertTrue(self.dao.owners.add("123", "admin"))
        self.assertTrue(self.dao.owners.contains("123"))
        self.assertEqual("123", self.dao.owners.get_all()[0]["user_id"])
        self.assertTrue(self.dao.owners.remove("123"))
        self.assertFalse(self.dao.owners.contains("123"))

    def test_environment_owners_are_recognized(self):
        with patch.dict(os.environ, {"BOT_OWNER_IDS": "123, 456"}, clear=False):
            self.assertTrue(self.dao.owners.contains("456"))


if __name__ == "__main__":
    unittest.main()
