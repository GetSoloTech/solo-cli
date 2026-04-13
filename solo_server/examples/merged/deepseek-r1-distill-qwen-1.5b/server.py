import litserve as ls
from transformers import pipeline

class HuggingFaceLitAPI(ls.LitAPI):
    def setup(self, device):
        # Load the model and tokenizer from Hugging Face Hub
        # For example, using the `distilbert-base-uncased-finetuned-sst-2-english` model for sentiment analysis
        # You can replace the model name with any model from the Hugging Face Hub
        model_name = "distilbert-base-uncased-finetuned-sst-2-english"
        self.pipeline = pipeline("text-classification", model=model_name, device=0 if device=="gpu" else -1)

    def decode_request(self, request):
        # Extract text from request
        # This assumes the request payload is of the form: {'text': 'Your input text here'}
        return request["text"]

    def predict(self, text):
        # Use the loaded pipeline to perform inference
        return self.pipeline(text)

    def encode_response(self, output):
        # Format the output from the model to send as a response
        # This example sends back the label and score of the prediction
        return {"label": output[0]["label"], "score": output[0]["score"]}

if __name__ == "__main__":
    # Create an instance of your API
    api = HuggingFaceLitAPI()
    # Start the server, specifying the port
    server = ls.LitServer(api, accelerator="cuda")
    server.run(port=8000)