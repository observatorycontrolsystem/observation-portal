from django.apps import AppConfig


class ProposalsConfig(AppConfig):
    name = 'valhalla.proposals'

    def ready(self):
        import observation_portal.proposals.signals.handlers  # noqa
        super().ready()
