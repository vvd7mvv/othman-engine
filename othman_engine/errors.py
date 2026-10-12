class ProcessingError(Exception):
    """خطأ متوقع: code ثابت يمكن ترجمته في واجهة، والرسالة للقراءة."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
