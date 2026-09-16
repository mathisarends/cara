class EventBusError(Exception):
    pass


class NoSubscriberError(EventBusError):
    pass
