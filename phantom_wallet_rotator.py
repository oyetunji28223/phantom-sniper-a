"""Round-robin names for virtual simulator wallets; no wallet keys are used."""


class PaperWalletRotator:
    def __init__(self, wallet_names: list[str]) -> None:
        if not wallet_names or any(not name.strip() for name in wallet_names):
            raise ValueError("at least one nonempty virtual wallet name is required")
        if len(set(wallet_names)) != len(wallet_names):
            raise ValueError("virtual wallet names must be unique")
        self._wallet_names = tuple(wallet_names)
        self._next_index = 0

    def next_wallet(self) -> str:
        wallet = self._wallet_names[self._next_index]
        self._next_index = (self._next_index + 1) % len(self._wallet_names)
        return wallet
