from django.apps import AppConfig


class ProposalsConfig(AppConfig):
    name = 'observation_portal.proposals'

    def ready(self):
        import observation_portal.proposals.signals.handlers  # noqa
        super().ready()
