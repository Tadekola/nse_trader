from pydantic import BaseModel
from typing import Optional

class Stock(BaseModel):
    symbol: str
    name: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None
