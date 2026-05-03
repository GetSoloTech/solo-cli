#Shaan Patel
#July 22, 2025
#YoloV11n MCP

from pydantic import BaseModel
from litserve.mcp import MCP
import litserve as ls
from PIL import Image, ImageOps
from ultralytics import YOLO
import base64
import cv2
import numpy as np
from io import BytesIO


# Define the request schema for analysis
class AnalysisRequest(BaseModel):
    data_path: str  # Path to the input image
    threshold: float = 0.5  # Optional threshold parameter (default 0.5)

# Define the custom LitAPI for YOLOv11n
class YoloV11n(ls.LitAPI):
    def setup(self, device: str):
        # Path to the local YOLO model weights
        model_path = "/Users/shaanpatel/Desktop/Personal/solo/model tests/local_detection_system/live_detection_model/models/best.pt"
        #model_path="/Users/shaanpatel/Desktop/Personal/solo/model tests/local_detection_system/live_detection_model/models/oldmodel.pt"
        self.model = YOLO(model_path)
        
    def decode_request(self, request: AnalysisRequest):
        # Convert the incoming request to a dictionary for inference
        return {"data": request.data_path, "threshold": request.threshold}

    def preprocess_for_inference(self, image_path):

        # 1. Auto-orient
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        # 2. Resize to 640x640 (stretch)
        img = img.resize((640, 640), Image.BILINEAR)
        # 3. Convert to grayscale
        img = img.convert("L")
        # 4. Convert grayscale to 3-channel
        img_np = np.array(img)
        img_gray_3ch = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
        return img_gray_3ch

    def predict(self, inputs: dict):
        image_path = inputs["data"]
        # Preprocess image for inference (minimal, robust)
        frame = self.preprocess_for_inference(image_path)
        # Inference
        results = self.model(frame)
        result = results[0]
        # Draw bounding boxes on the image
        boxed_img = result.plot()  # numpy array (BGR)
        # Convert to PIL Image (for base64 encoding)
        img_pil = Image.fromarray(boxed_img[..., ::-1])
        buffer = BytesIO()
        img_pil.save(buffer, format="JPEG")
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return {
            "result": result.boxes.xyxy.tolist(),
            "confidence": result.boxes.conf.tolist(),
            "image_base64": img_str
        }
        
    def encode_response(self, output: dict):
        # Format the output for the API response
        return {"result": output["result"], "confidence": output["confidence"]}

# Package and publish the MCP tool
if __name__ == "__main__":
    # Create the MCP tool with a name and description
    mcp = MCP(name="YoloV11n", description="YOLOv11n object detection MCP")
    # Instantiate the API with the MCP tool
    api = YoloV11n(mcp=mcp)
    # Create and run the LitServer on the default port
    server = ls.LitServer(api)
    server.run()