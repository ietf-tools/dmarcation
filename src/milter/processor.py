import logging
import urllib.parse
from email.headerregistry import Address
from email.utils import getaddresses
from typing import Iterable, Optional, Union

from checkdmarc import dmarc
from kilter.protocol import Accept, Discard, Header
from kilter.service import END, Runner, Session

from src import services
from src.utils import get_config_value

logger = logging.getLogger(__name__)


def check_required_headers(required_config: dict, headers: list[dict]) -> bool:
    """
    Check the headers to see if any required entries are present.

    Returns True if the required headers are present, or if no headers
    are required.
    """

    if "header" not in required_config:
        return True

    for header_entry in headers:
        required_value = required_config["header"].get(header_entry["name"], None)
        stripped_header = header_entry["value"].strip()

        if (
            required_value is True
            or (isinstance(required_value, str) and stripped_header == required_value)
            or (isinstance(required_value, list) and stripped_header in required_value)
        ):
            return True

    return False


def check_dmarc_rejection(domain: str):
    """
    Checks the domain DMARC policy.

    Returns True if the policy is to `reject` or `quarantine`
    Returns False otherwise
    """

    no_mail_values = ["reject", "quarantine"]

    try:
        dmarc_record = dmarc.get_dmarc_record(domain)

        is_subdomain = dmarc_record["location"] != domain

        logger.debug(
            "Domain %(domain)s is subdomain for %(location)s: %(res)s",
            {
                "domain": domain,
                "location": dmarc_record["location"],
                "res": is_subdomain,
            },
        )

        if (
            not is_subdomain
            and dmarc_record["parsed"]["tags"]["p"]["value"] in no_mail_values
        ):
            logger.debug(
                "Do not allow: Is domain and 'p' is %(value)s",
                {"value": dmarc_record["parsed"]["tags"]["p"]["value"]},
            )
            return True

        if (
            is_subdomain
            and dmarc_record["parsed"]["tags"]["sp"]["value"] in no_mail_values
        ):
            logger.debug(
                "Do not allow: Is subdomain and 'sp' is %(value)s",
                {"value": dmarc_record["parsed"]["tags"]["sp"]["value"]},
            )
            return True

    except dmarc.DMARCError as e:
        logger.error("Ignoring DMARC error: %(reason)s", {"reason": str(e)})

    return False


def check_all_dmarc_rejections(domains: Iterable[str]):
    """
    Checks the DMARC policy for multiple domains.

    Returns True if all the domains indicate the policy is `reject` or `quarantine`
    Returns False otherwise
    """

    for domain in domains:
        if check_dmarc_rejection(domain) is False:
            logger.debug("Domain %(domain)s indicates acceptance", {"domain": domain})
            return False

    logger.debug("No domain indicates acceptance")
    return True


def rewrite_email_address(
    email: tuple[str, str], domain: str, quote_char: str = "="
) -> str:
    """
    Generate a rewritten RFC compliant email address from a displayname/email pair

    The new address will be an encoded version of the original but from the provided domain.
    """
    address = Address(email[0], quote_email_address(email[1], quote_char), domain)

    return str(address)


def unrewrite_email_address(email: tuple[str, str], quote_char: str = "=") -> str:
    """
    Reverses the rewrite used to cloak the email addresses in the forward direction.

    The return is a simple string.
    """
    unquoted_address = unquote_email_address(extract_localpart(email[1]), quote_char)
    address = Address(email[0], addr_spec=unquoted_address)

    return str(address)


def quote_email_address(email_addr: str, percent_quote_char: str = "=") -> str:
    """
    Quotes an email address to be safe as a local part

    It is quoted as if it was for a URL, but the `%` characters are then replaced
    by the provided string (default: `=`)
    """
    return urllib.parse.quote(email_addr).replace("%", percent_quote_char)


def unquote_email_address(email_addr: str, percent_quote_char: str = "=") -> str:
    """
    Unquotes an email address that was quoted to be safe as a local part

    The `%` characters are reinstated by replacing the provided string (default: `=`)
    The result is then unquoted as if it was from a URL.
    """
    return urllib.parse.unquote(email_addr.replace(percent_quote_char, "%"))


