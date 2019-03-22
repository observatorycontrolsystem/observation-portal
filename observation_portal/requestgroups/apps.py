from django.apps import AppConfig


class RequestGroupsConfig(AppConfig):
    name = 'observation_portal.requestgroups'

    def ready(self):
        import observation_portal.requestgroups.signals.handlers  # noqa
        super().ready()
