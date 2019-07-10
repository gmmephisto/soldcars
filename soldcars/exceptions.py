class BaseError(Exception):
    pass


class CarNotFound(BaseError):
    def __init__(self, serial):
        super().__init__(f"Car with serial number '{serial}' not found.")


class CarAlreadyExists(BaseError):
    def __init__(self, serial):
        super().__init__(f"Car with serial number '{serial}' already exists.'")
