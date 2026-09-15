from abc import ABC, abstractmethod
from collections.abc import Callable

type TransactionAction = Callable[[], None]


class Transaction(ABC):
    @abstractmethod
    def after_commit(self, action: TransactionAction) -> None: ...
