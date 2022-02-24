from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'observation_portal.accounts'

    def ready(self):
        import observation_portal.accounts.signals.handlers  # noqa
        super().ready()
