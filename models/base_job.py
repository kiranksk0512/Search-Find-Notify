from abc import ABC, abstractmethod

class BaseJob(ABC):
    def __init__(self, job_id, title, url, date_posted):
        self.job_id = job_id
        self.title = title
        self.url = url
        self.date_posted = date_posted

    @abstractmethod
    def format_message(self) -> str:
        """Return a formatted message for email alert"""
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        pass