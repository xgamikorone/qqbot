from database.connection import create_connection
from database.repositories.chuang_repository import ChuangRepository
from database.repositories.command_record_repository import CommandRecordRepository
from database.repositories.nickname_repository import NicknameRepository
from database.repositories.owner_repository import OwnerRepository
from database.repositories.settings_repository import SettingsRepository
from database.repositories.wife_repository import WifeRepository
from database.schema import initialize_schema


DB_NAME = "user.db"


class Dao:
    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name
        self.conn = create_connection(db_name)
        initialize_schema(self.conn)

        self.wives = WifeRepository(self.conn)
        self.chuang = ChuangRepository(self.conn)
        self.command_records = CommandRecordRepository(self.conn)
        self.nicknames = NicknameRepository(self.conn)
        self.owners = OwnerRepository(self.conn)
        self.settings = SettingsRepository(self.conn)

    def close(self) -> None:
        self.conn.close()


_dao_instance: Dao | None = None


def get_dao(db_name: str = DB_NAME) -> Dao:
    global _dao_instance
    if _dao_instance is None:
        _dao_instance = Dao(db_name)
    return _dao_instance
