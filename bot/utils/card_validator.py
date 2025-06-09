import re


class CardValidator:
    """Utility class for validating credit card information"""

    @staticmethod
    def validate_card_number(card_number: str) -> tuple[bool, str]:
        """Validate card number format and basic checksums"""
        cleaned_number = re.sub(r'[\s\-]', '', card_number)
        if not cleaned_number.isdigit():
            return False, "Card number must contain only digits"
        if len(cleaned_number) < 13 or len(cleaned_number) > 19:
            return False, f"Card number must be 13-19 digits (got {len(cleaned_number)})"
        if not CardValidator._luhn_check(cleaned_number):
            return False, "Card number failed Luhn algorithm validation"
        return True, ""

    @staticmethod
    def validate_cvv(cvv: str, card_number: str = None) -> tuple[bool, str]:
        """Validate CVV format"""
        cleaned_cvv = cvv.strip()
        if not cleaned_cvv.isdigit():
            return False, "CVV must contain only digits"
        if len(cleaned_cvv) < 3 or len(cleaned_cvv) > 4:
            return False, f"CVV must be 3-4 digits (got {len(cleaned_cvv)})"
        if card_number:
            cleaned_card = re.sub(r'[\s\-]', '', card_number)
            if cleaned_card.startswith(('34', '37')) and len(cleaned_cvv) != 4:
                return False, "American Express cards require 4-digit CVV"
            elif not cleaned_card.startswith(('34', '37')) and len(cleaned_cvv) != 3:
                return False, "This card type requires 3-digit CVV"
        return True, ""

    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        """Implement Luhn algorithm for card number validation"""
        def luhn_digit(digit, even):
            doubled = digit * 2 if even else digit
            return doubled - 9 if doubled > 9 else doubled

        digits = [int(d) for d in card_number]
        checksum = sum(luhn_digit(d, i % 2 == len(digits) % 2) for i, d in enumerate(digits))
        return checksum % 10 == 0

    @staticmethod
    def format_card_number(card_number: str) -> str:
        """Clean and format card number (remove spaces/dashes, keep digits only)"""
        return re.sub(r'[\s\-]', '', card_number)
