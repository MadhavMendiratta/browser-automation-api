from pydantic import BaseModel
from typing import List , Optional , Dict 

#Timing Model - telling how much time it woud take to load page
class TimingModel(BaseModel):
    start_time: float
    domain_lookup_start: float
    domain_lookup_end: float
    connect_start: float
    secure_connection_start: float
    connect_end: float
    request_start: float
    response_start: float
    response_end: float

