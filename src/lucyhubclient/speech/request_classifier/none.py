from ...speech import RequestType

class EmptyRequestClassifier:
    def __init__(self):
        pass

    def classify(self, text, return_logits=False):
        return RequestType.INCOMPLETE_QUERY