def extract_domain(email_addr: str) -> Optional[str]:
    """Extract the domain from an email address"""
    return email_addr.split("@", 2)[1] if "@" in email_addr else False


def extract_localpart(email_addr: str) -> str:
    """Extract the localpart from an email address"""
    return email_addr.split("@", 2)[0] if "@" in email_addr else email_addr


async def rewrite_forward(
    session: Session, from_header: Header, from_value: str
) -> bool:
    """
    Performs the forward DMARC rewrite

    This means taking the original From address(es) and placing them into the
    `X-Original-From` header, and then replacing the From with encoded versions
    from a domain which will not cause the message to be rejected or quarantined.

    Returns True on success, or False otherwise.
    """
    header_from_addresses = [address for address in getaddresses([from_value])]

    from_domains = filter(
        None, [extract_domain(email[1]) for email in header_from_addresses]
    )

    try:
        should_reject = check_all_dmarc_rejections(from_domains)

        if not should_reject:
            return True

        # We need to rewrite the addresses. We do this by putting the original "From"
        # into "X-Original-From" and then using an encoded version of the "From" address
        # as the local part of a new email address that uses a domain that we control.

        replacement_addresses = [
            rewrite_email_address(
                email,
                get_config_value(services["app_config"], "domain"),
                get_config_value(services["app_config"], "rewrite.quote_char", "="),
            )
            for email in header_from_addresses
        ]

        replacement_from = " " + ", ".join(replacement_addresses)

        logger.debug(
            "Replacing Original From: %(header_from)s With: %(replacement_from)s",
            {
                "header_from": from_value,
                "replacement_from": replacement_from,
            },
        )

        new_header = Header("X-Original-From", from_value.encode())

        await session.headers.insert(new_header, END)
        await session.headers.update(from_header, replacement_from.encode())

        return True

    except Exception as e:
        logger.error("Unhandled error: %(reason)s", {"reason": str(e)})

        return False


async def rewrite_reverse(
    session: Session,
    from_header: Header,
    original_from_header: Header,
    original_from_value,
) -> bool:
    """
    Performs the reverse DMARC rewrite

    This means taking the `X-Original-From` address(es) and then replacing the From
    with the decoded versions.

    Returns True on success, or False otherwise.
    """
    if not original_from_header or not original_from_value:
        logger.debug("Invalid original from header detected.")
        return False

    logger.debug("Restoring From header to be the original from")
    await session.headers.delete(original_from_header)
    await session.headers.update(from_header, original_from_value.encode())

    return True


@Runner
async def handle(session: Session) -> Union[Accept, Discard]:
    """
    The milter processor for dmarcation.

    In order to pass the DMARC challenges we need to manipulate some of the
    addresses. This is done through the use of the `X-Original-From` header.

    If the rewrite configuration has a set of required headers then rewriting will
    not occur if those headers are not present.
    """

    mail_headers = []

    from_header = None
    original_from_header = None

    async with session.headers as headers:
        async for header in headers:
            header_entry = {
                "name": header.name,
                "lower_name": header.name.lower(),
                "value": header.value.decode(),
            }

            if header_entry["lower_name"] == "from":
                from_header = header
                from_value = header_entry["value"]

            elif header_entry["lower_name"] == "x-original-from":
                original_from_header = header
                original_from_value = header_entry["value"]

            mail_headers.append(header_entry)

    required_config_entry = get_config_value(
        services["app_config"], "rewrite.require", None
    )
    required_config = (
        {} if not required_config_entry else required_config_entry.as_dict()
    )

    # If the required headers are not present then we do not process the mail
    if not check_required_headers(required_config, mail_headers):
        return Accept()

    # At this stage we are ready to do the rewriting
    if original_from_header and get_config_value(
        services["app_config"], "rewrite.reverse", True
    ):
        # Time to reverse the rewriting
        await rewrite_reverse(
            session, from_header, original_from_header, original_from_value
        )

    elif get_config_value(services["app_config"], "rewrite.forward", True):
        # Do the rewriting
        await rewrite_forward(session, from_header, from_value)

    return Accept()
