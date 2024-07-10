from django.apps import AppConfig


class SciapplicationsConfig(AppConfig):
    name = 'observation_portal.sciapplications'

    def ready(self):
        import observation_portal.sciapplications.signals # noqa
        super().ready()
