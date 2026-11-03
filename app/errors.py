class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status
