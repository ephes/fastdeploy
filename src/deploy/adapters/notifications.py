import abc


class AbstractNotifications(abc.ABC):
    @abc.abstractmethod
    def send(self, destination, message):
        raise NotImplementedError


DEFAULT_HOST = "localhost"
DEFAULT_PORT = "25"


class EmailNotifications(AbstractNotifications):
    def __init__(self, smtp_host=DEFAULT_HOST, port=DEFAULT_PORT):
        pass
        # self.server = smtplib.SMTP(smtp_host, port=port)
        # self.server.noop()

    def send(self, destination, message):
        ...
        # msg = f"Subject: allocation service notification\n{message}"
        # self.server.sendmail(
        #     from_addr="fastdeploy@deploy.django-cast.com",
        #     to_addrs=[destination],
        #     msg=msg,
        # )
