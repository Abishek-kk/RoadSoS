import sys
from sqlalchemy.orm import Session
from app.services.route_service import get_safest_route, RouteNode
from app.services.sos_service import trigger_sos_workflow
from app.models.sos import SOSCreate
from db.database import SessionLocal, init_db

def test_route_service():
    print("Testing Route Service...")
    # Create mock nodes
    nodes = [
        {"id": "A", "lat": 13.0827, "lng": 80.2707, "name": "StartPoint"},
        {"id": "B", "lat": 13.0840, "lng": 80.2720, "name": "MidPoint"},
        {"id": "C", "lat": 13.0860, "lng": 80.2740, "name": "GoalPoint"}
    ]
    edges = [
        {"from": "A", "to": "B", "distance_km": 0.5, "risk_score": 1.0},
        {"from": "B", "to": "C", "distance_km": 0.5, "risk_score": 2.0}
    ]
    
    result = get_safest_route(
        nodes=nodes,
        start="A",
        goal="C",
        edges=edges
    )
    
    print("Route Result:", result)
    assert result["reachable"] == True
    assert result["path"] == ["A", "B", "C"]
    print("Route Service Test Passed!")

def test_sos_service():
    print("Testing SOS Service...")
    db = SessionLocal()
    try:
        payload = SOSCreate(
            user="Test User",
            lat=13.0827,
            lng=80.2707,
            speed=0.0,
            accuracy_m=10.0,
            battery_percent=85,
            device_id="test-device",
            severity="high",
            emergency_type="accident",
            note="Test SOS Note"
        )
        
        result = trigger_sos_workflow(db, payload)
        print("SOS Result:", result)
        assert result["ok"] == True
        assert result["status"] == "active"
        print("SOS Service Test Passed!")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    test_route_service()
    test_sos_service()
