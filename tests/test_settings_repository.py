import unittest

from dao import Dao


class SettingsRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.dao = Dao(":memory:")

    def tearDown(self):
        self.dao.close()

    def test_wife_refresh_time_has_default_and_can_be_updated(self):
        self.assertEqual("08:00", self.dao.settings.wife_refresh_time)
        self.assertTrue(self.dao.settings.set_wife_refresh_time("09:30"))
        self.assertEqual("09:30", self.dao.settings.wife_refresh_time)


if __name__ == "__main__":
    unittest.main()
