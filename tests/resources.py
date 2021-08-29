def test_fireplaces():
    """Fixture to return a set of fireplaces to test with"""
    return {
        1111: {
            'IPAddress': '8.8.8.8',
            'HasNewTimers': False,
            'FireIsOn': False,
            'FanBoost': False,
            'FlameEffect': False,
            'DesiredTemp': 19.0,
            'CurrentTemp': 16.0,
            'Responsive': True
        },
        2222: {
            'IPAddress': '8.8.4.4',
            'HasNewTimers': False,
            'FireIsOn': True,
            'FanBoost': False,
            'FlameEffect': True,
            'DesiredTemp': 24.0,
            'CurrentTemp': 22.0,
            'Responsive': True
        },
        33333: {
            'IPAddress': '8.8.8.4',
            'HasNewTimers': True,
            'FireIsOn': False,
            'FanBoost': True,
            'FlameEffect': False,
            'DesiredTemp': 20.0,
            'CurrentTemp': 20.0,
            'Responsive': True
        }
    }
