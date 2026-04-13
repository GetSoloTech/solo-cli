import litserve as ls
from transformers import pipeline

class HuggingFaceLitAPI(ls.LitAPI):
    def setup(self, device):
        # Load the model and tokenizer from Hugging Face Hub
        # For example, using the `distilbert-base-uncased-finetuned-sst-2-english` model for sentiment analysis
        # You can replace the model name with any model from the Hugging Face Hub
        model_name = "distilbert-base-uncased-finetuned-sst-2-english"
        self.pipeline = pipeline("text-classification", model=model_name, device=device)

    def decode_request(self, request):
        # Extract text from request
        # This assumes the request payload is of the form: {'text': 'Your input text here'}
        return request["text"]

    def batch(self, inputs):
        # return the batched input list
        return inputs

    def predict(self, texts):
        # Use the loaded pipeline to perform inference
        return self.pipeline(texts)

    def unbatch(self, outputs):
        # unbatch the model output
        return outputs

    def encode_response(self, output):
        # Format the output from the model to send as a response
        # This example sends back the label and score of the prediction
        return {"label": output["label"], "score": output["score"]}

if __name__ == "__main__":
    # Create an instance of your API
    api = HuggingFaceLitAPI()
    # Start the server, specifying the port
    server = ls.LitServer(api, accelerator="cuda", max_batch_size=16, workers_per_device=4, batch_timeout=0.01)
    server.run(port=8000)