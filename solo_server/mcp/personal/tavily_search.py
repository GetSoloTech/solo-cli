from tavily import Client
from pydantic import BaseModel
from litserve.mcp import MCP
import litserve as ls

class SearchRequest(BaseModel):
    query: str

class SearchAPI(ls.LitAPI):
    def setup(self, device):
        # Initialize Tavily client for web search
        self.client = Client(api_key="YOUR_TAVILY_API_KEY")

    def decode_request(self, request: SearchRequest):
        return request.query

    def predict(self, x):
        # Perform an internet search with Tavily
        response = self.client.search(
            query=x,
            top_k=5,
            web=True  # enable web search mode
        )
        # Format results
        results = []
        for hit in response.get("hits", []):
            results.append({
                "title": hit.get("title", ""),
                "snippet": hit.get("snippet", ""),
                "url": hit.get("url", ""),
                "score": hit.get("score", 0.0)
            })
        return results

    def encode_response(self, output):
        return {"results": output}

if __name__ == "__main__":
    api = SearchAPI(
        mcp=MCP(
            description="Performs internet search using Tavily Search"
        )
    )
    server = ls.LitServer(api)
    server.run(port=8000)
