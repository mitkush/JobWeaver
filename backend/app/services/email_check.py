"""Recipient format, no-reply and MX checks. DNS failures are explicit warnings."""

import re

import dns.asyncresolver
import dns.exception
import dns.resolver
from email_validator import EmailNotValidError, validate_email

from app.schemas.drafts import EmailCheck

_NO_REPLY = re.compile(r"(?:no[._-]?reply|do[._-]?not[._-]?reply)", re.I)


async def check_recipient(recipient: str) -> EmailCheck:
    warnings = []
    try:
        address = validate_email(recipient, check_deliverability=False)
    except EmailNotValidError:
        return EmailCheck(recipient=recipient, valid=False, warnings=["Invalid email format"])
    if _NO_REPLY.search(address.local_part):
        warnings.append("This looks like a no-reply address")
    try:
        answers = await dns.asyncresolver.resolve(address.ascii_domain, "MX", lifetime=3)
        if not any(str(answer.exchange) != "." for answer in answers):
            warnings.append("The domain does not accept email (null MX)")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        warnings.append("The domain has no MX record")
    except (dns.exception.DNSException, OSError):
        warnings.append("Could not verify the domain's MX records; try again")
    return EmailCheck(recipient=address.normalized, valid=not warnings, warnings=warnings)
