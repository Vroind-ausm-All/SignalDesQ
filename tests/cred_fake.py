"""Gemeinsamer Ersatz-Passwortspeicher für Tests (SDQ-004): Tests berühren nie den echten Schlüsselbund des Rechners."""


class FakeStore:
    name = 'Test-Passwortspeicher'

    def __init__(self, fail=False):
        self.data, self.fail = {}, fail

    def get(self, account):
        return self.data.get(account)

    def set(self, account, secret):
        if self.fail:
            raise OSError('verweigert')
        self.data[account] = secret

    def delete(self, account):
        self.data.pop(account, None)
