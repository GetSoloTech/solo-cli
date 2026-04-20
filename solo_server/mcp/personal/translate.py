from transformers import pipeline
from pydantic import BaseModel
from litserve.mcp import MCP
import litserve as ls

class TranslateRequest(BaseModel):
    text: str = Field(..., description="Text to translate")
    source_lang: str = Field('en', description="Source language code, e.g., 'en'")
    target_lang: str = Field('fr', description="Target language code, e.g., 'fr'")

class TranslateAPI(ls.LitAPI):
    def setup(self, device):
        # Cache translation pipelines per language pair
        self.device = device
        self.translators = {}

    def decode_request(self, request: TranslateRequest):
        return request

    def predict(self, req: TranslateRequest):
        pair = f"{req.source_lang}-{req.target_lang}"
        if pair not in self.translators:
            model_name = f"Helsinki-NLP/opus-mt-{req.source_lang}-{req.target_lang}"
            self.translators[pair] = pipeline(
                "translation", model=model_name, device=self.device
            )
        translator = self.translators[pair]
        result = translator(req.text, max_length=512)
        # Transformers translation pipeline returns a list of dicts
        translation = result[0].get('translation_text') or result[0].get('generated_text')
        return {"translation": translation}

    def encode_response(self, output):
        return output

if __name__ == "__main__":
    api = TranslateAPI(
        mcp=MCP(
            description="Translates text between specified source and target languages"
        )
    )
    server = ls.LitServer(api)
    server.run(port=8000)
