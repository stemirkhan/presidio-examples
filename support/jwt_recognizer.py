"""Detect compact three-part session tokens by shape and JSON header, not by value."""
import base64
import json
from presidio_analyzer import PatternRecognizer,Pattern

class JwtSessionRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(name='JwtSessionRecognizer',supported_entity='ACCESS_TOKEN',supported_language='ru',
                         patterns=[Pattern(name='three_part_session_token',
                         regex=r'(?<![A-Za-z0-9_.-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])',score=.95)])

    def validate_result(self,pattern_text):
        # Structural validation only. A signature/key check is neither performed nor needed for masking.
        try:
            header=pattern_text.split('.')[0]
            decoded=base64.b64decode(header+'='*((-len(header))%4),altchars=b'-_',validate=True)
            value=json.loads(decoded)
            return isinstance(value,dict) and isinstance(value.get('alg'),str) and bool(value['alg'])
        except (ValueError,UnicodeError):
            return False
