import time
import threading
import uuid
from typing import Optional, Literal, Dict
from pydantic import BaseModel, Field
from litserve.mcp import MCP
import litserve as ls

class TimerRequest(BaseModel):
    action: Literal['start', 'cancel', 'list'] = Field(
        ..., description="Action to perform: start a new timer, cancel an existing timer, or list active timers"
    )
    hours: Optional[int] = Field(0, ge=0, description="Hours for timer duration (used when starting)")
    minutes: Optional[int] = Field(0, ge=0, description="Minutes for timer duration (used when starting)")
    seconds: Optional[int] = Field(0, ge=0, description="Seconds for timer duration (used when starting)")
    timer_id: Optional[str] = Field(None, description="ID of timer to cancel (used when cancelling)")

class TimerAPI(ls.LitAPI):
    def setup(self, device):
        # Initialize storage for active timers
        self.timers: Dict[str, Dict] = {}

    def decode_request(self, request: TimerRequest):
        return request

    def predict(self, req: TimerRequest):
        if req.action == 'start':
            # Compute total duration in seconds
            total = req.hours * 3600 + req.minutes * 60 + req.seconds
            if total <= 0:
                return {"error": "Duration must be greater than zero."}
            # Generate a unique timer ID
            timer_id = str(uuid.uuid4())
            end_time = time.time() + total

            # Callback to clean up after completion
            def _complete(tid):
                print(f"Timer {tid} completed.")
                self.timers.pop(tid, None)

            # Create and start the timer thread
            t = threading.Timer(total, _complete, args=(timer_id,))
            t.start()
            # Store timer metadata
            self.timers[timer_id] = {"thread": t, "end_time": end_time}
            return {"timer_id": timer_id, "message": f"Timer started for {total} seconds."}

        elif req.action == 'cancel':
            tid = req.timer_id
            if not tid or tid not in self.timers:
                return {"error": "Invalid or missing timer_id."}
            # Cancel and remove
            self.timers[tid]['thread'].cancel()
            self.timers.pop(tid, None)
            return {"timer_id": tid, "message": "Timer cancelled."}

        elif req.action == 'list':
            # List active timers with remaining time
            now = time.time()
            active = []
            for tid, info in self.timers.items():
                remaining = max(0, int(info['end_time'] - now))
                active.append({"timer_id": tid, "remaining_seconds": remaining})
            return {"active_timers": active}

        else:
            return {"error": "Unsupported action."}

    def encode_response(self, output):
        return output

if __name__ == "__main__":
    api = TimerAPI(
        mcp=MCP(
            description="Manages timers: start, cancel, and list active timers"
        )
    )
    server = ls.LitServer(api)
    server.run(port=8000)
