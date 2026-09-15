from gateway.shared.transaction import Transaction, TransactionAction


class DatabaseTransaction(Transaction):
    def __init__(self) -> None:
        self._after_commit: list[TransactionAction] = []

    def after_commit(self, action: TransactionAction) -> None:
        self._after_commit.append(action)

    def complete(self) -> None:
        actions = tuple(self._after_commit)
        self._after_commit.clear()
        for action in actions:
            action()
