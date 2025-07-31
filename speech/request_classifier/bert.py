from transformers import AutoTokenizer, BertForSequenceClassification
from peft import PeftModel

from speech import RequestType

class RequestClassifierBERT:
    def __init__(self):
        base_model_name = "bert-base-uncased"
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name)
        base_model = BertForSequenceClassification.from_pretrained(base_model_name, num_labels=3)

        lora_path = "models/request-classifier"
        self.model = PeftModel.from_pretrained(base_model, lora_path)

        self.class_map = {
            0: RequestType.QUERY,
            1: RequestType.NOT_QUERY,
            2: RequestType.INCOMPLETE_QUERY
        }

    def classify(self, text, return_logits=False):
        return RequestType.INCOMPLETE_QUERY
        text = ''.join(char for char in text if char.isalnum() or char.isspace())
        text = text.strip()
        text = text.lower()

        inputs = self.tokenizer(text, return_tensors="pt")
        outputs = self.model(**inputs)
        logits = outputs.logits
        if return_logits:
            return logits
        predicted_class = logits.argmax(dim=-1).item()
        return self.class_map[predicted_class]
        