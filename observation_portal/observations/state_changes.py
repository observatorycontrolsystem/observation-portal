def on_configuration_state_change(instance):
    TERMINAL_OBSERVATION_STATES = ['CANCELED', 'ABORTED', 'FAILED']
    # Configuration Status state has changed, so see if Observation state should be updated and update
    if instance.observation.state in TERMINAL_OBSERVATION_STATES:
        # if it is already in a terminal state, do nothing
        return

    configuration_statuses = instance.observation.configuration_statuses
    states = [config_status.state for config_status in configuration_statuses]
    if all([state == 'PENDING' or state == 'ATTEMPTED' for state in states]):
        instance.observation.state = 'IN_PROGRESS'
    elif any([state == 'FAILED' for state in states]):
        instance.observation.state = 'FAILED'
    elif any([state == 'ABORTED' for state in states]):
        instance.observation.state = 'ABORTED'
    elif all([state == 'COMPLETED' for state in states]):
        instance.observation.state = 'COMPLETED'

    instance.observation.save()



