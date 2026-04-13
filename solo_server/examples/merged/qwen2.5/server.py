from fastapi import HTTPException
from stock_researcher import research_financials, research_news, stock_researcher, load_model
import litserve as ls

model_id = "Qwen/Qwen2.5-7B-Instruct"

class StockAnalyst(ls.LitAPI):
    def setup(self, device):
        # Using a self hosted open-source model with OpenAI API compatible interface
        self.model = model_id

    def decode_request(self, request: dict):
        # Query containing the stock name to research
        return request["query"]

    def predict(self, query: str):
        try:
            # 1. Find financial info
            messages, financials = research_financials(query, self.model)
            # 2. Research news about stocks
            tool_calls, tool_final_result = research_news(financials, query, self.model)
            # 3. Analyze data
            yield from stock_researcher(tool_final_result, tool_calls, messages, self.model)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Stock analyst ran into an error")

    def encode_response(self, response):
        for chunk in response:
            yield chunk

if __name__ == "__main__":
    load_model(model_id)
    api = StockAnalyst()
    server = ls.LitServer(api, workers_per_device=8, accelerator="cpu", timeout=False, stream=True)
    server.run(port=8888)