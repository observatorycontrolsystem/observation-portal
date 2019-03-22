from django.apps import AppConfig


class ObservationsConfig(AppConfig):
    name = 'observation_portal.observations'

    def ready(self):
        import observation_portal.observations.signals.handlers  # noqa
        super().ready()
