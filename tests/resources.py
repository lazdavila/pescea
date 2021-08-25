from pytest import fixture

@fixture
def fireplaces():
    """Fixture to return a set of fireplaces to test with"""
    return {
        1111: {
            "IPAddress": "8.8.8.8",
            "DeviceUId": 1111,
            "ControllerState": "Ready",
            "HasNewTimers": False,
            "FireIsOn": False,
            "FanMode": "Auto",
            "DesiredTemp": 19.0,
            "CurrentTemp": 16.0
        },
        2222: {
            "IPAddress": "8.8.4.4",
            "DeviceUId": 2222,
            "ControllerState": "Ready",
            "HasNewTimers": False,
            "FireIsOn": True,
            "FanMode": "FanBoost",
            "DesiredTemp": 24.0,
            "CurrentTemp": 22.0
        },
        33333: {
            "IPAddress": "8.8.8.4",
            "DeviceUId": 33333,
            "ControllerState": "Ready",
            "HasNewTimers": True,
            "FireIsOn": True,
            "FanMode": "FlameEffect",
            "DesiredTemp": 20.0,
            "CurrentTemp": 20.0
        }
    }
