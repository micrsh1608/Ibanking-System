from services.account.database import Base, engine
from services.account import models
from shared.migrations import upgrade


def migrate():
    upgrade(engine, [('20261104_account_cancellation', lambda connection: Base.metadata.create_all(connection))])


if __name__ == '__main__':
    migrate()
